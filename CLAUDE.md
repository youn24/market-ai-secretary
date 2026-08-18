# 市場AI秘書 — CLAUDE.md（プロジェクト指示書）

このファイルはClaude Codeが自動で読み込み、プロジェクトの文脈を理解するための指示書です。

---

## 🎯 プロジェクト概要

**名前**: 市場AI秘書  
**オーナー**: 中田 洋介（投資初心者）  
**目的**: PC電源OFFでもGitHub Actionsが毎朝自動実行し、市場分析レポートをTelegramとGitHub PagesのHTMLで配信する  
**GitHub**: https://github.com/youn24/market-ai-secretary  
**レポートURL**: https://youn24.github.io/market-ai-secretary  

---

## 🏗 アーキテクチャ

```
GitHub Actions（毎朝7:30 JST）
    ↓
cloud_run.py（メインスクリプト）
    ├── Step 1:     src/fetch_prices.py          → yfinanceで価格取得
    ├── Step 1.5:   src/data_integrity.py        → データ健全性チェック（異常値検出）
    ├── Step 2:     src/fetch_news.py            → Google News RSS取得
    ├── Step 3:     src/fetch_extra_news.py      → 追加ニュース
    ├── Step 4:     src/indicators.py            → リスクスコア計算
    ├── Step 5:     src/analyze.py               → 基本分析
    ├── Step 5b:    src/ai_debate.py             → AI3視点議論（強気/弱気/中立）
    ├── Step 5c:    src/economic_indicators.py   → 経済指標分析
    ├── Step 5d:    src/youtube_summary.py       → YouTube動画要約
    ├── Step L3a:   src/ai_agent.py             → 自律AIエージェント（Gemini Function Calling）
    ├── Step L3b:   src/technical_ai.py         → テクニカル分析（RSI/MACD/BB）
    ├── Step L3b2:  src/setup_scanner.py        → 手法シグナル・スキャナー（押し目/ブレイク等）
    ├── Step L3c:   src/portfolio.py            → ポートフォリオ管理
    ├── Step L3d:   src/scenario.py             → 3シナリオ分析（楽観/基本/悲観）
    ├── Step L3e:   src/prediction_tracker.py   → 予測学習・正解率記録
    ├── Step L4a:   src/sector_analysis.py      → セクター分析・ローテーション
    │               src/sector_chart.py         → セクターヒートマップ画像
    ├── Step L4a2:  src/sector_ranking_jp.py    → 日本業種別ランキング（TOPIX-17 ETF）
    ├── Step L4b:   src/historical_analysis.py  → 長期歴史データ分析（20年分）
    ├── Step L4c:   src/fred_data.py            → FRED経済指標（GDP/CPI/FF金利等）
    ├── Step L4d:   src/correlation_analysis.py → 資産間相関分析
    ├── Step L4e:   src/backtest.py             → バックテスト（月曜のみ）
    ├── Step L4f:   src/sentiment_data.py       → センチメントデータ（P/C比率等）
    ├── Step L4h:   src/monte_carlo.py          → モンテカルロ+マーコウィッツ（月曜のみ）
    ├── Step L4i:   src/fomc_sentiment.py       → FOMC議事録NLP分析（月曜のみ）
    ├── Step L4j:   src/congress_trading.py     → 米議員株取引（月曜のみ）
    ├── Step L5e:   src/self_critique.py        → 自己批判エンジン（過去予測の反省）
    ├── Step L5f:   src/reddit_sentiment.py     → Redditソーシャル感情分析
    ├── Step L5g:   src/earnings_preview.py     → 決算前AI事前分析
    ├── Step L5h:   src/market_chain.py         → グローバル市場連鎖分析
    ├── Step L5j:   src/jquants_screener.py     → J-Quants日本株スクリーナー（月曜のみ）
    ├── Step L5a:   src/multi_agent_consensus.py → 4AIエージェント多数決合議
    ├── Step L5a.5: update_confidence()         → 合議確信度を予測レコードへ書き戻し
    ├── Step L5a.6: src/cross_check.py          → 情報源クロスチェック（方向一致度）
    ├── Step L5b:   src/autonomous_orchestrator.py → 完全自律エージェント（今日のミッション決定）
    ├── Step L5c:   src/reinforcement_learning.py → 強化学習ループ（ML予測・パターン学習）
    ├── Step 5f:    src/economic_calendar.py    → 週次カレンダー（月曜のみ）
    ├── Step 5e:    src/ai_memory.py            → AI記憶更新・継続分析
    ├── Step 6:     src/visualize.py            → matplotlibチャート生成
    ├── Step CHR:   src/character_commentary.py → AIキャラクターコメント（ガネーシャ&カワウソ）
    ├── Step L5d:   src/multimodal_analysis.py  → チャート画像Gemini Vision分析（Step6後）
    ├── Step L5i:   src/notify_line.py          → LINE通知（Telegramと並行送信）
    ├── Step MA:    src/macro_summary.py        → マクロ要約（ファンダ＋金融政策）
    ├── Step TD:    src/tdnet_watcher.py        → TDnet適時開示ウォッチャー
    ├── Step EB:    src/earnings_brief.py       → 決算ブリーフ（PDF AI要約）
    ├── Step CA:    src/catalyst_analyzer.py    → 材料分析AI（5軸評価＋デイトレ仮説）
    ├── Step AN:    src/anomaly_calendar.py     → アノマリーカレンダー
    ├── Step TR:    src/theme_ranker.py         → テーマ株人気ランキング
    ├── Step FA:    src/financial_analyzer.py   → 財務・決算書分析（月曜のみ）
    ├── Step SD:    src/supply_demand.py        → 需給分析ランキング（月曜のみ）
    ├── Step KY:    src/kabuyoho.py             → 株予報（アナリスト目標株価・月曜のみ）
    ├── Step SH:    src/sector_heatmap.py       → 業種ヒートマップ
    ├── Step ND:    src/nikkei_market_data.py   → 日経225内部データ（騰落レシオ/空売り/ADR）
    ├── Step ADR:   src/adr_data.py             → 日本株ADR（夜間NYの値動き）
    ├── Step 7:     cloud_run._save_html_report() → HTMLレポート生成（バックアップ版）
    ├── Step 7a2:   src/design_ai.py           → デザインAIレポート（docs/daily_report.html 公開メイン版）
    ├── Step 7b:    src/note_article.py        → note記事生成
    ├── Step 7c:    src/note_cover.py          → noteカバー画像生成
    ├── Step 8:     src/notify_telegram.py     → Telegram通知送信
    ├── Step 8b:    src/note_article_generator.py → note記事テキスト自動生成
    └── Step 8d:    src/notify_x.py           → X（Twitter）自動投稿
```

