# /add-indicator

新しい経済指標や価格シンボルをシステムに追加します。

追加したいシンボルまたは指標名: $ARGUMENTS

以下の手順で追加してください：
1. `config/symbols.yaml` にシンボルを追加
2. `src/fetch_prices.py` で取得対象に含める
3. `cloud_run.py` の HTMLレポート部分（big_card）に表示追加
4. `src/notify_telegram.py` の通知に含めるか判断
5. 変更後にシンタックスチェック: `python -c "import ast; ast.parse(open('cloud_run.py').read())"`

CLAUDE.mdの「新しい分析モジュールを追加するとき」のパターンを参照してください。
