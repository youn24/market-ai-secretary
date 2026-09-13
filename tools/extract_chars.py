"""
会話ファイルからキャラクター画像を抽出するスクリプト
"""
import json, base64, re, os, sys

JSONL = r"C:\Users\中田　洋介\.claude\projects\C--Users-------Desktop-tousijouhou\48d773cc-d01e-4bd0-9967-b4ddbf6bd725.jsonl"
OUT   = r"C:\Users\中田　洋介\Desktop\tousijouhou\market-ai-secretary\src\assets\characters.png"

with open(JSONL, "r", encoding="utf-8") as f:
    content = f.read()

pattern = r'"data":\s*"(iVBOR[^"]{100,})'
matches = re.findall(pattern, content)
print(f"Found {len(matches)} PNG images")

# サイズ別に全部確認
sized = []
for m in matches:
    full = m + "=" * (4 - len(m) % 4)
    try:
        img = base64.b64decode(full)
        sized.append((len(img), img))
    except:
        pass

sized.sort(reverse=True)
for i, (sz, img) in enumerate(sized[:5]):
    print(f"  [{i}] {sz/1024:.0f}KB")

# 最大サイズ（複数キャラが写っている大きな画像）
if sized:
    best_img = sized[0][1]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(best_img)
    print(f"Saved largest ({sized[0][0]/1024:.0f}KB) -> {OUT}")
else:
    print("No images found!")
