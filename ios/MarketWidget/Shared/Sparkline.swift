import SwiftUI
import Charts

extension Quote {
    /// 配色はこのプロジェクトの規約に合わせる（上げ=緑・下げ=赤）。日本の慣習と逆なので注意
    var tint: Color { isUp ? .green : .red }
}

/// 軸なしの小チャート。点線は前日終値（1日チャートのときだけ渡す）
struct Sparkline: View {
    let points: [Double]
    var prevClose: Double? = nil
    let tint: Color

    var body: some View {
        if points.count < 2 {
            Color.clear
        } else {
            let lo = min(points.min() ?? 0, prevClose ?? .infinity)
            let rawHi = max(points.max() ?? 1, prevClose ?? -.infinity)
            let hi = rawHi - lo <= 0 ? lo + 1 : rawHi   // 値が全部同じでも領域がつぶれない
            Chart {
                ForEach(Array(points.enumerated()), id: \.offset) { i, v in
                    AreaMark(x: .value("t", i), yStart: .value("base", lo), yEnd: .value("p", v))
                        .foregroundStyle(LinearGradient(colors: [tint.opacity(0.35), tint.opacity(0.02)],
                                                        startPoint: .top, endPoint: .bottom))
                    LineMark(x: .value("t", i), y: .value("p", v))
                        .foregroundStyle(tint)
                        .lineStyle(StrokeStyle(lineWidth: 1.6, lineCap: .round, lineJoin: .round))
                        .interpolationMethod(.monotone)
                }
                if let p = prevClose {
                    RuleMark(y: .value("prev", p))
                        .lineStyle(StrokeStyle(lineWidth: 0.6, dash: [3, 3]))
                        .foregroundStyle(.secondary)
                }
            }
            .chartXAxis(.hidden)
            .chartYAxis(.hidden)
            .chartYScale(domain: lo...hi)
        }
    }
}