---

## 📁 重要ファイル一覧

### メインスクリプト
| ファイル | 役割 |
|---------|------|
| `cloud_run.py` | GitHub Actions用メイン実行スクリプト |
| `weekly_run.py` | 日曜週次レポート用スクリプト |
| `monitor_run.py` | 15分ごと急変アラート用スクリプト |
| `fx_noon_run.py` | FX午後レポート（14:00 JST）実行スクリプト |

### srcモジュール（各Stepの実体）
| ファイル | 役割 |
|---------|------|
| `src/utils.py` | 共通ユーティリティ（JST時刻、ディレクトリ管理等） |
| `src/fetch_prices.py` | yfinanceで価格・Fear&Greed取得 |
| `src/fetch_news.py` | Google News RSS + config/news_sources.yaml |
| `src/data_integrity.py` | 価格データ健全性チェック（外れ値・欠損検出） |
| `src/indicators.py` | リスクスコア算出 |
| `src/ai_debate.py` | Gemini 3視点AIディベート（強気・弱気・中立） |
| `src/ai_agent.py` | Gemini Function Calling 自律エージェント |
| `src/technical_ai.py` | RSI/MACD/ボリンジャーバンド計算 |
| `src/setup_scanner.py` | 手法シグナル・スキャナー（押し目買い/ブレイクアウト等） |
| `src/portfolio.py` | ポートフォリオ損益管理 |
| `src/scenario.py` | 楽観/基本/悲観シナリオ生成 |
| `src/prediction_tracker.py` | 予測記録→翌日検証→正解率→Geminiフィードバック |
| `src/ai_memory.py` | 過去データを記憶・継続比較分析 |
| `src/historical_analysis.py` | 長期歴史データ分析（Yahoo Finance API直接取得・20年分） |
| `src/cross_check.py` | 複数手法の方向一致度クロスチェック（信頼度スコア） |
| `src/economic_calendar.py` | 週次経済カレンダー画像生成（月曜のみ） |
| `src/character_commentary.py` | AIキャラクターコメント（ガネーシャ＆カワウソ） |
| `src/design_ai.py` | 公開用リッチHTMLレポート（docs/daily_report.html メイン着地ページ） |
| `src/visualize.py` | matplotlibダッシュボード画像生成 |
| `src/notify_telegram.py` | Telegram Bot通知送信 |
| `src/notify_line.py` | LINE通知（Telegramと並行送信） |
| `src/notify_x.py` | X（Twitter）自動投稿 |
| `src/macro_summary.py` | マクロ要約（ファンダメンタルズ＋金融政策） |
| `src/tdnet_watcher.py` | TDnet適時開示ウォッチャー（ウォッチリスト銘柄） |
| `src/earnings_brief.py` | 決算PDFのGemini AI要約 |
| `src/catalyst_analyzer.py` | 材料分析AI（5軸評価＋デイトレ仮説） |
| `src/anomaly_calendar.py` | アノマリーカレンダー（経験則・季節性） |
| `src/theme_ranker.py` | テーマ株人気ランキング |
| `src/financial_analyzer.py` | 財務・決算書分析（月曜のみ） |
| `src/supply_demand.py` | 需給分析ランキング（出来高/資金フロー/空売り残） |
| `src/kabuyoho.py` | 株予報（アナリスト目標株価・月曜のみ） |
| `src/sector_heatmap.py` | 業種別ヒートマップ生成 |
| `src/nikkei_market_data.py` | 日経225内部データ（騰落レシオ/空売り比率/ADR等） |
| `src/adr_data.py` | 日本株ADRデータ（夜間NYの値動き・寄り付き先行ヒント） |
| `src/backtest_predictions.py` | 予測ロジックの過去検証（470件生成）＋信頼度表の再較正 |
| `src/failure_analysis.py` | 予測のクセ分析（強さ別・環境別の勝率、ギャップ分解、連敗分布） |
| `src/signal_confidence.py` | 信頼度ランク（S/A/B/C）。`config/confidence_tiers.json` を読む |
| `src/publish_check.py` | 公開ページをHTTPで外から点検（毎朝8:30・異常時のみTelegram通知＋exit 1） |
| `src/risk_gauges.py` | リスク計器盤（恐怖指数10種・日米金利・ドル指数・暗号資産F&G。統計しきい値で大きな動きを検知） |
| `src/fx_signals.py` | 為替シグナル（8通貨ペア・強いサイン3つ以上一致でFX専用グループへ通知） |
| `scripts/lint_workflows.py` | ワークフローの「静かに壊れる書き方」を機械検出。`# lint:allow-fail 理由` で除外可 |
| `src/note_article.py` | note記事生成（Step 7b） |
| `src/note_article_generator.py` | note記事テキスト自動生成（Step 8b） |
| `src/fx_visual_report.py` | FX専用ビジュアルダッシュボード（13パネル・matplotlib） |

