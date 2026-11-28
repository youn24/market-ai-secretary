"""
drawdown_screener の検証（ネット不要・合成データ）

  python -m tests.test_drawdown_screener
  （pytest があれば pytest tests/ でも動く）
"""
import numpy as np
import pandas as pd

from src import drawdown_screener as ds


def _series(start, end, days=260, seed=0):
    """start→end へ直線的に動く日足（平日のみ）にわずかなノイズを乗せる。"""
    idx = pd.bdate_range(end="2026-11-26", periods=days)
    rng = np.random.default_rng(seed)
    base = np.linspace(start, end, days)
    return pd.Series(base * (1 + rng.normal(0, 0.003, days)), index=idx)


def test_price_metrics_6m_is_date_based():
    s = _series(100, 50)
    m = ds._price_metrics(s)
    six_ago = s[s.index <= s.index[-1] - pd.Timedelta(days=182)].iloc[-1]
    assert abs(m["ret_6m"] - (s.iloc[-1] / six_ago - 1)) < 1e-9
    assert m["from_high"] < -0.4
    assert m["rsi14"] is not None and 0 <= m["rsi14"] <= 100


def test_short_history_is_skipped():
    assert ds._price_metrics(_series(100, 90, days=60)) is None


def test_classify_cheap_and_growing_is_candidate():
    f = ds._fundamentals({"forwardPE": 12, "trailingPE": 15, "priceToBook": 3,
                          "trailingEps": 5, "forwardEps": 6, "revenueGrowth": 0.1})
    assert ds._classify("US", f)["bucket"] == "割安候補"


def test_classify_cheap_but_eps_falling_is_caution():
    # 景気循環株の天井: 予想PERは安いが来期EPSが大きく減る
    f = ds._fundamentals({"forwardPE": 6, "trailingPE": 4, "priceToBook": 2,
                          "trailingEps": 10, "forwardEps": 6, "revenueGrowth": 0.3})
    c = ds._classify("JP", f)
    assert c["bucket"] == "要注意"
    assert any("来年の利益が今より40%減る予想" == x for x in c["flags"]), c["flags"]


def test_classify_expensive_is_pricey():
    f = ds._fundamentals({"forwardPE": 35, "trailingEps": 2, "forwardEps": 2.5,
                          "revenueGrowth": 0.2})
    assert ds._classify("US", f)["bucket"] == "割高のまま"


def test_classify_loss_making_is_caution_even_if_not_cheap():
    f = ds._fundamentals({"forwardPE": 80, "trailingEps": -1, "forwardEps": 0.5})
    assert ds._classify("US", f)["bucket"] == "要注意"


def test_jp_low_pbr_counts_as_cheap():
    f = ds._fundamentals({"forwardPE": 19, "priceToBook": 0.8,
                          "trailingEps": 100, "forwardEps": 105})
    assert ds._classify("JP", f)["bucket"] == "割安候補"
    assert ds._classify("US", f)["bucket"] == "割高のまま"


def test_garbage_values_are_dropped():
    f = ds._fundamentals({"forwardPE": float("nan"), "trailingPE": -3,
                          "priceToBook": "Infinity", "revenueGrowth": 99})
    assert f["fwd_per"] is None and f["ttm_per"] is None
    assert f["pbr"] is None and f["rev_growth"] is None
    assert ds._classify("US", f)["bucket"] == "判定不可"


def test_scan_end_to_end_with_fakes():
    us = {"AAA": "下げて安い", "BBB": "下げて罠", "CCC": "上げた", "DDD": "下げて高い"}
    jp = {"1111.T": "データなし"}
    closes = {
        "AAA": _series(100, 60, seed=1),
        "BBB": _series(100, 55, seed=2),
        "CCC": _series(100, 140, seed=3),
        "DDD": _series(100, 70, seed=4),
    }
    infos = {
        "AAA": {"forwardPE": 11, "trailingEps": 4, "forwardEps": 4.5, "revenueGrowth": 0.08},
        "BBB": {"forwardPE": 7, "trailingEps": 10, "forwardEps": 5},
        "DDD": {"forwardPE": 40, "trailingEps": 1, "forwardEps": 1.2},
    }
    called = []

    def fake_info(sym):
        called.append(sym)
        return infos[sym]

    res = ds.scan(us=us, jp=jp, downloader=lambda syms: closes, info_fetcher=fake_info,
                  rates_fetcher=lambda: {})
    assert res["available"]
    assert [x["symbol"] for x in res["candidates"]] == ["AAA"]
    assert [x["symbol"] for x in res["caution"]] == ["BBB"]
    assert [x["symbol"] for x in res["pricey"]] == ["DDD"]
    assert "CCC" not in called, "上げた銘柄に .info を叩いてはいけない"
    assert res["no_data"] == ["1111.T"]
    text = ds.format_text(res)
    assert "割安候補" in text and "来年の利益" in text


