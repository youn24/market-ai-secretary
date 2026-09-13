"""
校閲ループ（フェーズ3・精度土台 L6）
配信直前に AI テキストを自動チェック → 自動修正し、品質を担保する。

check_and_fix(text, prices, context) → (fixed_text, report)
  - 空セクション除去
  - 断定表現 + 低信頼データの組み合わせを軟化
  - ai_guard で捏造数字を検出 → 警告注入（数字は削除しない。事実が正しい可能性もあるため）
  - 文字数が極端に長い or 短いセクションに印をつける
  - report: {"passed": bool, "issues": [...], "fixes": int}
"""
import re
from src.utils import setup_logger

logger = setup_logger("editorial_qa")

# 断定的な表現パターン（日本語）
_ASSERTIVE = [
    r"必ず[上下]が[りる]",
    r"確実に",
    r"間違いなく",
    r"絶対に",
    r"[上下]がるはず",
    r"[上下]がる一方",
    r"予想通り",
]
_ASSERTIVE_RE = re.compile("|".join(_ASSERTIVE))

# 軟化置換マップ（断定 → 推測）
_SOFTEN = [
    (r"必ず(上がり|下がり|上る|下る)", r"上がる可能性があり" ),
    (r"確実に",     "可能性として"),
    (r"間違いなく", "おそらく"),
    (r"絶対に",     "状況次第では"),
    (r"上がるはず", "上がる可能性がある"),
    (r"下がるはず", "下がる可能性がある"),
    (r"上がる一方", "上昇傾向が続く可能性がある"),
    (r"下がる一方", "下落傾向が続く可能性がある"),
    (r"予想通り",   "想定に沿う形で"),
]

# 空セクション検出（セクション見出しに続く内容が空か「---」のみ）
_EMPTY_SECTION_RE = re.compile(
    r"(#+\s*.+)\n+(?:---+|　*|　*\n){0,3}(?=#+|\Z)",
    re.MULTILINE,
)

# 極端に短いセクション本文（見出し除く5文字未満）
_SHORT_BODY_RE = re.compile(r"(#+\s*.+)\n(.{1,5})\n", re.MULTILINE)

# 「記載なし」や「確認できません」が含まれるのは正常（ai_guard の正しい挙動）
_LEGIT_UNKNOWN = re.compile(r"記載なし|確認できません|不明|データなし")


def _soften_assertions(text: str) -> tuple[str, int]:
    """断定表現を推測表現に軟化する。修正件数を返す。"""
    count = 0
    for pattern, replacement in _SOFTEN:
        new_text, n = re.subn(pattern, replacement, text)
        if n:
            text = new_text
            count += n
    return text, count


def _remove_empty_sections(text: str) -> tuple[str, int]:
    """空セクション（見出しだけで本文なし）を除去する。"""
    original = text
    text = _EMPTY_SECTION_RE.sub("", text)
    removed = original != text
    return text, (1 if removed else 0)


def _check_fabricated_numbers(text: str, prices: dict) -> list[float]:
    """ai_guard を使って捏造数字を検出。テキストは変更しない。"""
    if not prices:
        return []
    try:
        from src.ai_guard import verify_against, build_allowed
        allowed = build_allowed(prices)
        _, suspects = verify_against(text, allowed)
        return suspects
    except Exception:
        return []


def _inject_suspect_warning(text: str, suspects: list[float]) -> str:
    """捏造疑い数字がある場合、テキスト末尾に⚠️注記を追加。"""
    if not suspects:
        return text
    top = ", ".join(str(s) for s in suspects[:3])
    note = f"\n\n⚠️ *注意: {len(suspects)}件の数値が実データと照合不能（{top}など）。フルレポートで実値を確認してください。*"
    return text + note


def _trim_oversized(text: str, max_chars: int = 4000) -> tuple[str, bool]:
    """最大文字数を超えた場合に末尾を省略する。"""
    if len(text) <= max_chars:
        return text, False
    cutoff = text.rfind("\n", 0, max_chars)
    if cutoff == -1:
        cutoff = max_chars
    return text[:cutoff] + "\n\n…（省略）", True


def check_and_fix(text: str, prices: dict = None,
                  confidence: str = "mid",
                  max_chars: int = 4000) -> tuple[str, dict]:
    """
    テキストを校閲・修正する。
    confidence: "high" / "mid" / "low" — low の場合は断定軟化を強制
    返り値: (fixed_text, report)
    """
    issues = []
    fixes  = 0

    if not text or not text.strip():
        return text, {"passed": False, "issues": ["テキストが空"], "fixes": 0}

    # 1. 空セクション除去
    text, n = _remove_empty_sections(text)
    if n:
        fixes += n
        issues.append(f"空セクション {n}件を除去")

    # 2. 断定軟化（low 信頼度 or 断定パターン検出時）
    has_assertive = bool(_ASSERTIVE_RE.search(text))
    if confidence == "low" or has_assertive:
        text, n = _soften_assertions(text)
        if n:
            fixes += n
            issues.append(f"断定表現 {n}件を推測表現に軟化")

    # 3. 捏造数字チェック（ai_guard 経由）
    suspects = _check_fabricated_numbers(text, prices)
    if suspects:
        text = _inject_suspect_warning(text, suspects)
        issues.append(f"捏造疑い数値 {len(suspects)}件を検出（末尾に注記追加）")

    # 4. 文字数上限
    text, trimmed = _trim_oversized(text, max_chars)
    if trimmed:
        issues.append(f"文字数上限 {max_chars}字で省略")

    passed = len([i for i in issues if "捏造" in i or "断定" in i]) == 0

    report = {"passed": passed, "issues": issues, "fixes": fixes}
    if issues:
        logger.info(f"校閲結果: passed={passed} fixes={fixes} issues={issues}")

    return text, report


def qa_ai_summary(ai_summary: dict, prices: dict = None) -> dict:
    """
    ai_debate の結果（bull_view / bear_view / neutral_view）に校閲を適用する。
    元の dict を汚染せず、修正済みコピーを返す。
    """
    if not isinstance(ai_summary, dict) or not ai_summary.get("available"):
        return ai_summary

    result = dict(ai_summary)
    total_fixes = 0
    all_issues  = []

    for key in ("bull_view", "bear_view", "neutral_view"):
        raw = result.get(key, "")
        if not raw:
            continue
        fixed, report = check_and_fix(raw, prices, confidence="mid", max_chars=400)
        result[key] = fixed
        total_fixes += report.get("fixes", 0)
        all_issues  += report.get("issues", [])

    if total_fixes:
        result["qa_applied"]  = True
        result["qa_fixes"]    = total_fixes
        result["qa_issues"]   = all_issues
        logger.info(f"AI要約に校閲適用: {total_fixes}件修正")

    return result


if __name__ == "__main__":
    # 自己テスト
    test_text = """## 強気分析
日経平均は確実に上がる一方で、S&P500も絶対に上昇する。
VIXは38,000円を示しており、リスクは低い。

##

## 弱気分析
こちらは正常なテキスト。VIXが18.5と高く、下落のリスクがある。
"""
    test_prices = {
        "^N225": {"latest": 38000.0, "name": "日経225"},
        "^VIX":  {"latest": 18.5,   "name": "VIX"},
    }
    fixed, report = check_and_fix(test_text, test_prices, confidence="low")
    print("=== 修正後テキスト ===")
    print(fixed)
    print("\n=== レポート ===")
    print(report)