### 設定・データ
| ファイル | 役割 |
|---------|------|
| `config/news_sources.yaml` | ニュースキーワード25件（カテゴリ別10分類） |
| `config/symbols.yaml` | 取得シンボル設定 |
| `data/predictions.json` | AI予測学習データ（永続化・Gitコミット対象） |
| `data/ai_memory.json` | AI記憶データ（永続化・Gitコミット対象） |
| `data/portfolio.json` | ポートフォリオ保有情報 |

### GitHub Actions ワークフロー
| ファイル | タイミング |
|---------|-----------|
| `.github/workflows/daily_report.yml` | UTC 22:30 = JST 7:30（平日月〜金） |
| `.github/workflows/weekly_report.yml` | UTC 23:00 土曜 = JST 8:00 日曜 |
| `.github/workflows/monitor.yml` | 平日15分ごと急変アラート |
| `.github/workflows/fx_noon.yml` | UTC 05:00 = JST 14:00（毎日・FX専用午後レポート） |
| `.github/workflows/health_check.yml` | UTC 23:30 = JST 8:30（平日）＋ワークフロー変更時の自動検査 |

---

## 🔑 必須環境変数（GitHub Secrets）

```
GEMINI_API_KEY      → Google AI Studio で発行（無料枠あり）
GEMINI_MODEL        → 使用モデルを一元管理（任意・未設定なら gemini-2.5-flash）
                      ※全モジュール共通。レート制限時は gemini-2.0-flash に変更すれば一括切替
CF_PROXY_URL        → 業種別ランキングのザラ場リアルタイム更新用CORSプロキシ（任意）
                      ※Cloudflare WorkerのURL。未設定なら朝の値を表示。SETUP_CLOUDFLARE.md参照
TELEGRAM_BOT_TOKEN  → @BotFather で発行
TELEGRAM_CHAT_ID    → 8958569711
GITHUB_PAGES_URL    → https://youn24.github.io/market-ai-secretary
```

---

## ⚠️ 絶対に守るルール（変更禁止事項）

1. **「投資助言ではありません」などの免責表示を追加しない**
   → オーナーが明示的に不要と指定済み

2. **cloud_run.py の Step 番号順序を崩さない**
   → 依存関係があるため（例: prices → risk → ai_summary → prediction_tracker の順が必須）

3. **`get_jst_now` を関数内でimportしない**
   → `from src.utils import get_jst_now` はモジュール先頭のみ（局所importするとUnboundLocalError発生）

