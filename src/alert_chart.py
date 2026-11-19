# -*- coding: utf-8 -*-
"""緊急アラートに添える図（Step ALC）— 公式の数字で描き、出典を画像に焼き込む

オーナー指示（2026-11-19）:
  「画像などサイトや公式から必ず出典引用してほしい。どの緊急アラートでも。」

**なぜ他所のチャート画像を直リンクせず、自分で描くか**
  公式サイトのチャート画像をそのまま貼る案もあったが、緊急アラートでは特に採れない。

  1. **本文の数字と食い違っても気づけない。** 「日経先物 -3.1%」と書いた真下に、
     締め時刻の違う他所の画像が並ぶ。緊急の知らせで数字と絵が矛盾するのは最悪。
  2. **先方がURLを変えた日に、絵だけ消える。** この案件では nikkei225jp.com が
     フォルダ名を1語変えただけでデータが1ヶ月止まった実績がある。
  3. **相手のサーバーに通信費を負わせる。**

  なので「**公式の数字を取ってきて、こちらで描き、出典を画像に焼き込む**」。
  これなら絵と本文は必ず一致し、どこの数字かも画像を見れば分かる。

⚠️ **アラートが図のせいで遅れたり消えたりしてはいけない。**
   図は「あれば添える」もの。取得も描画も短い制限時間で打ち切り、
   駄目ならテキストだけで必ず届ける（呼び出し側が None を受ける）。
"""
import json
import urllib.request

from src.utils import setup_logger, get_dirs, get_jst_now
from src.sources import cite_image, source_for_symbol

logger = setup_logger("alert_chart")

_HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

_BG, _FG, _DIM = "#0b0e14", "#eaf0fa", "#8a99ae"
_UP, _DOWN, _GRID = "#2fd98a", "#ff4d63", "#1d2531"

_MAX_LINES = 4          # 5本以上は線が重なって読めない
_TIMEOUT = 8            # 1銘柄あたりの取得上限（秒）。緊急なので待たない


def intraday(symbol: str):
    """その日の値動きを「前日終値からの%」で返す。取れなければ空。

    ⚠️ `chartPreviousClose` を前日終値として使ってよいのは **range=1d のときだけ**
       （CLAUDE.md の最重要の罠）。ここは 1d なので使える。
       5d や 1y で同じことをすると、前日比が桁違いの嘘になる。
    """
    sym = str(symbol or "").replace("CFD:", "")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?interval=5m&range=1d")
    try:
        req = urllib.request.Request(url, headers=_HEAD)
        res = json.load(urllib.request.urlopen(req, timeout=_TIMEOUT))
        r = res["chart"]["result"][0]
        prev = r["meta"].get("chartPreviousClose")
        closes = r["indicators"]["quote"][0]["close"]
        if not isinstance(prev, (int, float)) or not prev:
            return []
        return [(float(c) / prev - 1) * 100
                for c in closes if isinstance(c, (int, float))]
    except Exception as e:
        logger.debug(f"日中の値動きを取れませんでした [{symbol}]: {e}")
        return []


