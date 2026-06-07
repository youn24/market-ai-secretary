# /deploy

変更をGitHubにプッシュしてGitHub Actionsを確認します。

以下の手順で実行してください：
1. `git status` で変更ファイルを確認
2. シンタックスチェック（変更したPythonファイルすべて）:
   ```
   python -c "import ast; ast.parse(open('cloud_run.py',encoding='utf-8').read()); print('OK')"
   ```
3. 変更内容を要約してコミットメッセージを作成
4. `git add` → `git commit` → `git push origin main`
5. プッシュ後、GitHub Actionsページ（https://github.com/youn24/market-ai-secretary/actions）で確認方法を案内

⚠️ CLAUDE.mdの「絶対に守るルール」を必ず事前確認してからコミットすること。