4. **Telegram通知は「1日3通」を維持**（2026-08-03 オーナー判断で2通＋動画から変更）
   → 朝 7:30  : `cloud_run.py` → サマリーカード画像＋寄り付き前チェックのキャプション
                ＋「フルレポートを開く」インラインボタン。**必ず1通に収める**
   → 昼 14:00 : `fx_noon_run.py` → FX統合カード＋キャプション＋ボタン。**1通**
   → 夜 23:00 : `evening_run.py` → 夜の振り返り。**1通**
   → この3通以外の定期通知は追加しない（週次レポート・急変アラートは別扱い）
   → 朝の詳細（3シナリオ/4AI合議/セクター/株ドラゴン/銘柄カルテ等）は
      Telegramに並べず `design_ai.py` の公開レポート側へ集約し、ボタンで誘導する
   → 停止中: 前場12:00・引け後15:30（`intraday_alerts.yml` の cron をコメントアウト）、
      要約ナレーション動画（`video_summary.py` は生成のみ・送信しない）。
      どちらも機能は残置。戻す場合はオーナーの明示的な指示があるときだけ

5. **`data/predictions.json`, `data/ai_memory.json` をgitignoreに入れない**
   → 予測学習データの永続化に必須

6. **GitHub Actions でmatplotlibを使う場合は必ず `matplotlib.use("Agg")` を先頭に**
   → 非GUIバックエンドが必要

---

## ✅ よくある作業パターン

### 新しい分析モジュールを追加するとき
```python
# cloud_run.py のパターンに従う
new_module = {"available": False}
try:
    logger.info("--- Step XX: 新モジュール ---")
    from src.new_module import run as run_new
    new_module = run_new(prices, risk, fear_greed)
    if new_module.get("available"):
        logger.info("✅ 新モジュール完了")
except Exception:
    logger.error("新モジュールエラー"); logger.debug(traceback.format_exc())
```

### Gemini APIを呼ぶときの標準パターン
```python
api_key = os.getenv("GEMINI_API_KEY", "").strip()
if not api_key:
    return {"available": False}
import google.generativeai as genai
genai.configure(api_key=api_key)
# モデルは環境変数 GEMINI_MODEL で一元管理（既定 gemini-2.5-flash）。直接 "gemini-1.5-flash" 等とハードコードしない
model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
response = model.generate_content(prompt)
```

### Telegram通知を追加するとき
```python
# src/notify_telegram.py の run() 関数に引数追加
# → 既存の3メッセージは必ず送り、追加メッセージはその後に append
```

### HTMLレポートにセクションを追加するとき
```python
# cloud_run.py の _save_html_report() で
# 1. 引数追加
# 2. HTML変数生成（pred_html等）
# 3. html文字列内の適切な位置にf-string追加
```

---

## 🐛 過去に起きたバグと対処法

| バグ | 原因 | 対処 |
|------|------|------|
| `UnboundLocalError: get_jst_now` | 関数内で局所import | モジュール先頭のimportのみ使う |
| `Invalid format string %-m` | Windows非対応の日付フォーマット | `%m` を使う（`%-m` はLinux専用） |
| `axhline transform not allowed` | matplotlibバージョン差 | `ax.plot([0,1],[y,y])` に変更 |
| `feedparser not found` | monitor.ymlにpip install漏れ | workflow全ファイルのpip installを統一 |
| 日本語フォント文字化け | ローカルWindowsにフォントなし | GitHub Actionsでは`fonts-noto-cjk`が解決 |
| `Step 8d` のloggerに `Step 8b` と表示される | logger.infoのStep番号の書き間違い | 2026-07-01修正済み（"Step 8d: X自動投稿"に統一） |
| 予測正解率が23%まで低下 | `_extract_direction()`の強気バイアス（スコアが高くても bull を出しやすい） | 2026-06-28にバイアス是正コミット済み（推定改善後39%） |
| Telegram通知停止（2026-06） | GitHub SecretのBot token失効＋iPhoneのプッシュ通知オフ | verify_bot()等で恒久対策済み。再発時はSecretの有効期限を確認 |
| 予測正解率が26.3%(5/19)に再低下（2026-07-12時点） | bull閾値6.0でも強気過多継続（bull的中率20%、予測分布bull53%が実際26%を大幅超過）、シナリオ差分25%オーバーライドが低スコア(2.5点)でもbullに上書き | 2026-07-12: bull閾値9.0・bear閾値-3.0・シナリオ差分30%に再調整、git push済み |
| **公開レポートが1.5ヶ月更新されず（2026-06-26で停止・8/11発覚）** | design_ai.run()が例外を`logger.debug`で握りつぶし、cloud_run Step 7a2も戻り値を確認せず「✅生成」と無条件でログ出力。Actionsは緑・ログも成功表示のため誰も気づけなかった。自動コミットにも daily_report.html が一度も含まれていなかった | 2026-08-11修正: ①例外を`logger.error`で型とメッセージごと出力 ②生成後にファイル実在とサイズ(5KB未満は不完全)を検証 ③cloud_run側で「本日の日付が含まれるか」を確認 ④workflowに検証ステップ追加（古ければ`::error::`） |

