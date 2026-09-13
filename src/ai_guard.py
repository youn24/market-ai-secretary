"""
AI事実検証ガード（フェーズ2・精度土台 L3）
Gemini などの AI テキストに含まれる数値が、実データと乖離していないか照合する。

主機能:
  verify_against(text, allowed_values, tol_pct) → (clean_text, suspects)
    - text 中の数字（小数・カンマ区切り）を正規表現で抽出
    - allowed_values（実データ辞書）のどの値とも tol_pct 以内に収まらない数字を "suspect" とする
    - suspects が 1 件以上あれば警告ログを出す

  inject_guard_prompt(base_prompt, prices) → hardened_prompt
    - すべての Gemini 呼び出し前に追加するプロンプト注入
    - 「提供された数字だけを使え、不明なら『記載なし』と書け」を強制

  is_hallucinated_number(value, allowed_values, tol_pct) → bool
    - 単一の数値が allowed_values のどれとも tol_pct 以内に収まらないか検査
"""
import re
from src.utils import setup_logger

logger = setup_logger("ai_guard")

# デフォルト許容誤差 (%)
_DEFAULT_TOL = 2.0

# AI テキストから数値を抽出する正規表現
# カンマ区切り整数（例: 38,000）、小数（例: 149.5）
# \b は日本語文字と数字の境界では機能しないので lookahead/lookbehind を使用
_NUM_RE = re.compile(r"(?<![,.\d])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+\.\d+)(?![,.\d])")

# 照合しない小さな数値（1〜999はほぼ一致不要なコンテキスト数値）
_SKIP_BELOW = 1000.0

# よくある「年」や「順位」などの誤検出を除外する閾値
_SKIP_YEAR_MIN, _SKIP_YEAR_MAX = 1900, 2100


def _parse_num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _is_skip_candidate(val: float) -> bool:
    """年号・ランク・小数例外など照合不要な値を除外"""
    if val < _SKIP_BELOW:
        return True
    if _SKIP_YEAR_MIN <= val <= _SKIP_YEAR_MAX:
        return True
    return False


def is_hallucinated_number(value: float, allowed_values: dict, tol_pct: float = _DEFAULT_TOL) -> bool:
    """
    value が allowed_values のどの値とも tol_pct% 以内にない → True（捏造の疑い）
    allowed_values: {"日経225": 38000.0, "S&P500": 5200.0, ...}
    """
    if _is_skip_candidate(value):
        return False
    for ref in allowed_values.values():
        if ref is None:
            continue
        try:
            ref = float(ref)
        except (TypeError, ValueError):
            continue
        if ref == 0:
            continue
        spread = abs(value - ref) / abs(ref) * 100
        if spread <= tol_pct:
            return False
    return True


def verify_against(text: str, allowed_values: dict,
                   tol_pct: float = _DEFAULT_TOL) -> tuple[str, list[float]]:
    """
    AI テキスト中の数値を allowed_values と照合する。
    返り値: (text_unchanged, suspect_values)
      - text は変更しない（ロギング・フラグ目的のみ）
      - suspect_values: 照合不能だった数値リスト
    """
    suspects = []
    for m in _NUM_RE.finditer(text):
        val = _parse_num(m.group(1))  # group(1) = capturing group
        if val is None:
            continue
        if is_hallucinated_number(val, allowed_values, tol_pct):
            suspects.append(val)

    if suspects:
        logger.warning(
            f"⚠️ AI捏造疑い: {len(suspects)}件の数値が実データと乖離 → {suspects[:5]}"
        )
    else:
        logger.debug("AI数値検証: 疑わしい数値なし")

    return text, suspects


def inject_guard_prompt(base_prompt: str, prices: dict) -> str:
    """
    Gemini プロンプトの冒頭に「数字ガード指示」を注入して返す。
    prices: fetch_prices の返り値（キーごとに latest 値を持つ dict）
    """
    data_lines = []
    for sym, d in (prices or {}).items():
        if not isinstance(d, dict):
            continue
        val = d.get("latest")
        name = d.get("name", sym)
        if val is not None:
            data_lines.append(f"  {name}({sym}): {val}")

    data_block = "\n".join(data_lines[:20]) if data_lines else "  （データなし）"

    guard = (
        "【重要ルール】以下の実データのみを数値として使用してください。\n"
        "データに存在しない株価・指標・数字を創作・推測して記述することを禁止します。\n"
        "不明な情報は「記載なし」または「確認できません」と書いてください。\n\n"
        f"【実データ一覧】\n{data_block}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    return guard + base_prompt


def build_allowed(prices: dict) -> dict:
    """prices から {名前: 値} の照合用辞書を生成するヘルパー"""
    allowed = {}
    for sym, d in (prices or {}).items():
        if isinstance(d, dict) and d.get("latest") is not None:
            name = d.get("name", sym)
            allowed[name] = d["latest"]
    return allowed


if __name__ == "__main__":
    # 自己テスト
    test_prices = {
        "^N225":    {"latest": 38000.0, "name": "日経225"},
        "^GSPC":    {"latest": 5200.0,  "name": "S&P500"},
        "USDJPY=X": {"latest": 149.5,   "name": "USD/JPY"},
    }
    allowed = build_allowed(test_prices)

    # 架空数字入り AI テキスト
    fake_text = "日経225は42,000円台を維持し、S&P500は5,200ポイントで推移。USD/JPYは149.50円。"
    _, suspects = verify_against(fake_text, allowed)
    print(f"suspects: {suspects}")  # 42000 が疑いとして検出されるはず

    # プロンプト注入テスト
    hardened = inject_guard_prompt("市場の状況を分析してください。", test_prices)
    print(hardened[:200])
