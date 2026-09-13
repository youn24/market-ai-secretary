# /improve-visuals

レポートやチャートの見た目を改善します。

改善したい箇所: $ARGUMENTS

改善できる対象：
- **HTMLレポート**: `cloud_run.py` の `_save_html_report()` 内のHTML/CSS
- **ダッシュボードチャート**: `src/visualize.py` の `chart_overview()`
- **週次カレンダー**: `src/economic_calendar.py` の `generate_calendar_image()`
- **テクニカルチャート**: `src/technical_ai.py` の `generate_chart()`
- **Telegram通知**: `src/notify_telegram.py` の `build_three_messages()`

ユーザーは投資初心者のため：
- 専門用語には必ず説明を添える
- 色は意味を持たせる（緑=上昇/良い、赤=下落/注意、黄=中立）
- 文字は大きく、数値は目立つように
- 「中学生でもわかる」を基準にする

変更後は必ずサンプルデータで動作確認してから提案すること。
