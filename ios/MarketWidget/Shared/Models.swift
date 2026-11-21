import Foundation

// MARK: - データモデル（アプリとウィジェットで共有）

struct Quote: Codable, Identifiable, Hashable {
    var id: String { symbol }
    let symbol: String
    let name: String
    let price: Double
    /// 前日終値。range=1d の chartPreviousClose だけが前日終値を指す
    /// （5d/1y では「レンジ直前の終値」になり前日比が桁違いになる。CLAUDE.md 参照）
    let prevClose: Double
    let points: [Double]
    let updated: Date

    var change: Double { price - prevClose }
    var changePct: Double { prevClose == 0 ? 0 : change / prevClose * 100 }
    var isUp: Bool { change >= 0 }
}

struct NewsItem: Codable, Identifiable, Hashable {
    var id: String { url.absoluteString }
    let title: String
    let source: String
    let date: Date?
    let url: URL
}

struct Snapshot: Codable {
    var quotes: [Quote]
    var news: [NewsItem]
    var fetched: Date
}

struct WatchItem: Codable, Hashable, Identifiable {
    var id: String { symbol }
    let symbol: String
    var name: String
}

// MARK: - 共有ストレージ（App Group）

enum Shared {
    /// ⚠️ バンドルIDのプレフィックスを変えたら、ここと project.yml の両方を直すこと
    static let groupID = "group.com.youn24.marketwidget"

    static var defaults: UserDefaults { UserDefaults(suiteName: groupID) ?? .standard }

    static var cacheURL: URL {
        let base = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: groupID)
            ?? FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        return base.appendingPathComponent("snapshot.json")
    }

    static func loadCache() -> Snapshot? {
        guard let data = try? Data(contentsOf: cacheURL) else { return nil }
        let d = JSONDecoder(); d.dateDecodingStrategy = .iso8601
        return try? d.decode(Snapshot.self, from: data)
    }

    static func saveCache(_ s: Snapshot) {
        let e = JSONEncoder(); e.dateEncodingStrategy = .iso8601
        if let data = try? e.encode(s) { try? data.write(to: cacheURL, options: .atomic) }
    }
}

enum Watchlist {
    static let key = "watchlist.v1"

    static let defaults: [WatchItem] = [
        WatchItem(symbol: "^N225", name: "日経225"),
        WatchItem(symbol: "USDJPY=X", name: "ドル円"),
        WatchItem(symbol: "^GSPC", name: "S&P500"),
        WatchItem(symbol: "^IXIC", name: "ナスダック"),
        WatchItem(symbol: "^VIX", name: "VIX"),
    ]

    static func load() -> [WatchItem] {
        guard let data = Shared.defaults.data(forKey: key),
              let list = try? JSONDecoder().decode([WatchItem].self, from: data),
              !list.isEmpty else { return defaults }
        return list
    }

    static func save(_ list: [WatchItem]) {
        if let data = try? JSONEncoder().encode(list) { Shared.defaults.set(data, forKey: key) }
    }
}

// MARK: - 表示用ヘルパー

enum Fmt {
    static func price(_ v: Double) -> String {
        v.formatted(.number.precision(.fractionLength(2)))
    }
    static func pct(_ v: Double) -> String {
        (v >= 0 ? "+" : "") + v.formatted(.number.precision(.fractionLength(2))) + "%"
    }
    static func signed(_ v: Double) -> String {
        (v >= 0 ? "+" : "") + v.formatted(.number.precision(.fractionLength(2)))
    }
}

extension Snapshot {
    /// プレースホルダー専用（ウィジェットギャラリー・プレビュー）。実データとして表示しない
    static let sample = Snapshot(
        quotes: [
            Quote(symbol: "^N225", name: "日経225", price: 50123.45, prevClose: 49800, points: (0..<40).map { 49800 + Double($0) * 8 + sin(Double($0) / 3) * 60 }, updated: Date()),
            Quote(symbol: "USDJPY=X", name: "ドル円", price: 154.21, prevClose: 154.6, points: (0..<40).map { 154.6 - Double($0) * 0.01 + sin(Double($0) / 4) * 0.1 }, updated: Date()),
            Quote(symbol: "^GSPC", name: "S&P500", price: 6012.3, prevClose: 5990, points: (0..<40).map { 5990 + Double($0) * 0.5 }, updated: Date()),
        ],
        news: [
            NewsItem(title: "サンプル見出し: 市場の動きを要約", source: "サンプル", date: Date(), url: URL(string: "https://news.google.com")!),
            NewsItem(title: "サンプル見出し: 為替と金利の注目点", source: "サンプル", date: Date(), url: URL(string: "https://news.google.com")!),
        ],
        fetched: Date())
}