| **公開レポートが1週間更新されず（2026-08-18発覚）** | `git add docs data/A.json data/B.json ...` の形で複数パスを一度に渡していた。git add は**存在しないパスが1つでもあるとエラー終了し、何もステージしない**。状態ファイル(policy_state等)はgitignore対象で毎回チェックアウトされず、モジュール未生成なら存在しない。その1つのせいで docs/ ごと巻き添えになり、毎日「変更なし」でコミットされなかった。`2>/dev/null \|\| true` が出力もexit codeも消していたため完全に無音 | ①docsは単独add、状態ファイルは`[ -f ]`で1つずつ ②ステージが空なら`::error::` ③状態ファイルを.gitignoreでホワイトリスト化（重複防止台帳が毎回リセットされる問題も同時に解消） ④`scripts/lint_workflows.py`で同型を機械検出 ⑤`src/publish_check.py`で公開ページを外から実地点検 |

### ⚠️ この事故から得た原則（新規実装時に必ず守る）
**「成功ログを無条件で出さない」** — 戻り値と生成物を検証してから成功と報告する。
`try/except`で握りつぶす場合も、例外の内容は必ず`logger.error`で残す
（`logger.debug`は本番ログに出ないため、事実上の握りつぶしになる）。
外部に公開・配信される成果物（HTML・通知・画像）は、生成後に
「実在するか」「中身が今日のものか」まで確認する。

**「生成できた」と「利用者に届いた」は別物** — 2026-08-18の事故は、
生成物はすべて正しいのに公開サイトへ届いていない、という形だった。
リポジトリ内のファイルを見る点検はすべて正常と判定し、1週間気づけなかった。
最終確認は必ず**外からHTTPで実物を取りに行く**こと（`src/publish_check.py`）。

**`git add` に複数パスを一度に渡さない** — 存在しないパスが1つでもあると
git add はエラー終了し、他の正しいパスも含めて何もステージしない。
必ず `[ -f "$f" ]` で確認して1つずつ add する。

**点検の例外を `logger.debug` で捨てない** — 点検自体が死んでいることに
気づけなくなり、事故そのものと同じ構図になる。

---

## 📈 定期精度チェック記録

### 2026-07-20 チェック（07-12修正の効果測定）
- 全期間: 34.8%(8/23) ／ 直近30日: 40.0%(6/15) ／ 直近10日: 75.0%(3/4)
- 全期間・30日の低さは07-12修正**前**の強気過多期間（bull的中率20%）に引きずられている数字。07-12修正**後**の検証済み予測は4件のみ（07-13〜07-16）で3勝1敗＝75%。
- 注目点: 07-12の閾値引き上げ（bull 9.0）以降、bullシグナルが一度も発火していない（スコアが届いていない＝相場がbear/neutral寄りで推移）。そのためbull判定の改善効果はまだ未検証。
- 判断: サンプル数(n=4)が少なすぎるため、_extract_direction()への追加の閾値変更は見送り（n=4での再調整は過学習のリスクが高い）。来週以降、bullシグナルが発火した際の的中率を優先的に確認する。
- 弱気(bear)判定は全期間57.1%(4/7)と相対的に安定。中立判定は33.3%(2/6)、強気判定は20.0%(2/10)で依然最弱（ただし全て07-12修正前のデータ）。

---

### 2026-08-13 バックテストによる閾値の再決定（470件で検証）

実運用の検証済みは26件しかなく、少ないサンプルから「強気過多」と誤って
判断していた。過去2年の実データに同じロジックを当てて470件を生成し検証。

| 設定 | 全体的中 | bull | bear | neutral |
|---|---|---|---|---|
| 9.0/-3.0（従来） | 41.3% | 76件 72.4% | 134件 56.0% | 260件 24.6% |
| **7.0/-2.0（採用）** | **45.3%** | 110件 70.0% | 155件 54.2% | — |
| 3.0/-1.0（最大） | 47.9% | 190件 57.9% | 172件 53.5% | — |

**判明した構造的問題**: 予測のneutralが55.3%も出るのに、実際にneutral
（±0.3%以内）だった日は22.1%しかなかった。閾値の幅が広すぎて、
判断できるはずの日を「様子見」に落としていた。

**採用理由**: 7.0/-2.0 は全体を+4.0pt改善しつつ、bullの的中率70%を維持できる。
3.0/-1.0 の方が全体は高いが、「強気」と言ったときの信頼性が57.9%まで落ちるため
採らなかった。

