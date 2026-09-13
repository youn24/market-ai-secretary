"""
急変アラートモニター
15分ごとに市場を監視して急変時にTelegram通知
"""
import os
import json
import traceback
from datetime import timedelta
from pathlib import Path
from src.utils import setup_logger, get_jst_now, get_dirs, BASE_DIR

logger = setup_logger("alert_monitor")

# アラートの閾値（暴落級のみ通知）
# 細かい急変通知は廃止。本当に大きな暴落・恐怖急騰の時だけ安全網として通知する。
#   dir="down" … その%以上の「下落」で発火
#   dir="up"   … その%以上の「上昇」で発火（VIX＝恐怖の急騰用）
# 日経はほぼ24時間動くCME先物(NIY=F)を主監視 — 夜間の暴落も検知できる。
# 現物(^N225)は先物取得失敗時の安全網としてザラ場中のみ機能する。
THRESHOLDS = {
    "NIY=F": {"name": "日経先物(CME 24h)", "pct": 3.0,  "dir": "down"},
    "^N225": {"name": "日経平均(現物)",     "pct": 3.0,  "dir": "down"},
    "^GSPC": {"name": "S&P500",           "pct": 2.5,  "dir": "down"},
    "^IXIC": {"name": "NASDAQ",           "pct": 3.0,  "dir": "down"},
    "^VIX":  {"name": "VIX恐怖指数",       "pct": 25.0, "dir": "up"},
}

# 連発防止: 同じ銘柄のアラートは1セッションにつき「一度だけ」送る。
# セッション = JST 6:00 〜 翌 5:59（夜間の暴落が日付をまたいでも1回に保たれる）。
# 例外はエスカレーションのみ: 1回目より1.5倍以上悪化したときだけ、
# セッション中に1度だけ追加で知らせる（2026-08-19にオーナー了承）。
# それ以外は追撃しない（オーナー指示: 何度も通知しない）。
_STATE_FILE = BASE_DIR / "data" / "alert_state.json"


def _session_key(now=None) -> str:
    """JST 6時始まりの取引セッションを表すキー（例: 2026-07-30）。"""
    now = now or get_jst_now()
    return (now - timedelta(hours=6)).strftime("%Y-%m-%d")


# 1回目の通知からこの倍率を超えて悪化したら、もう一度だけ知らせる。
# 例: -2.6%で通知したあと -3.9%（1.5倍）まで進んだら再通知。
#
# なぜ必要か: 2026-08-18に日経先物が -2.6% で発報したあと -4.0% まで悪化したが、
# 「1日1回」の決まりで2回目が出せず、事態の悪化が伝わらなかった。
# かといって毎回鳴らすと読み飛ばされるので、
# 「最初の警報が霞むほど状況が変わったときだけ」に限って1度だけ許す。
_ESCALATE_FACTOR = 1.5
# 何度も段階的に鳴るのを防ぐため、1セッションでの再通知はこの回数まで
_ESCALATE_MAX = 1


