import Foundation

enum MarketError: Error { case badURL, http(Int), noData }

/// データ取得。価格は Yahoo Finance のチャートAPI（非公式・キー不要）、
/// ニュースは Google News RSS（このリポジトリのPython側と同じ取得元）。
enum MarketService {
    private static let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 12
        c.httpAdditionalHeaders = ["User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"]
        return URLSession(configuration: c)
    }()

    // MARK: 価格

    private struct ChartResponse: Decodable {
        let chart: Chart
        struct Chart: Decodable { let result: [Result]? }
        struct Result: Decodable { let meta: Meta; let indicators: Indicators }
        struct Meta: Decodable {
            let regularMarketPrice: Double?
            let chartPreviousClose: Double?
            let shortName: String?
        }
        struct Indicators: Decodable { let quote: [Q] }
        struct Q: Decodable { let close: [Double?]? }
    }

    struct Series {
        var name: String?
        var price: Double?
        var prevClose: Double?
        var points: [Double]
    }

    static func series(symbol: String, range: String = "1d", interval: String = "5m") async throws -> Series {
        guard let enc = symbol.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "https://query1.finance.yahoo.com/v8/finance/chart/\(enc)?range=\(range)&interval=\(interval)")
        else { throw MarketError.badURL }
        let (data, resp) = try await session.data(from: url)
        if let code = (resp as? HTTPURLResponse)?.statusCode, code != 200 { throw MarketError.http(code) }
        let r = try JSONDecoder().decode(ChartResponse.self, from: data)
        guard let res = r.chart.result?.first else { throw MarketError.noData }
        let pts = (res.indicators.quote.first?.close ?? []).compactMap { $0 }   // 休場中の null を除く
        return Series(name: res.meta.shortName,
                      price: res.meta.regularMarketPrice ?? pts.last,
                      prevClose: res.meta.chartPreviousClose,
                      points: pts)
    }

    static func quote(for item: WatchItem) async throws -> Quote {
        let s = try await series(symbol: item.symbol)
        guard let price = s.price, let prev = s.prevClose ?? s.points.first else { throw MarketError.noData }
        return Quote(symbol: item.symbol,
                     name: item.name.isEmpty ? (s.name ?? item.symbol) : item.name,
                     price: price, prevClose: prev,
                     points: downsample(s.points, to: 60), updated: Date())
    }

    static func downsample(_ p: [Double], to n: Int) -> [Double] {
        guard p.count > n, n > 1 else { return p }
        let step = Double(p.count - 1) / Double(n - 1)
        return (0..<n).map { p[Int((Double($0) * step).rounded())] }
    }

    // MARK: ニュース

    static func news(query: String = "日経平均 OR 株価 OR 為替 OR 米国株 when:1d", limit: Int = 8) async throws -> [NewsItem] {
        var c = URLComponents(string: "https://news.google.com/rss/search")!
        c.queryItems = [.init(name: "q", value: query), .init(name: "hl", value: "ja"),
                        .init(name: "gl", value: "JP"), .init(name: "ceid", value: "JP:ja")]
        guard let url = c.url else { throw MarketError.badURL }
        let (data, _) = try await session.data(from: url)
        var seen = Set<String>()
        return NewsParser().parse(data)
            .sorted { ($0.date ?? .distantPast) > ($1.date ?? .distantPast) }
            .filter { seen.insert($0.title).inserted }
            .prefix(limit).map { $0 }
    }

    // MARK: 配信ファイル（ウィジェット用）

    /// Actionsが数時間ごとに作る静的JSON。端末はこれを読むだけ（Yahooを直接叩かない）
    static let feedURL = URL(string: "https://youn24.github.io/market-ai-secretary/widget_feed.json")!
    /// 3時間更新＋予約実行の遅れを見込んだ上限。これを超えたら「古い」と明示する
    static let feedMaxAge: TimeInterval = 8 * 3600

    static func loadFeed() async -> (snapshot: Snapshot?, stale: Bool) {
        var req = URLRequest(url: feedURL)
        req.cachePolicy = .reloadIgnoringLocalCacheData
        if let (data, resp) = try? await session.data(for: req),
           (resp as? HTTPURLResponse)?.statusCode == 200 {
            let d = JSONDecoder(); d.dateDecodingStrategy = .iso8601
            if let snap = try? d.decode(Snapshot.self, from: data), !snap.quotes.isEmpty {
                Shared.saveCache(snap)
                return (snap, Date().timeIntervalSince(snap.fetched) > feedMaxAge)
            }
        }
        return (Shared.loadCache(), true)   // 取れない日は前回分を「古い」と明示して返す
    }

    // MARK: まとめ取得（アプリ用・ライブ）


    /// 取得に失敗した部分は直前のキャッシュで補い、古いデータなら stale=true を返す。
    /// 「取れなかったのに新しいように見せる」ことはしない。
    static func loadSnapshot() async -> (snapshot: Snapshot?, stale: Bool) {
        let watch = Watchlist.load()
        async let newsTask: [NewsItem]? = try? await news()

        let quotes: [Quote] = await withTaskGroup(of: (Int, Quote?).self) { group in
            for (i, w) in watch.enumerated() {
                group.addTask { (i, try? await quote(for: w)) }
            }
            var out: [(Int, Quote)] = []
            for await (i, q) in group { if let q { out.append((i, q)) } }
            return out.sorted { $0.0 < $1.0 }.map { $0.1 }
        }
        let freshNews = await newsTask
        let cache = Shared.loadCache()

        if quotes.isEmpty {
            return (cache, true)                      // 完全失敗: キャッシュを古いと明示して返す
        }
        let snap = Snapshot(quotes: quotes,
                            news: (freshNews?.isEmpty == false ? freshNews : cache?.news) ?? [],
                            fetched: Date())
        Shared.saveCache(snap)
        return (snap, quotes.count < watch.count)     // 一部欠けたときも注意表示
    }
}

// MARK: - RSSパーサ

final class NewsParser: NSObject, XMLParserDelegate {
    private var items: [NewsItem] = []
    private var cur: [String: String] = [:]
    private var text = ""
    private var inItem = false

    private static let df: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"
        return f
    }()

    func parse(_ data: Data) -> [NewsItem] {
        let p = XMLParser(data: data); p.delegate = self; p.parse(); return items
    }

    func parser(_ parser: XMLParser, didStartElement name: String, namespaceURI: String?,
                qualifiedName: String?, attributes: [String: String] = [:]) {
        if name == "item" { inItem = true; cur = [:] }
        text = ""
    }
    func parser(_ parser: XMLParser, foundCharacters string: String) { text += string }
    func parser(_ parser: XMLParser, foundCDATA CDATABlock: Data) {
        text += String(data: CDATABlock, encoding: .utf8) ?? ""
    }
    func parser(_ parser: XMLParser, didEndElement name: String, namespaceURI: String?, qualifiedName: String?) {
        guard inItem else { return }
        if name == "item" {
            inItem = false
            guard var title = cur["title"], let link = cur["link"], let url = URL(string: link) else { return }
            let source = cur["source"] ?? ""
            // 末尾の " - 配信元" は配信元と一致したときだけ落とす（題名の一部を削らない）
            if !source.isEmpty, title.hasSuffix(" - \(source)") { title = String(title.dropLast(source.count + 3)) }
            items.append(NewsItem(title: title, source: source, date: Self.df.date(from: cur["pubDate"] ?? ""), url: url))
        } else {
            cur[name] = text.trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }
}