**限界（結果を読むときの注意）**: シナリオ補正（Gemini生成）は過去再現不可のため
除外、Fear&GreedはVIXからの近似。実運用とは完全一致しない。
過去2年の相場に最適化されている点にも注意し、実運用データで継続検証する。
再実行: 2026-08-17 09:55:01 [INFO] backtest_predictions: GC=F: 503日分
2026-08-17 09:55:01 [INFO] backtest_predictions: USDJPY=X: 516日分
2026-08-17 09:55:01 [INFO] backtest_predictions: ^GSPC: 501日分
2026-08-17 09:55:02 [INFO] backtest_predictions: ^IXIC: 501日分
2026-08-17 09:55:02 [INFO] backtest_predictions: ^N225: 486日分
2026-08-17 09:55:02 [INFO] backtest_predictions: ^SOX: 501日分
2026-08-17 09:55:03 [INFO] backtest_predictions: ^VIX: 503日分
2026-08-17 09:55:03 [INFO] backtest_predictions: ✅ バックテスト完了: 470件 / 全体的中率 41.3%
Tv 470 / I¦ 41.3%
  bull    :   76 I72.4% (\ª䗦16.2%)
  bear    :  134 I56.0% (\ª䗦28.5%)
  neutral :  260 I24.6% (\ª䗦55.3%)

---

### 2026-08-17 「どういう時に外すか」の分析（src/failure_analysis.py）

全体的中率だけを見て判断していたのが誤りだった。470件を条件別に切り分けた結果:

**① 41.3%という数字は誤解だった**
| 見方 | 的中率 |
|---|---|
| 全体（中立含む3択） | 41.3% |
| **上げ/下げを明言し、相場も±0.3%超動いた日** | **76.5%**（170件） |

中立予測は、相場が凪いだ日（470日中107日=22.8%）しか正解にならない。
つまり構造的に23%が上限で、低く出るのは当然だった。実力の指標として使えない。

**② 信号の強さで勝率が35ポイント違う（明言した日のみ）**
| 強さ | 勝率 | 件数 |
|---|---|---|
| \|score\| 3-6 | 50.0% | 40 |
| \|score\| 6-10 | 65.8% | 38 |
| \|score\| 10-15 | 74.1% | 58 |
| \|score\| 15+ | 85.1% | 74 |

これが `src/signal_confidence.py`（信頼度ランク）の根拠。

**③ 下げ予想の弱点が特定できた**
方向別に見ると bear は \|score\| 3-10 の帯で勝率50〜54%＝コイン投げ。
bull は閾値7.0のため弱い帯が存在せず全帯でS。
→ 閾値を締める案（bear -7.0 で的中66.3%）もあるが、中立過多に戻る副作用があるため
  **閾値は変えず、信頼度ランクで「当てにしない日」を明示する方式を採用**。

**④ 期待値+0.92%の6割は寄り付きギャップだった**
| 内訳 | 値 |
|---|---|
| 終値→翌終値 | +0.92% |
| うち寄り付きギャップ（見た時点で既に織り込み済み） | +0.59%（63.9%） |
| うち日中（寄り付き後に残る分） | +0.33%（勝率59.0%） |

米国市場の引け後にサインが出る以上、翌朝には織り込まれている。
数字を額面通り「取れる利益」と読むと実力を過大評価する。
ただし日中分が残っていたので、ギャップだけの見せかけではない。

**⑤ その他**: 最長6連敗あり（連敗は想定内）／ 最悪の外し10件は全て下げ予想 ／
金曜が最良(78.7%)・月曜が最悪(61.0%)／ パニック相場(VIX高)は75%だがn=16で未確定

**⚠️ 分析時の注意**: 値幅別（by_move_size）の集計は「結果が出た後」の分類であり、
事前に選べる条件ではない。判断ルールとして使ってはいけない。

---

## 🏆 機能レベル

