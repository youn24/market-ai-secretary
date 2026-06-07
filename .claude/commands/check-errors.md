# /check-errors

GitHub Actionsの最新ログを確認し、エラーがあれば原因と修正方法を教えてください。

以下の順番で確認してください：
1. `.github/workflows/daily_report.yml` のcron設定が正しいか
2. `logs/` フォルダ内の最新ログファイルを読む
3. `data/predictions.json` が正常に存在するか
4. エラーがあれば該当ファイルと行番号を特定して修正案を提示する

CLAUDE.mdの「過去に起きたバグ」セクションも参照して既知のパターンと照合してください。