def make(alerts: list, out_path: str = None, title: str = "急変した銘柄の今日の動き"):
    """アラート対象の値動きを1枚に描く。描けなければ None。

    alerts: [{"symbol","name","change"}, ...]（alert_monitor が作る形）
    """
    try:
        import matplotlib
        matplotlib.use("Agg")       # GitHub Actions は画面が無いので必須
        import matplotlib.pyplot as plt
        # ⚠️ 日本語が「□□□」になるのを防ぐ。japanize_matplotlib が無い環境
        #    （手元のWindows・入れ忘れたworkflow）でも読める字で描けるよう、
        #    他の9モジュールと同じ入れ替え先を並べておく。
        try:
            import japanize_matplotlib  # noqa: F401
        except ImportError:
            matplotlib.rcParams["font.family"] = [
                "Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic",
                "Yu Gothic", "Meiryo", "DejaVu Sans"]
    except Exception as e:
        logger.info(f"matplotlib が無いため図は添えません: {e}")
        return None

    try:
        rows, keys = [], []
        for a in (alerts or [])[:_MAX_LINES]:
            sym = a.get("symbol")
            vals = intraday(sym)
            if len(vals) < 5:
                continue
            rows.append((a.get("name") or sym, vals, a.get("change")))
            keys.append(source_for_symbol(sym))
        if not rows:
            logger.info("日中データが取れず、図は添えません")
            return None

        out = out_path or str(
            get_dirs()["charts"] /
            f"alert_{get_jst_now().strftime('%Y%m%d_%H%M%S')}.png")

        fig, ax = plt.subplots(figsize=(8.2, 4.4), dpi=150)
        fig.patch.set_facecolor(_BG)
        ax.set_facecolor(_BG)

        for name, vals, chg in rows:
            # 銘柄ごとに時間の本数が違う（取引時間が違う）ので、
            # 横軸は時刻ではなく「その日の進み具合 0〜100%」に揃える。
            # ⚠️ ここを本数で揃えると、24時間動く先物と東京の現物が
            #    まったく違う時間帯のまま重なり、読み違える。
            n = len(vals)
            xs = [i / (n - 1) * 100 for i in range(n)]
            col = _UP if vals[-1] >= 0 else _DOWN
            ax.plot(xs, vals, color=col, linewidth=2.0, zorder=3)
            ax.fill_between(xs, vals, 0, color=col, alpha=0.10, zorder=2)
            label = f"{name} {vals[-1]:+.2f}%"
            ax.annotate(label, (xs[-1], vals[-1]), xytext=(-4, 6),
                        textcoords="offset points", ha="right",
                        color=col, fontsize=11, fontweight="bold", zorder=4)

        ax.axhline(0, color=_DIM, linewidth=1.0, linestyle="--", zorder=1)
        ax.set_title(f"{title}（前日終値からの変化）",
                     color=_FG, fontsize=13, fontweight="bold", pad=12)
        ax.set_xlabel("その日の取引時間の進み具合（%）", color=_DIM, fontsize=9)
        ax.set_ylabel("前日終値からの変化（%）", color=_DIM, fontsize=9)
        ax.tick_params(colors=_DIM, labelsize=9)
        ax.grid(True, color=_GRID, linewidth=0.8, zorder=0)
        for s in ax.spines.values():
            s.set_color(_GRID)

        # 出典を画像に焼き込む。画像だけが転送されても出どころが残るように。
        fig.text(0.012, 0.015, cite_image(*keys), color=_DIM, fontsize=7.5)
        fig.text(0.988, 0.015,
                 get_jst_now().strftime("%Y-%m-%d %H:%M JST 時点"),
                 color=_DIM, fontsize=7.5, ha="right")

        fig.tight_layout(rect=(0, 0.035, 1, 1))
        fig.savefig(out, facecolor=_BG)
        plt.close(fig)
        logger.info(f"アラート図を作成: {out}（{len(rows)}銘柄）")
        return out
    except Exception:
        # ⚠️ 図が描けないことでアラートを落とさない。必ず None で返す。
        logger.error("アラート図の作成に失敗（テキストのみで送ります）", exc_info=True)
        return None


