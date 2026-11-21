import SwiftUI
import Charts
import WidgetKit

@main
struct MarketApp: App {
    var body: some Scene {
        WindowGroup { RootView() }
    }
}

// MARK: - Store

@MainActor
final class Store: ObservableObject {
    @Published var snapshot: Snapshot?
    @Published var stale = false
    @Published var loading = false
    @Published var watch: [WatchItem] = Watchlist.load()

    func refresh() async {
        guard !loading else { return }
        loading = true
        let r = await MarketService.loadSnapshot()
        snapshot = r.snapshot
        stale = r.stale
        loading = false
        WidgetCenter.shared.reloadAllTimelines()   // アプリを開いたときはウィジェットも即更新
    }

    func saveWatch() {
        Watchlist.save(watch)
        Task { await refresh() }
    }
}

// MARK: - Root

struct RootView: View {
    @StateObject private var store = Store()

    var body: some View {
        TabView {
            MarketTab().tabItem { Label("マーケット", systemImage: "chart.line.uptrend.xyaxis") }
            NewsTab().tabItem { Label("ニュース", systemImage: "newspaper") }
            SettingsTab().tabItem { Label("設定", systemImage: "slider.horizontal.3") }
        }
        .environmentObject(store)
        .task {
            // アプリを開いている間だけ60秒ごとに更新。ウィジェットとは別の話
            while !Task.isCancelled {
                await store.refresh()
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }
}

// MARK: - Market

struct MarketTab: View {
    @EnvironmentObject var store: Store

    var body: some View {
        NavigationStack {
            List {
                if store.stale {
                    Label("一部または全部を取得できませんでした（古い数字を含みます）", systemImage: "exclamationmark.triangle")
                        .font(.footnote).foregroundStyle(.orange)
                }
                ForEach(store.snapshot?.quotes ?? []) { q in
                    NavigationLink(value: q) { QuoteRow(q: q) }
                }
                if let t = store.snapshot?.fetched {
                    Text("取得: \(t.formatted(date: .omitted, time: .standard))（配信元の遅延あり）")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("マーケット")
            .navigationDestination(for: Quote.self) { DetailView(q: $0) }
            .refreshable { await store.refresh() }
            .overlay { if store.snapshot == nil && store.loading { ProgressView() } }
        }
    }
}

struct QuoteRow: View {
    let q: Quote
    var body: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(q.name).font(.headline)
                Text(q.symbol).font(.caption2).foregroundStyle(.secondary)
            }
            Spacer()
            Sparkline(points: q.points, prevClose: q.prevClose, tint: q.tint).frame(width: 70, height: 32)
            VStack(alignment: .trailing) {
                Text(Fmt.price(q.price)).font(.system(.body, design: .rounded).bold())
                Text(Fmt.pct(q.changePct)).font(.caption.bold()).foregroundStyle(q.tint)
            }
            .frame(minWidth: 90, alignment: .trailing)
        }
    }
}

struct DetailView: View {
    let q: Quote
    private let ranges: [(label: String, range: String, interval: String)] = [
        ("1日", "1d", "5m"), ("5日", "5d", "30m"), ("1か月", "1mo", "1d"), ("3か月", "3mo", "1d"),
    ]
    @State private var sel = 0
    @State private var points: [Double] = []
    @State private var failed = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // 1日以外は「期間の最初→最後」の変化。chartPreviousClose は使わない（前日比が壊れる）
            let base = sel == 0 ? q.prevClose : (points.first ?? q.prevClose)
            let last = sel == 0 ? q.price : (points.last ?? q.price)
            let up = last >= base
            Text(Fmt.price(last)).font(.system(size: 34, weight: .bold, design: .rounded))
            Text("\(Fmt.signed(last - base))  \(Fmt.pct(base == 0 ? 0 : (last - base) / base * 100))")
                .font(.headline).foregroundStyle(up ? Color.green : Color.red)

            Picker("期間", selection: $sel) {
                ForEach(ranges.indices, id: \.self) { Text(ranges[$0].label).tag($0) }
            }
            .pickerStyle(.segmented)