def _apply_cooldown(alerts: list, source: str = "alert") -> list:
    """
    同一銘柄はこのセッションで既に通知済みなら送らない（1回だけ）。
    ただし1回目より大きく悪化した場合に限り、もう一度だけ通す（エスカレーション）。
    さらに共通の通知台帳を通し、他のモジュールが同じ話題を既に伝えていれば
    重ねて送らない（VIX急騰が複数の入口から届くのを防ぐ）。
    """
    now  = get_jst_now()
    skey = _session_key(now)
    try:
        st = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    kept = []
    for a in alerts:
        rec = st.get(a["symbol"])
        if isinstance(rec, dict) and rec.get("session") == skey:
            prev = rec.get("chg")
            sent = int(rec.get("escalated", 0))
            # ちょうど1.5倍のときに取りこぼさないよう、わずかな誤差を許す。
            # 2.6*1.5 は 3.9000000000000004 になり、素直に比べると
            # -3.9% が「まだ1.5倍未満」と判定されてしまう。
            worse = (prev is not None
                     and abs(a["change"]) >= abs(prev) * _ESCALATE_FACTOR - 1e-9
                     # 反対方向に振れただけの場合は「悪化」ではないので除外する
                     and (a["change"] > 0) == (prev > 0))
            if worse and sent < _ESCALATE_MAX:
                a["escalated"] = True
                a["prev_change"] = prev
                logger.info(f"悪化のため再通知: {a['name']} "
                            f"({prev:+.2f}% → {a['change']:+.2f}%)")
                kept.append(a)
                continue
            logger.info(f"通知済みのためスキップ: {a['name']} ({a['change']:+.2f}%)")
            continue
        kept.append(a)
    # 共通台帳で他モジュールとの重複を排除。
    # ただしエスカレーション（悪化による再通知）は台帳を通さない。
    # 台帳は「同じ話題を二度送らない」ための仕組みなので、
    # ここを通すと意図した再通知まで確実に消される（実際に消えていた）。
    escalated = [a for a in kept if a.get("escalated")]
    normal    = [a for a in kept if not a.get("escalated")]
    try:
        from src.notify_ledger import filter_new
        normal = filter_new(normal, key_func=lambda a: a["symbol"],
                            topic_func=lambda a: None, source=source)
    except Exception:
        logger.error("通知台帳の照会に失敗しました", exc_info=True)
    kept = normal + escalated

    if kept:
        for a in kept:
            prev_rec = st.get(a["symbol"]) or {}
            # 前日以前の記録は引き継がない。
            # セッションを見ずに引き継ぐと、昨日1回使った再通知枠が今日も
            # 埋まったままになり、翌日の悪化を知らせられなくなる。
            if prev_rec.get("session") != skey:
                prev_rec = {}
            escalated = int(prev_rec.get("escalated", 0))
            if a.get("escalated"):
                escalated += 1
            st[a["symbol"]] = {
                "session": skey, "ts": now.isoformat(),
                # 記録する変化率は、そのセッション中で最も大きかった値にする。
                # 直近値で上書きすると、いったん戻したときに基準が下がり、
                # 同じ水準まで再び悪化しただけで再通知が出てしまう。
                "chg": max([a["change"], prev_rec.get("chg", a["change"])], key=abs),
                "escalated": escalated,
            }
        # 古い記録を掃除（当日セッション分のみ残す＝ファイルの肥大化防止）
        st = {k: v for k, v in st.items()
              if isinstance(v, dict) and v.get("session") == skey}
        try:
            _STATE_FILE.parent.mkdir(exist_ok=True)
            _STATE_FILE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.debug(traceback.format_exc())
    return kept


def check_alerts(prices: dict) -> list:
    """暴落級アラートをチェックして通知リストを返す"""
    alerts = []
    for sym, config in THRESHOLDS.items():
        p = prices.get(sym, {})
        chg = p.get("change_pct")
        val = p.get("latest")
        if chg is None or val is None:
            continue
        threshold = config["pct"]
        direction = config.get("dir", "down")
        hit = (chg <= -threshold) if direction == "down" else (chg >= threshold)
        if hit:
            arrow = "急騰🔺" if chg > 0 else "急落🔻"
            alerts.append({
                "symbol": sym,
                "name": config["name"],
                "value": val,
                "change": chg,
                "direction": arrow,
                "threshold": threshold,
            })
    return alerts


def _esc_tag(a: dict) -> str:
    """
    再通知の行に付ける印。
    「また同じ通知が来た」と誤解されないよう、1回目からどれだけ進んだかを必ず書く。
    """
    if not a.get("escalated"):
        return ""
    prev = a.get("prev_change")
    if prev is None:
        return "　⚠️ *さらに悪化*"
    return f"　⚠️ *さらに悪化*（1回目 {prev:+.2f}% → 今 {a['change']:+.2f}%）"


def build_alert_message(alerts: list, prices: dict, fear_greed: dict, risk: dict) -> str:
    """アラートメッセージを生成"""
    now = get_jst_now().strftime("%Y-%m-%d %H:%M JST")
    fg  = fear_greed.get("score")
    fg_r= fear_greed.get("rating_ja","---")
    fg_disp = f"{fg:.0f}" if fg is not None else "---"

    lines = [
        f"🚨 *重大アラート：市場が大きく動いています* 🚨",
        f"⏰ {now}",
        f"━━━━━━━━━━━━━━━",
    ]

    for a in alerts:
        chg = a["change"]
        s   = "▲" if chg > 0 else "▼"
        lines.append(f"{a['direction']} *{a['name']}*: {a['value']:,.2f} ({s}{abs(chg):.2f}%)")
        if _esc_tag(a):
            lines.append(_esc_tag(a))

    lines += [
        f"━━━━━━━━━━━━━━━",
        f"🌡 地合い: {risk.get('sentiment','---')}",
        f"😱 Fear&Greed: {fg_disp} ({fg_r})",
        f"📱 市場AI秘書",
    ]
    return "\n".join(lines)