def candle_chart(symbol: str, label: str = "", days: int = 30,
                 sources=("yahoo",), out_path: str = None):
    """急変した銘柄のローソク足。描けなければ None。

    値動きの折れ線（`make`）は「今日どう動いたか」、こちらは
    「**ここ1ヶ月の中で今日がどういう日か**」を見せる。
    急落の日に、それが下げ続きの延長なのか、上げていた所からの急反転なのかで
    意味がまったく違うので、アラートにはこちらが効く場面がある。
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        try:
            import japanize_matplotlib  # noqa: F401
        except ImportError:
            matplotlib.rcParams["font.family"] = [
                "Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic",
                "Yu Gothic", "Meiryo", "DejaVu Sans"]
    except Exception as e:
        logger.info(f"matplotlib が無いため図は添えません: {e}")
        return None

    try:
        from src.feed_visuals import ohlc
        # 25日平均を引くには表示本数より長い履歴が要る
        allrows = ohlc(str(symbol).replace("CFD:", ""), "6mo") or []
        rows = allrows[-days:]
        if len(rows) < 5:
            logger.info(f"4本値が足りないため図は添えません [{symbol}]")
            return None

        out = out_path or str(
            get_dirs()["charts"] /
            f"candle_{get_jst_now().strftime('%Y%m%d_%H%M%S')}.png")
        fig, ax = plt.subplots(figsize=(8.2, 4.4), dpi=150)
        fig.patch.set_facecolor(_BG)
        ax.set_facecolor(_BG)

        for i, (o, h, l, c) in enumerate(rows):
            col = _UP if c >= o else _DOWN
            ax.plot([i, i], [l, h], color=col, linewidth=1.1, zorder=3)
            ax.add_patch(plt.Rectangle(
                (i - 0.32, min(o, c)), 0.64, max(abs(c - o), (h - l) * 0.004),
                facecolor=col, edgecolor=col, zorder=4))

        # 移動平均線（5日＝ここ1週間、25日＝ここ1ヶ月の平均）
        cl = [r[3] for r in allrows]
        for n, col in ((5, "#ffc24d"), (25, "#6aa9ff")):
            ma = [None if i + 1 < n else sum(cl[i + 1 - n:i + 1]) / n
                  for i in range(len(cl))][len(allrows) - len(rows):]
            xs = [i for i, v in enumerate(ma) if v is not None]
            ys = [ma[i] for i in xs]
            if len(xs) >= 2:
                ax.plot(xs, ys, color=col, linewidth=1.4,
                        label=f"{n}日平均", zorder=5)
        if any(True for _ in (5, 25)):
            lg = ax.legend(loc="upper right", fontsize=8, frameon=False,
                           labelcolor=_DIM)
            if lg:
                lg.get_frame().set_alpha(0)

        last = rows[-1][3]
        ax.axhline(last, color=_FG, linewidth=0.7, linestyle="--",
                   alpha=0.45, zorder=1)
        ax.annotate(f"{last:,.0f}", (len(rows) - 1, last), xytext=(8, 0),
                    textcoords="offset points", va="center",
                    color=_FG, fontsize=11, fontweight="bold", zorder=6)
        ax.set_title(f"{label or symbol}　直近{len(rows)}営業日の日足",
                     color=_FG, fontsize=13, fontweight="bold", pad=12)
        ax.set_xlabel("緑＝その日上げた　赤＝下げた　／　細い線はその日の高値と安値",
                      color=_DIM, fontsize=9)
        ax.tick_params(colors=_DIM, labelsize=9)
        ax.set_xticks([])
        ax.grid(True, axis="y", color=_GRID, linewidth=0.8, zorder=0)
        for sp in ax.spines.values():
            sp.set_color(_GRID)

        fig.text(0.012, 0.015, cite_image(*sources), color=_DIM, fontsize=7.5)
        fig.text(0.988, 0.015,
                 get_jst_now().strftime("%Y-%m-%d %H:%M JST 時点"),
                 color=_DIM, fontsize=7.5, ha="right")
        fig.tight_layout(rect=(0, 0.035, 1, 1))
        fig.savefig(out, facecolor=_BG)
        plt.close(fig)
        logger.info(f"ローソク足の図を作成: {out}（{len(rows)}本）")
        return out
    except Exception:
        logger.error("ローソク足の図の作成に失敗（テキストのみで送ります）",
                     exc_info=True)
        return None


def level_chart(values, label: str, sources=("nikkei_vi",),
                bands=(), band_note: str = "", out_path: str = None, note: str = ""):
    """水準そのものの推移を描く（恐怖指数など）。描けなければ None。

    bands: [(値, 色, 説明), ...] 判定の線を引く。
      ⚠️ **線を引くときは必ず説明も書く。** 「32.8」とだけ言われても
         高いのか低いのか分からないのが恐怖指数で、意味が出るのは
         「普段のどのあたりか」を示したときだけ（この案件で一度、
         上から14%の高さを「平常」と表示していた）。
    """
    vals = [v for v in (values or []) if isinstance(v, (int, float))]
    if len(vals) < 10:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        try:
            import japanize_matplotlib  # noqa: F401
        except ImportError:
            matplotlib.rcParams["font.family"] = [
                "Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic",
                "Yu Gothic", "Meiryo", "DejaVu Sans"]
    except Exception as e:
        logger.info(f"matplotlib が無いため図は添えません: {e}")
        return None

    try:
        out = out_path or str(
            get_dirs()["charts"] /
            f"level_{get_jst_now().strftime('%Y%m%d_%H%M%S')}.png")
        fig, ax = plt.subplots(figsize=(8.2, 4.2), dpi=150)
        fig.patch.set_facecolor(_BG)
        ax.set_facecolor(_BG)

        xs = list(range(len(vals)))
        ax.plot(xs, vals, color=_FG, linewidth=1.8, zorder=3)
        ax.fill_between(xs, vals, min(vals), color=_FG, alpha=0.07, zorder=2)

        # ⚠️ 線の名前は**背景を敷いて**書く。最初これを敷かずに折れ線の上へ
        #    直接置いたため、肝心の「ここから上は異常」が線に埋もれて
        #    読めなかった。読めない注意書きは無いのと同じ。
        # 半透明(0.85)だと折れ線が透けて読みにくかったので、不透明にする
        box = dict(boxstyle="round,pad=0.3", facecolor=_BG,
                   edgecolor="none", alpha=1.0)
        for y, col, desc in (bands or []):
            if not isinstance(y, (int, float)):
                continue
            ax.axhline(y, color=col, linewidth=1.2, linestyle="--", zorder=1)
            ax.annotate(f"{desc}　{y:.1f}", (0, y), xytext=(4, 6),
                        textcoords="offset points", color=col, fontsize=9,
                        bbox=box, zorder=5)

        ax.annotate(f"今 {vals[-1]:.1f}", (xs[-1], vals[-1]), xytext=(-6, 12),
                    textcoords="offset points", ha="right",
                    color=_FG, fontsize=12, fontweight="bold",
                    bbox=box, zorder=6)
        ax.set_title(f"{label}　この{len(vals)}営業日の推移",
                     color=_FG, fontsize=13, fontweight="bold", pad=12)
        # ⚠️ 図は直近だけを映すが、線は**全履歴の分布**から引いている。
        #    断らないと「この図の中の上位5%」と読まれ、意味がずれる。
        ax.set_xlabel("← 古い　　　　営業日　　　　新しい →"
                      + (f"　／　{band_note}" if band_note else ""),
                      color=_DIM, fontsize=9)
        ax.tick_params(colors=_DIM, labelsize=9)
        ax.grid(True, color=_GRID, linewidth=0.8, zorder=0)
        for s in ax.spines.values():
            s.set_color(_GRID)

        fig.text(0.012, 0.015, cite_image(*sources), color=_DIM, fontsize=7.5)
        fig.text(0.988, 0.015,
                 note or get_jst_now().strftime("%Y-%m-%d %H:%M JST 時点"),
                 color=_DIM, fontsize=7.5, ha="right")
        fig.tight_layout(rect=(0, 0.035, 1, 1))
        fig.savefig(out, facecolor=_BG)
        plt.close(fig)
        logger.info(f"水準の図を作成: {out}（{len(vals)}点）")
        return out
    except Exception:
        logger.error("水準の図の作成に失敗（テキストのみで送ります）", exc_info=True)
        return None


if __name__ == "__main__":
    p = make([{"symbol": "^N225", "name": "日経平均", "change": -1.34},
              {"symbol": "USDJPY=X", "name": "ドル円", "change": -0.09}])
    print(p)