            if points.count >= 2 {
                let lo = points.min()!, hi = points.max()!
                Chart(Array(points.enumerated()), id: \.offset) { i, v in
                    LineMark(x: .value("t", i), y: .value("p", v))
                        .foregroundStyle(up ? Color.green : Color.red)
                        .interpolationMethod(.monotone)
                }
                .chartYScale(domain: lo...(hi > lo ? hi : lo + 1))
                .chartXAxis(.hidden)
                .frame(height: 260)
            } else if failed {
                Text("チャートを取得できませんでした").foregroundStyle(.secondary)
            } else {
                ProgressView().frame(maxWidth: .infinity, minHeight: 260)
            }
            Spacer()
        }
        .padding()
        .navigationTitle(q.name)
        .navigationBarTitleDisplayMode(.inline)
        .task(id: sel) {
            failed = false
            let r = ranges[sel]
            if let s = try? await MarketService.series(symbol: q.symbol, range: r.range, interval: r.interval),
               s.points.count >= 2 {
                points = s.points
            } else {
                points = []; failed = true
            }
        }
    }
}

// MARK: - News

struct NewsTab: View {
    @EnvironmentObject var store: Store
    var body: some View {
        NavigationStack {
            List(store.snapshot?.news ?? []) { n in
                Link(destination: n.url) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(n.title).font(.subheadline).foregroundStyle(.primary)
                        HStack {
                            Text(n.source)
                            if let d = n.date { Text(d, style: .relative) }
                        }
                        .font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("ニュース")
            .refreshable { await store.refresh() }
        }
    }
}

// MARK: - Settings

struct SettingsTab: View {
    @EnvironmentObject var store: Store
    @State private var symbol = ""
    @State private var name = ""
    @State private var message: String?
    @State private var checking = false

    var body: some View {
        NavigationStack {
            List {
                Section("ウォッチリスト（先頭の銘柄がウィジェットの主役）") {
                    ForEach(store.watch) { w in
                        VStack(alignment: .leading) {
                            Text(w.name.isEmpty ? w.symbol : w.name)
                            Text(w.symbol).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    .onDelete { store.watch.remove(atOffsets: $0); store.saveWatch() }
                    .onMove { store.watch.move(fromOffsets: $0, toOffset: $1); store.saveWatch() }
                }
                Section("銘柄を追加（Yahoo Financeのシンボル）") {
                    TextField("例: 7203.T / AAPL / EURJPY=X", text: $symbol)
                        .textInputAutocapitalization(.characters).autocorrectionDisabled()
                    TextField("表示名（任意）", text: $name)
                    Button(checking ? "確認中…" : "追加") { Task { await add() } }
                        .disabled(symbol.trimmingCharacters(in: .whitespaces).isEmpty || checking)
                    if let message { Text(message).font(.footnote).foregroundStyle(.orange) }
                }
                Section("ウィジェットについて") {
                    Text("ウィジェットの更新間隔はiOSが決めます。約15分ごとを要求しますが、省電力や更新回数の予算により遅れることがあります。ウィジェット下部の時刻が取得時点です。")
                        .font(.footnote).foregroundStyle(.secondary)
                    Text("価格はYahoo Financeの非公式APIから取得するため、無料枠の遅延（最大15〜20分）や取得制限が起こりえます。")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("設定")
            .toolbar { EditButton() }
        }
    }

    private func add() async {
        let s = symbol.trimmingCharacters(in: .whitespaces).uppercased()
        guard !store.watch.contains(where: { $0.symbol == s }) else { message = "登録済みです"; return }
        checking = true; defer { checking = false }
        // 実在確認してから登録する（存在しない銘柄でウィジェット全体が空になるのを防ぐ）
        guard let r = try? await MarketService.series(symbol: s), r.price != nil else {
            message = "「\(s)」のデータを取得できませんでした"; return
        }
        store.watch.append(WatchItem(symbol: s, name: name.trimmingCharacters(in: .whitespaces)))
        store.saveWatch()
        symbol = ""; name = ""; message = nil
    }
}