# 米国時間外の個別株アラート閾値（決算級の大きな反応のみ・スパム防止）
AH_ALERT_PCT = 5.0

# 日本市場への影響が直接的な銘柄は、より小さな動きでも知らせる。
# 日本株ADR（ソニー・トヨタ等）は翌朝の同じ銘柄にほぼそのまま反映されるため
# 3%でも十分大きい。半導体の主要株も日本の装置株・半導体株に直結する。
AH_ALERT_PCT_JP_LINKED = 3.0

# その銘柄が動いたとき、日本のどこに効くか（通知に添えて判断を助ける）
_JP_IMPACT = {
    "SONY": "ソニーG", "TM": "トヨタ", "HMC": "ホンダ",
    "MUFG": "三菱UFJ", "SMFG": "三井住友FG", "MFG": "みずほFG",
    "NVDA": "半導体株（東エレク・アドテスト・レーザーテック）",
    "TSM": "半導体株", "AVGO": "半導体株", "MU": "半導体メモリ関連",
    "ASML": "半導体装置（東エレク・レーザーテック）",
    "AMAT": "半導体装置（東エレク・SCREEN）",
    "LRCX": "半導体装置（東エレク・SCREEN）", "KLAC": "レーザーテック",
    "ARM": "ソフトバンクG",
    "AAPL": "部品株（村田・TDK・イビデン）",
    "TSLA": "EV関連（パナソニック・デンソー）",
    "GM": "自動車株", "F": "自動車株",
    "CAT": "建機（コマツ・日立建機）", "DE": "クボタ",
    "GE": "重工（三菱重工・IHI）", "BA": "重工・航空部品",
    "FCX": "非鉄・商社", "XOM": "資源・商社", "CVX": "資源・商社",
    "JPM": "メガバンク", "GS": "証券（野村・大和）", "C": "メガバンク",
    "NKE": "アシックス・ゴールドウイン", "MCD": "日本マクドナルド",
    "DIS": "オリエンタルランド", "COIN": "暗号資産関連", "MSTR": "暗号資産関連",
    "FDX": "物流（景気の先行指標）", "UPS": "物流",
}
_JP_LINKED = {
    # 日本株ADR＝米国市場で取引される日本企業そのもの
    "SONY", "TM", "MUFG", "SMFG", "HMC", "MFG",
    # 日本の半導体・装置株を直接動かす銘柄
    "NVDA", "TSM", "ASML", "AMAT", "LRCX", "KLAC", "MU", "AVGO", "ARM",
    # アップルは村田・TDK・日本電産など部品株のサプライチェーンに直結
    "AAPL",
}

# ── CFD/24時間マーケット監視（株価指数先物・コモディティ・欧州指数）──────
# CFD業者が24時間配信している価格の実体＝これらの先物/指数。
# 日本の夜間に大きく動くとそのまま翌朝の寄り付きに影響するため上下どちらも通知。
# 閾値は各商品の平常ボラティリティに合わせて個別設定（原油・銀は元々よく動く）。
CFD_WATCH = [
    # 株価指数先物（24時間）
    ("NIY=F", "日経225先物(CME)",   "指数", 2.0),
    ("ES=F",  "S&P500先物",         "指数", 1.5),
    ("NQ=F",  "NASDAQ100先物",      "指数", 2.0),
    ("YM=F",  "NYダウ先物",          "指数", 1.5),
    # 欧州株価指数（日本の夕方〜深夜が取引時間）
    ("^GDAXI", "ドイツDAX",         "欧州", 2.0),
    ("^FTSE",  "英FTSE100",        "欧州", 2.0),
    # コモディティ（商品先物・CFDの主力）
    ("GC=F",  "金(ゴールド)",        "商品", 2.0),
    ("SI=F",  "銀(シルバー)",        "商品", 3.5),
    ("CL=F",  "WTI原油",            "商品", 3.5),
    ("NG=F",  "天然ガス",            "商品", 5.0),
    ("HG=F",  "銅",                 "商品", 2.5),
    ("ZC=F",  "トウモロコシ",        "商品", 3.0),
]
_CFD_ICON = {"指数": "📈", "欧州": "🇪🇺", "商品": "🛢"}