def test_scan_refuses_when_most_prices_missing():
    res = ds.scan(us={"A": "a", "B": "b", "C": "c"}, jp={},
                  downloader=lambda syms: {}, info_fetcher=lambda s: {},
                  rates_fetcher=lambda: {})
    assert not res["available"]


def test_design_section_renders():
    from src.design_ai import _drawdown_section
    res = ds.scan(us={"AAA": "テスト銘柄"}, jp={},
                  downloader=lambda syms: {"AAA": _series(100, 50)},
                  info_fetcher=lambda s: {"forwardPE": 9, "trailingEps": 10, "forwardEps": 6},
                  rates_fetcher=lambda: {"US": {"now": 4.6, "avg": 4.1}})
    html = _drawdown_section(res)
    assert "テスト銘柄" in html and "利益が減りそう" in html
    assert "基準を少し厳しく" in html and "金利が取れなかった" in html  # 日本は金利なし
    assert "PER" in html and "RSI" not in html.split("売られすぎ")[0]  # 記号は説明欄だけ
    assert _drawdown_section({"available": False}) == ""


def test_rate_adjusted_per():
    # 金利が平均どおり → 基準そのまま
    assert ds._rate_adjusted_per(18.0, 4.0, 4.0) == 18.0
    # 平均より+0.5% → 益回り5.56%+0.5% → 16.5倍
    assert ds._rate_adjusted_per(18.0, 4.5, 4.0) == 16.5
    # 平均より-1% → ゆるく
    assert ds._rate_adjusted_per(18.0, 3.0, 4.0) > 18.0
    # 取れない日は動かさない
    assert ds._rate_adjusted_per(14.0, None, 1.5) == 14.0
    # 極端な値でも上下限に収まる
    assert ds._rate_adjusted_per(18.0, 20.0, 4.0) == ds.PER_BOUNDS[0]
    assert ds._rate_adjusted_per(18.0, -20.0, 4.0) == ds.PER_BOUNDS[1]


def test_higher_rates_turn_borderline_into_pricey():
    # PER17倍・利益増の米国株: 金利いつもどおりなら割安候補、金利が高ければ割高のまま
    us = {"AAA": "境目の銘柄"}
    closes = {"AAA": _series(100, 60, seed=7)}
    info = {"forwardPE": 17, "trailingEps": 5, "forwardEps": 5.5}
    calm = ds.scan(us=us, jp={}, downloader=lambda s: closes, info_fetcher=lambda s: info,
                   rates_fetcher=lambda: {"US": {"now": 4.0, "avg": 4.0}})
    hot = ds.scan(us=us, jp={}, downloader=lambda s: closes, info_fetcher=lambda s: info,
                  rates_fetcher=lambda: {"US": {"now": 4.8, "avg": 4.0}})
    assert [x["symbol"] for x in calm["candidates"]] == ["AAA"]
    assert [x["symbol"] for x in hot["pricey"]] == ["AAA"]
    assert hot["rates"]["US"]["adjusted"] and not hot["rates"]["JP"]["adjusted"]


def test_rates_fetch_failure_keeps_fixed_threshold():
    def boom():
        raise RuntimeError("network down")
    res = ds.scan(us={"AAA": "a"}, jp={}, downloader=lambda s: {"AAA": _series(100, 60)},
                  info_fetcher=lambda s: {"forwardPE": 17, "trailingEps": 5, "forwardEps": 5.5},
                  rates_fetcher=boom)
    assert res["available"] and res["thresholds"]["cheap_per"]["US"] == 18.0


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"{n} tests passed")
