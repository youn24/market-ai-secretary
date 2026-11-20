# -*- coding: utf-8 -*-
"""レポートが引いているニュースの label が、設定に実在するかを調べる。

    python -m scripts.check_news_labels

⚠️ なぜ要るか。`src/feed_card.py` の区画（注目の企業とテーマ／世界の政治と
   お金／報道が挙げている理由）は、`config/news_sources.yaml` の `label`
   （「💻 AI・半導体」など）でニュースを引いている。
   yaml の表示名を1文字変えると、**例外にならずその区画が丸ごと空になる。**
   この案件は「静かに消える」事故を10件以上繰り返しているので、
   実行して確かめるのではなく、ここで機械的に突き合わせる。

   絵文字を含む文字列の一致なので、目で見比べても気づけない
   （見た目が同じで符号が違う絵文字がある）。
"""
import io
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
YAML = ROOT / "config" / "news_sources.yaml"


def main() -> int:
    # ⚠️ Windowsの既定(cp932)では絵文字を印字できず、**合格の行だけで落ちる**。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    cfg = yaml.safe_load(io.open(YAML, encoding="utf-8"))
    known = {str(k.get("label") or "") for k in cfg.get("google_news_keywords", [])}
    known.discard("")

    sys.path.insert(0, str(ROOT))
    from src import feed_card as fc

    used = {}            # label -> それを使っている区画の名前
    for gname, groups in (("注目の企業とテーマ", fc._THEME_GROUPS),
                          ("世界の政治とお金", fc._GEO_GROUPS)):
        for _k, title, labels, _hint in groups:
            for lb in labels:
                used.setdefault(lb, []).append(f"{gname}／{title}")
    for lb in fc._WHY_LABELS:
        used.setdefault(lb, []).append("報道が挙げている理由")

    missing = {lb: w for lb, w in used.items() if lb not in known}

    print(f"── 設定にある label: {len(known)}個 ／ レポートが引く label: {len(used)}個")
    if missing:
        print(f"\n❌ 設定に無い label を引いています（その区画は空になります）")
        for lb, where in sorted(missing.items()):
            print(f"   「{lb}」 ← {'、'.join(where)}")
        print("\nconfig/news_sources.yaml の label と綴りを揃えてください。")
        return 1

    unused = sorted(known - set(used))
    if unused:
        print(f"\n（レポートのどの区画にも出していない label: {len(unused)}個）")
        for lb in unused:
            print(f"   {lb}")
        print("   ※ 取るだけ取って捨てている話題です。意図していなければ繋いでください。")

    print(f"\n✅ 引いている{len(used)}個すべて設定に実在します")
    return 0


if __name__ == "__main__":
    sys.exit(main())
