import WidgetKit
import SwiftUI

// MARK: - Timeline

struct MarketEntry: TimelineEntry {
    let date: Date
    let snapshot: Snapshot?
    let stale: Bool
}

struct MarketProvider: TimelineProvider {
    func placeholder(in context: Context) -> MarketEntry {
        MarketEntry(date: Date(), snapshot: .sample, stale: false)
    }

    func getSnapshot(in context: Context, completion: @escaping (MarketEntry) -> Void) {
        if context.isPreview { completion(placeholder(in: context)); return }
        Task { completion(await load()) }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<MarketEntry>) -> Void) {
        Task {
            let entry = await load()
            // iOSは更新回数に予算を持つ（目安: 1日40〜70回）。15分は「要求」であって保証ではない
            let next = Date().addingTimeInterval(15 * 60)
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }

    private func load() async -> MarketEntry {
        let (snap, stale) = await MarketService.loadSnapshot()
        return MarketEntry(date: Date(), snapshot: snap, stale: stale)
    }
}

// MARK: - Views

struct MarketWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: MarketEntry

    var body: some View {
        Group {
            if let snap = entry.snapshot, let main = snap.quotes.first {
                switch family {
                case .systemSmall:        SmallView(q: main, entry: entry)
                case .systemMedium:       MediumView(snap: snap, entry: entry)
                case .systemLarge:        LargeView(snap: snap, entry: entry)
                case .accessoryRectangular: LockRectView(q: main)
                case .accessoryInline:
                    Text("\(main.name) \(Fmt.price(main.price)) \(Fmt.pct(main.changePct))")
                default:                  SmallView(q: main, entry: entry)
                }
            } else {
                VStack(spacing: 4) {
                    Image(systemName: "wifi.exclamationmark")
                    Text("データを取得できません").font(.caption.bold())
                    Text("アプリを開いて更新").font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
        .containerBackground(.fill.tertiary, for: .widget)
    }
}

private struct Footer: View {
    let entry: MarketEntry
    var body: some View {
        HStack(spacing: 3) {
            if entry.stale { Text("⚠︎ 古いデータ").foregroundStyle(.orange) }
            Spacer(minLength: 0)
            // 取得時刻を必ず出す。「リアルタイム」ではなく「いつ時点か」を示す
            Text(entry.snapshot?.fetched ?? entry.date, style: .time)
        }
        .font(.system(size: 9)).foregroundStyle(.secondary)
    }
}

private struct PriceHeader: View {
    let q: Quote
    var big = false
    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(q.name).font(.caption.bold()).foregroundStyle(.secondary).lineLimit(1)
            Text(Fmt.price(q.price))
                .font(.system(size: big ? 26 : 20, weight: .bold, design: .rounded))
                .minimumScaleFactor(0.6).lineLimit(1)
            Text("\(Fmt.signed(q.change))  \(Fmt.pct(q.changePct))")
                .font(.caption.bold()).foregroundStyle(q.tint).lineLimit(1).minimumScaleFactor(0.7)
        }
    }
}

private struct SmallView: View {
    let q: Quote; let entry: MarketEntry
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            PriceHeader(q: q)
            Sparkline(points: q.points, prevClose: q.prevClose, tint: q.tint)
            Footer(entry: entry)
        }
    }
}

private struct NewsRow: View {
    let n: NewsItem
    var body: some View {
        Link(destination: n.url) {
            VStack(alignment: .leading, spacing: 1) {
                Text(n.title).font(.caption).lineLimit(2).multilineTextAlignment(.leading)
                Text(n.source).font(.system(size: 9)).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct MediumView: View {
    let snap: Snapshot; let entry: MarketEntry
    var body: some View {
        let q = snap.quotes[0]
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                PriceHeader(q: q)
                Sparkline(points: q.points, prevClose: q.prevClose, tint: q.tint)
            }
            .frame(maxWidth: .infinity)
            VStack(alignment: .leading, spacing: 6) {
                ForEach(snap.news.prefix(3)) { NewsRow(n: $0) }
                Spacer(minLength: 0)
                Footer(entry: entry)
            }
            .frame(maxWidth: .infinity)
        }
    }
}

private struct QuoteChip: View {
    let q: Quote
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(q.name).font(.system(size: 10, weight: .bold)).foregroundStyle(.secondary).lineLimit(1)
            Text(Fmt.price(q.price)).font(.system(size: 13, weight: .bold, design: .rounded))
                .lineLimit(1).minimumScaleFactor(0.6)
            Text(Fmt.pct(q.changePct)).font(.system(size: 10, weight: .bold)).foregroundStyle(q.tint)
            Sparkline(points: q.points, prevClose: q.prevClose, tint: q.tint).frame(height: 24)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct LargeView: View {
    let snap: Snapshot; let entry: MarketEntry
    var body: some View {
        let q = snap.quotes[0]
        VStack(alignment: .leading, spacing: 8) {
            PriceHeader(q: q, big: true)
            Sparkline(points: q.points, prevClose: q.prevClose, tint: q.tint).frame(maxHeight: 110)
            HStack(alignment: .top, spacing: 10) {
                ForEach(snap.quotes.dropFirst().prefix(3)) { QuoteChip(q: $0) }
            }
            Divider()
            ForEach(snap.news.prefix(3)) { NewsRow(n: $0) }
            Spacer(minLength: 0)
            Footer(entry: entry)
        }
    }
}

private struct LockRectView: View {
    let q: Quote
    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("\(q.name)  \(Fmt.pct(q.changePct))").font(.caption.bold()).lineLimit(1)
            Text(Fmt.price(q.price)).font(.headline)
            Sparkline(points: q.points, prevClose: q.prevClose, tint: .primary)
        }
    }
}

// MARK: - Widget

struct MarketWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "MarketWidget", provider: MarketProvider()) { entry in
            MarketWidgetView(entry: entry)
        }
        .configurationDisplayName("市場ウォッチ")
        .description("ウォッチリストの値動きチャートと最新ニュース")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge,
                            .accessoryRectangular, .accessoryInline])
    }
}

@main
struct MarketWidgetBundle: WidgetBundle {
    var body: some Widget { MarketWidget() }
}