| Level | 内容 | 状態 |
|-------|------|------|
| L1 | 価格取得・ニュース・基本分析・Telegram通知 | ✅ 完成 |
| L2 | AI議論・経済指標・YouTube要約・AI記憶・週次レポート・カレンダー | ✅ 完成 |
| L3a | 自律AIエージェント（Gemini Function Calling） | ✅ 完成 |
| L3b | テクニカル分析（RSI/MACD/ボリンジャーバンド） | ✅ 完成 |
| L3c | ポートフォリオ損益管理 | ✅ 完成 |
| L3d | 3シナリオ分析（楽観/基本/悲観・確率付き） | ✅ 完成 |
| L3e | 予測学習・正解率記録・Geminiへの精度フィードバック | ✅ 完成 |
| L4a | セクター分析・ローテーション検出・週次成績サマリー強化 | ✅ 完成 |
| L4b | 長期歴史データ分析（20年分・市場レジーム・類似期間検索） | ✅ 完成 |
| L4c | FRED経済指標（GDP・CPI・失業率・FF金利・イールドカーブ） | ✅ 完成 |
| L4d | 資産間相関分析（日経-ドル円・日経-S&P等の統計的関係） | ✅ 完成 |
| L4e | バックテスト（200日MA・VIXタイミング・押し目買い戦略検証） | ✅ 完成 |
| L4f | センチメント複合データ（P/C比率・AAII・COTレポート） | ✅ 完成 |
| L4g | Streamlitダッシュボード（インタラクティブWebアプリ） | ✅ 完成 |
| L4h | モンテカルロシミュレーション + マーコウィッツ効率的フロンティア | ✅ 完成 |
| L4i | FOMC議事録NLP分析（タカ派/ハト派自動判定） | ✅ 完成 |
| L4j | 米議員株取引トラッカー（STOCK Act公開データ） | ✅ 完成 |
| L4k | 自己改善AI（予測ミス分析→パラメータ自動最適化→自動コミット） | ✅ 完成 |
| L5a | マルチエージェント合議（4AI多数決・全員一致＝高確信シグナル） | ✅ 完成 |
| L5b | 完全自律エージェント（市場レジーム検知→今日の優先タスク自己決定） | ✅ 完成 |
| L5c | 強化学習ループ（予測ミスパターン学習・30件以上でRandomForest起動） | ✅ 完成 |
| L5d | マルチモーダル分析（チャート画像をGemini Visionで視覚的テクニカル分析） | ✅ 完成 |
| L5e | 自己批判エンジン（過去予測の反省→弱点発見→今日の分析に反映） | ✅ 完成 |
| L5f | Redditソーシャル感情（WSB/investing/stocks 個人投資家熱量スコア化） | ✅ 完成 |
| L5g | 決算前AI事前分析（直近5日内の主要企業決算プレビューを自動生成） | ✅ 完成 |
| L5h | グローバル市場連鎖（日経→DAX→S&P500の時系列ラグ相関・翌日予測） | ✅ 完成 |
| L5i | LINE通知（LINE Notifyで主要サマリーをTelegramと並行送信） | ✅ 完成 |
| L5j | J-Quants日本株スクリーナー（Nikkei225銘柄の上昇率・ATH近辺を毎週月曜分析） | ✅ 完成 |
| FX-PM | FX午後ダッシュボード（毎日14:00 JST・13パネル・Telegram配信） | ✅ 完成 |

<!-- ── 2026-07 来月の目標 ──────────────────────────────
  優先1: 予測精度の改善（6月の正解率23%→強気バイアス是正後の継続モニタリング）
  優先2: ポートフォリオ登録をTelegram Botコマンドで操作できるようにする（初心者でも使いやすく）
  優先3: note記事自動投稿の完全自動化（Step 8b の記事を手動コピーなしでnoteに投稿）
  ────────────────────────────────────────────────── -->

---

## 💻 ローカルでテスト実行

```bash
# 仮想環境（Python 3.11推奨）
pip install yfinance feedparser requests matplotlib japanize-matplotlib google-generativeai python-dotenv PyYAML pandas numpy

# 環境変数
cp .env.example .env
# .envにGEMINI_API_KEY、TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_IDを記入

# テスト実行
python cloud_run.py --mode test

# 特定モジュールのみテスト
python -c "from src.prediction_tracker import calc_accuracy; print(calc_accuracy())"
```

---

## 📱 エンドユーザー情報

- **名前**: 中田 洋介
- **レベル**: 投資初心者（わかりやすさ最優先）
- **デバイス**: iPhone（Safari/Chrome でレポート閲覧）
- **通知**: Telegram（market_ai_nakata_bot）
- **希望**: 「中学生でもわかる」レベルのわかりやすい説明

---

## 🕐 マルチタイムフレーム分析（2026-08-18追加）

`tech_signals.py` に「時間軸の一致」判定を追加。個々のシグナルの重なり
（コンフルエンス）とは**別の情報**として扱う。

- シグナルの重なり = その瞬間に何が起きたか
- 時間軸の一致 = そもそも今どちらへ傾いた相場か

**判定**: 週足(重み3)・日足(2)・4時間足(1)の各足で、25本移動平均に対する
**位置と傾きの両方**が揃ったときだけ up/down と判定（片方だけだと下降中の
戻りを上昇と誤読する）。移動平均から±0.3%以内は横ばい扱い。

**信頼度への反映**
- 全時間軸が同じ方向 → ⭐ 最高ランクへ格上げ（最も逆らいにくい形）
- 大きな時間軸が逆向き → 格下げ＋警告表示（押し目/戻りの可能性）

実例（2026-08-18）: 日経225の日足デッドクロス（売り）は週足・4時間足が
上向きのため ★★★→★参考 に格下げされた。単独では強い売りサインだが、
大きな流れに逆らう形なので警告付きで通知される。