def run_cfd_alert() -> bool:
    """
    CFD/24時間マーケット（指数先物・欧州指数・コモディティ）の急変を通知。
    夜間に金や原油、欧州株が大きく動いた場合も翌朝の東京市場に影響するため、
    上昇・下落どちらの方向でも閾値超えで知らせる。
    """
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from src.cfd_sq import _fetch_one

        hits = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(_fetch_one, s): (s, n, cat, th)
                    for s, n, cat, th in CFD_WATCH}
            for fut in as_completed(futs):
                s, n, cat, th = futs[fut]
                d = fut.result()
                if not d or d.get("change_pct") is None:
                    continue
                chg = d["change_pct"]
                if abs(chg) >= th:
                    hits.append({"symbol": f"CFD:{s}", "name": n, "cat": cat,
                                 "value": d.get("latest"), "change": chg,
                                 "direction": "急騰🔺" if chg > 0 else "急落🔻"})
        if not hits:
            logger.info(f"CFD/24時間: 閾値超えの急変なし（{len(CFD_WATCH)}銘柄チェック済み）")
            return False

        hits.sort(key=lambda x: abs(x["change"]), reverse=True)
        alerts = _apply_cooldown(hits, source="cfd")
        if not alerts:
            return False

        now = get_jst_now().strftime("%m-%d %H:%M JST")
        lines = [
            "🌐 *24時間マーケットで大きな動き* 🚨",
            f"⏰ {now}",
            "━━━━━━━━━━━━━━━",
        ]
        for cat in ("指数", "欧州", "商品"):
            grp = [a for a in alerts if a["cat"] == cat]
            if not grp:
                continue
            lines.append(f"{_CFD_ICON[cat]} *{cat}*")
            for a in grp[:4]:
                v = a.get("value")
                v_s = f"{v:,.2f}" if v and v < 1000 else f"{v:,.0f}" if v else "—"
                s = "▲" if a["change"] > 0 else "▼"
                lines.append(f"　{a['direction']} {a['name']}: {v_s} ({s}{abs(a['change']):.2f}%)")
                if _esc_tag(a):
                    lines.append(_esc_tag(a))
        lines += [
            "━━━━━━━━━━━━━━━",
            "CFDで24時間動く先物・商品の急変です。翌朝の東京市場や関連セクターに波及しやすい動きです。",
            "📱 市場AI秘書",
        ]

        from src.notify_telegram import send_message
        send_message("\n".join(lines))
        logger.info(f"🚨 CFD/24時間アラート送信: {len(alerts)}銘柄")
        return True
    except Exception:
        logger.error("CFD/24時間アラートエラー")
        logger.debug(traceback.format_exc())
        return False


