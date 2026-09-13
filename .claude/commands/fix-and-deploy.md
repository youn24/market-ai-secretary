# /fix-and-deploy

コードのエラーチェック → 修正 → GitHub push まで自動で行います。

## 実行順序（この順番を守る）

### Phase 1: GitHub Actionsのログ確認
```
gh run list --repo youn24/market-ai-secretary --limit 5
```
失敗しているrunがあれば：
```
gh run view <RUN_ID> --repo youn24/market-ai-secretary --log-failed
```
`CLAUDE.md` の「過去に起きたバグ」セクションと照合して既知パターンか確認。

### Phase 2: Pythonの構文チェック
```
cd C:\Users\中田　洋介\Desktop\tousijouhou\market-ai-secretary
python -m py_compile cloud_run.py && echo OK: cloud_run.py
python -m py_compile src/sector_analysis.py && echo OK: sector_analysis.py
python -m py_compile src/prediction_tracker.py && echo OK: prediction_tracker.py
python -m py_compile src/notify_telegram.py && echo OK: notify_telegram.py
python -m py_compile src/visualize.py && echo OK: visualize.py
```

### Phase 3: よくあるエラーのチェック
```
grep -rn "%-m" src/
grep -rn "axhline.*transform" src/
```

既知の修正パターン：

| エラー | 修正 |
|--------|------|
| `Invalid format string %-m` | `%-m` → `%m` に変更 |
| `UnboundLocalError: get_jst_now` | 関数内のimportをモジュール先頭に移動 |
| `axhline transform not allowed` | `ax.plot([0,1],[y,y], transform=...)` に変更 |

### Phase 4: 修正適用の前に必ず確認
- `CLAUDE.md` の「絶対に守るルール」6項目を確認
- 免責表示・投資助言の文言を追加していないか？
- `data/predictions.json` を gitignore に入れていないか？

### Phase 5: コミット & プッシュ
```
git add <修正したファイル>
git commit -m "fix: [内容を日本語で]"
git push origin main
```

### Phase 6: 結果報告（このフォーマットで）
```
🔧 修正 & デプロイ完了
━━━━━━━━━━━━━━━
❌ 発見したエラー: [内容 or なし]
✅ 修正したファイル: [ファイル名 or なし]
📤 プッシュ: [完了 or スキップ]
💡 今後の注意点: [アドバイス]
```

### 安全ルール
- `git push --force` は絶対にしない
- エラーがない場合はプッシュしない
- 大きな変更はユーザーに確認してから行う