⚠️ yfinanceは4時間足に対応している（`interval="4h"`）。1時間足からの合成は不要。

## 🌡 リスク計器盤（risk_gauges.py・2026-08-18追加）

恐怖指数を横並びで一覧し、「その指標にとって普段より大きく動いた」ものを通知する。

**既存2モジュールとの役割分担（重複させないこと）**
| モジュール | 見るもの |
|---|---|
| `sentiment_extreme.py` | VIXとF&Gが極値ゾーンに入った/戻った瞬間（水準） |
| `risk_sentiment.py` | 複数資産が同時に同じ方向を向いたか（リスクオン/オフ） |
| `risk_gauges.py` | 各指標が普段と比べてどれだけ動いたか（変化の大きさ） |

**しきい値の決め方が肝**: 固定%は使わない。VIXは平常時でも日々5〜10%動くが、
MOVE指数やドル指数が5%動くのは異常事態で、同じ数字では意味が違う。
各指標の過去1年の「1日の変化率の絶対値」の**90パーセンタイル**を基準にする
（＝年に約25日しか起きない大きさ）。最低1.5%の下限も設け、凪の期間に
基準が下がりすぎて些細な動きで鳴るのを防ぐ。

**データ入手先（Yahooに無いものが多い）**
| 指標 | 入手先 |
|---|---|
| VIX/VIX1D/VIX9D/VIX3M/VVIX/VXN/VXD/SKEW/MOVE/OVX/GVZ | yfinance（全て取得可） |
| 日経VI | 日経公式CSV `indexes.nikkei.co.jp/nkave/historical/nikkei_stock_average_vi_daily_jp.csv`（**各値が引用符で囲まれている**ので strip('"') 必須） |
| 日本国債利回り | 財務省CSV。**2種類を使い分ける**: `jgbcm.csv`=直近10日（最新値用）／`data/jgbcm_all.csv`=全期間1.1MB（しきい値の母数用）。和暦(R8.8.3)・Shift-JIS |
| 暗号資産F&G | `api.alternative.me/fng/?limit=365`（キー不要。**新しい順**で返るので反転が必要） |

⚠️ **取得できないもの**: VSTOXX（^V2TX/V2TX.DE とも不可）、RVX、日本国債VIX。

⚠️ `up_is_bad` を計器ごとに持たせている。VIXは上昇＝危険、F&Gは上昇＝安心で
色の意味が逆になるため。ここを取り違えると危険な状態が緑で表示される（過去に一度やらかしている）。

## 💱 為替シグナル（fx_signals.py）

対象8ペア: ドル円・ユーロ円・ポンド円・豪ドル円・スイス円（クロス円）＋
ユーロドル・ポンドドル・豪ドルドル（ドルストレート）。
クロス円の動きが「円が動いた」のか「ドルが動いた」のかを切り分けるため
両方を見る。

**通知条件**: 信頼度の高いサインが同方向に**3つ以上**（`_MIN_STRONG = 3`）。
緩めると毎日鳴って読み飛ばされるので変更しないこと。
配信先は `TELEGRAM_FX_CHAT_ID`（ようちゃん相場通知）。未設定ならメイン側へ。

検出ロジックは `tech_signals` を使い回す。二重実装すると片方だけ直して
食い違う（`technical_signal.py` と `tech_signals.py` の重複で二重通知が発生した実例あり）。

⚠️ 為替は24時間動くため、株のような「引け後のみ判定」の時間帯制限はかけない。

## 🔌 MCPサーバー（コネクタ）

設定ファイル: `.mcp.json`（プロジェクトルート）

| MCP | 役割 | 使うコマンド |
|-----|------|------------|
| **github** | GitHub Actionsのログ・ワークフロー・コミット履歴を直接参照 | `/check-actions` |
| **brave-search** | 最新の市場ニュース・経済指標をリアルタイム検索 | `/market-news`, `/research` |

### セットアップ方法
1. `.mcp.json` の `YOUR_GITHUB_PAT_HERE` を実際のGitHub Personal Access Tokenに書き換え
2. `.mcp.json` の `YOUR_BRAVE_API_KEY_HERE` を実際のBrave Search APIキーに書き換え
3. Claude Codeで `/mcp` コマンドを実行して接続確認

### トークン取得先
- GitHub PAT: https://github.com/settings/tokens → `repo` + `workflow` 権限
- Brave Search API: https://brave.com/search/api/ → 無料枠2000回/月

---

## 🔧 Python環境

- **ローカル**: Python 3.14.5（Windows）
  - `C:\Users\中田　洋介\AppData\Local\Python\pythoncore-3.14-64\python.exe`
- **GitHub Actions**: Python 3.11（Ubuntu）
- **主要ライブラリ**: yfinance, feedparser, matplotlib, japanize-matplotlib, google-generativeai, requests, PyYAML