def run_afterhours_alert() -> bool:
    """
    米国主要株の時間外（アフターアワーズ/プレマーケット）±5%級の大変動を通知。
    決算発表への最初の反応など、翌朝の東京市場に波及しやすい動きを夜のうちに知らせる。
    「1セッション1回だけ」のゲートは指数アラートと共用。
    """
    try:
        from src.us_afterhours import run as run_us
        us = run_us()
        # 日本市場に直結する銘柄は低い閾値（3%）、それ以外は決算級（5%）で判定する
        def _threshold(sym: str) -> float:
            return AH_ALERT_PCT_JP_LINKED if sym in _JP_LINKED else AH_ALERT_PCT

        movers = [m for m in us.get("movers", [])
                  if abs(m.get("chg_pct") or 0) >= _threshold(m.get("symbol", ""))]
        if not movers:
            logger.info(f"時間外の個別株変動なし"
                        f"（日本連動銘柄±{AH_ALERT_PCT_JP_LINKED:.0f}% / "
                        f"その他±{AH_ALERT_PCT:.0f}%）")
            return False

        alerts = [{
            "symbol": f"AH:{m['symbol']}",
            "name":   f"{m['name']}({m['symbol']})",
            "value":  m.get("price"),
            "change": m["chg_pct"],
            "direction": "急騰🔺" if m["chg_pct"] > 0 else "急落🔻",
            "jp": _JP_IMPACT.get(m["symbol"], ""),
        } for m in movers]
        alerts = _apply_cooldown(alerts, source="afterhours")
        if not alerts:
            return False

        session = movers[0].get("session", "post")
        s_label = "引け後の時間外" if session == "post" else "寄り付き前の時間外"
        now = get_jst_now().strftime("%m-%d %H:%M JST")
        lines = [
            "🇺🇸 *時間外で大きな動き* 🚨",
            f"⏰ {now}（{s_label}）",
            "━━━━━━━━━━━━━━━",
        ]
        for a in alerts[:5]:
            price_s = f"${a['value']:,.2f}" if a.get("value") else "—"
            s = "▲" if a["change"] > 0 else "▼"
            lines.append(f"{a['direction']} *{a['name']}*: {price_s} ({s}{abs(a['change']):.1f}%)")
            if _esc_tag(a):
                lines.append(_esc_tag(a))
            if a.get("jp"):
                lines.append(f"　→ 日本の{a['jp']}に波及しやすい")
        lines += [
            "━━━━━━━━━━━━━━━",
            "決算・材料への時間外反応。翌朝の東京市場の関連銘柄・セクターに波及しやすい動きです。",
            "📱 市場AI秘書",
        ]

        from src.notify_telegram import send_message
        send_message("\n".join(lines))
        logger.info(f"🚨 時間外ムーバーアラート送信: {len(alerts)}銘柄")
        return True
    except Exception:
        logger.error("時間外アラートエラー")
        logger.debug(traceback.format_exc())
        return False


def run_alert_check(prices: dict, fear_greed: dict, risk: dict) -> bool:
    """アラートチェックを実行してTelegram通知"""
    try:
        # 日経先物(CME・ほぼ24時間)を取得して監視対象へ注入 — 夜間の暴落も捕捉
        try:
            from src.cfd_sq import _fetch_one
            f = _fetch_one("NIY=F")
            if f and f.get("latest") and f.get("change_pct") is not None:
                prices = {**prices, "NIY=F": f}
                logger.info(f"日経先物: {f['latest']:,.0f} ({f['change_pct']:+.2f}%)")
        except Exception:
            logger.debug(traceback.format_exc())

        alerts = check_alerts(prices)
        # 先物と現物が同時ヒットした場合は先物のみ通知（重複排除）
        syms = {a["symbol"] for a in alerts}
        if "NIY=F" in syms and "^N225" in syms:
            alerts = [a for a in alerts if a["symbol"] != "^N225"]
        alerts = _apply_cooldown(alerts, source="crash")
        if not alerts:
            logger.info(f"アラートなし（{len(prices)}銘柄チェック済み）")
            return False

        logger.info(f"🚨 急変検知: {len(alerts)}件")
        msg = build_alert_message(alerts, prices, fear_greed, risk)

        # Gemini AIによる急変分析（別送せず本文に統合＝アラートは必ず1通）
        try:
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            if api_key:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

                alert_text = "\n".join(
                    f"・{a['name']}: {a['direction']} {abs(a['change']):.2f}%"
                    for a in alerts
                )
                prompt = f"""市場で以下の急変が発生しました：
{alert_text}

投資家への簡潔なコメントを150文字以内で書いてください。
事実と推測を分け、断定表現は使わないでください。"""

                resp = model.generate_content(prompt)
                ai_comment = (resp.text or "").strip()[:300]
                if ai_comment:
                    msg += f"\n\n🤖 *AI緊急分析*\n{ai_comment}"
                logger.info("Gemini急変分析をアラート本文へ統合")
        except Exception as e:
            logger.error(f"Gemini急変分析エラー: {e}")

        from src.notify_telegram import send_message
        send_message(msg)
        return True

    except Exception as e:
        logger.error(f"アラートチェックエラー: {e}")
        logger.debug(traceback.format_exc())
        return False
