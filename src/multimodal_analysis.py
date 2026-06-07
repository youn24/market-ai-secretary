"""
マルチモーダル分析（L5d）
生成されたチャート画像をGemini Visionに送り、
「人間の目」でテクニカルパターンを読み取らせる。
数値だけではわからない視覚的パターン（ヘッド&ショルダー、ダブルトップ等）を検出。
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CHART_PROMPT = """あなたはプロのテクニカルアナリストです。
このチャート画像を分析して以下を特定してください。

1. **チャートパターン**: ヘッド&ショルダー、ダブルトップ/ボトム、トライアングル、フラッグ、ウェッジなど
2. **トレンド**: 上昇/下落/横ばい、トレンドの強さ
3. **サポート・レジスタンスライン**: 主要な価格水準
4. **視覚的シグナル**: 出来高パターン、ローソク足のパターン（あれば）
5. **総合評価**: 短期的な方向性（上昇/中立/下落）と確信度

回答は日本語で、以下の形式で200字以内に：
【パターン】（検出されたチャートパターン）
【トレンド】（現在のトレンド評価）
【重要価格帯】（サポート・レジスタンス）
【視覚的判断】（上昇/中立/下落 + 一言理由）"""


def _load_image_bytes(path: str) -> bytes | None:
    """画像ファイルをバイト列として読み込む"""
    try:
        p = Path(path)
        if not p.exists() or p.stat().st_size < 1000:
            return None
        with open(p, "rb") as f:
            return f.read()
    except Exception:
        return None


def _analyze_with_gemini(image_bytes: bytes, model) -> str:
    """GeminiにチャートイメージをVision分析させる"""
    try:
        # Gemini Python SDK でのマルチモーダル送信
        import google.generativeai.types as genai_types

        # PIL経由で試みる（より安定）
        try:
            import PIL.Image
            import io
            img = PIL.Image.open(io.BytesIO(image_bytes))
            response = model.generate_content([CHART_PROMPT, img])
            return response.text.strip()
        except ImportError:
            pass

        # PIL未インストールの場合はinline_data方式
        import base64
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        response = model.generate_content([
            {"text": CHART_PROMPT},
            {"inline_data": {"mime_type": "image/png", "data": b64}},
        ])
        return response.text.strip()

    except Exception as e:
        logger.warning(f"  Gemini Vision エラー: {e}")
        return ""


def _parse_visual_analysis(text: str) -> dict:
    """Geminiの回答からセクションを抽出"""
    result = {
        "pattern": "",
        "trend": "",
        "key_levels": "",
        "direction": "neutral",
        "full_text": text,
    }

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "パターン】" in line or "【パターン" in line:
            result["pattern"] = line.replace("【パターン】", "").replace("【パターン", "").strip("：:】")
        elif "トレンド】" in line or "【トレンド" in line:
            result["trend"] = line.replace("【トレンド】", "").replace("【トレンド", "").strip("：:】")
        elif "価格帯】" in line or "【重要" in line:
            result["key_levels"] = line.replace("【重要価格帯】", "").replace("【重要", "").strip("：:】")
        elif "視覚的判断】" in line or "【視覚" in line:
            visual = line.replace("【視覚的判断】", "").replace("【視覚", "").strip("：:】")
            if "上昇" in visual:
                result["direction"] = "bull"
            elif "下落" in visual:
                result["direction"] = "bear"
            else:
                result["direction"] = "neutral"

    # フォールバック: テキスト全体から方向性を推定
    if not result["pattern"] and text:
        if "上昇" in text[:100]:
            result["direction"] = "bull"
        elif "下落" in text[:100]:
            result["direction"] = "bear"

    return result


def run(chart_paths: dict, prices: dict, technical=None) -> dict:
    """チャート画像をGemini Visionで分析"""
    logger.info("--- マルチモーダル分析（チャートVision） ---")
    result = {"available": False}

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return result

    # 分析対象チャートを優先順位で選択
    priority_keys = ["overview", "technical", "prices", "sector"]
    target_path = None
    target_key = None

    for key in priority_keys:
        path = chart_paths.get(key, "")
        if path and Path(path).exists():
            target_path = str(path)
            target_key = key
            break

    if not target_path:
        logger.info("  分析対象チャートなし")
        return result

    logger.info(f"  分析対象: {target_key} ({target_path})")

    image_bytes = _load_image_bytes(target_path)
    if not image_bytes:
        logger.warning("  画像読み込み失敗")
        return result

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        # Vision対応のモデルを使用
        model = genai.GenerativeModel("gemini-1.5-flash")

        vision_text = _analyze_with_gemini(image_bytes, model)
        if not vision_text:
            return result

        parsed = _parse_visual_analysis(vision_text)

        # テクニカル分析（数値）との整合チェック
        agreement = None
        if technical and technical.get("available"):
            quant_direction = "neutral"
            for r in technical.get("results", []):
                rsi = r.get("rsi", 50)
                macd = r.get("macd_hist", 0)
                if rsi < 40 and macd < 0:
                    quant_direction = "bear"
                elif rsi > 60 and macd > 0:
                    quant_direction = "bull"
                break

            if parsed["direction"] == quant_direction and quant_direction != "neutral":
                agreement = "✅ 視覚とテクニカル指標が一致 → 信頼度高い"
            elif parsed["direction"] != "neutral" and quant_direction != "neutral" and parsed["direction"] != quant_direction:
                agreement = "⚠️ 視覚とテクニカル指標が乖離 → 要注意"

        result = {
            "available": True,
            "chart_key": target_key,
            "chart_path": target_path,
            "pattern": parsed.get("pattern", ""),
            "trend": parsed.get("trend", ""),
            "key_levels": parsed.get("key_levels", ""),
            "direction": parsed.get("direction", "neutral"),
            "full_analysis": vision_text,
            "quant_agreement": agreement,
        }

        dir_ja = {"bull": "上昇", "bear": "下落", "neutral": "中立"}
        logger.info(f"✅ Vision分析: {dir_ja.get(parsed['direction'], '---')} パターン={parsed.get('pattern','---')[:30]}")
        return result

    except Exception as e:
        logger.error(f"マルチモーダル分析エラー: {e}")
        return result


def format_telegram(data: dict) -> str:
    if not data.get("available"):
        return ""
    dir_icons = {"bull": "📈 上昇", "bear": "📉 下落", "neutral": "➡️ 中立"}
    lines = [
        "👁️ *AIチャート視覚分析（Vision）*",
        "━━━━━━━━━━━━━━━",
    ]
    if data.get("pattern"):
        lines.append(f"📐 パターン: {data['pattern']}")
    if data.get("trend"):
        lines.append(f"📊 トレンド: {data['trend']}")
    if data.get("key_levels"):
        lines.append(f"💰 重要価格帯: {data['key_levels']}")
    lines.append(f"🔍 視覚的判断: {dir_icons.get(data.get('direction','neutral'), '---')}")
    if data.get("quant_agreement"):
        lines += ["", data["quant_agreement"]]
    return "\n".join(lines)
