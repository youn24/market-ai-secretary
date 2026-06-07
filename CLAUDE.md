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
    ├── Step 1: src/fetch_prices.py      → yfinanceで価格取得
    ├── Step 2: src/fetch_news.py        → Google News RSS取得
    ├── Step 3: src/fetch_extra_news.py  → 追加ニュース
    ├── Step 4: src/indicators.py        → リスクスコア計算
    ├── Step 5: src/analyze.py           → 基本分析
    ├── Step 5b: src/ai_debate.py        → AI3視点議論（強気/弱気/中立）
    ├── Step 5c: src/economic_indicators.py → 経済指標分析
    ├── Step 5d: src/youtube_summary.py  → YouTube動画要約
    ├── Step L3a: src/ai_agent.py        → 自律AIエージェント（Gemini Function Calling）
    ├── Step L3b: src/technical_ai.py   → テクニカル分析（RSI/MACD/BB）
    ├── Step L3c: src/portfolio.py       → ポートフォリオ管理
    ├── Step L3d: src/scenario.py        → 3シナリオ分析（楽観/基本/悲観）
    ├── Step L3e: src/prediction_tracker.py → 予測学習・正解率記録
    ├── Step L4a: src/sector_analysis.py   → セクター分析・ローテーション
    │             src/sector_chart.py      → セクターヒートマップ画像
    ├── Step L4b: src/historical_analysis.py → 長期歴史データ分析（20年分）
    ├── Step L5a: src/multi_agent_consensus.py → 4AIエージェント多数決合議
    ├── Step L5b: src/autonomous_orchestrator.py → 完全自律エージェント（今日のミッション決定）
    ├── Step L5c: src/reinforcement_learning.py → 強化学習ループ（ML予測・パターン学習）
    ├── Step 5f: src/economic_calendar.py → 週次カレンダー（月曜のみ）
    ├── Step 5e: src/ai_memory.py        → AI記憶更新・継続分析
    ├── Step 6: src/visualize.py         → matplotlibチャート生成
    ├── Step 7: cloud_run._save_html_report() → HTMLレポート生成
    ├── Step L5d: src/multimodal_analysis.py → チャート画像Gemini Vision分析（Step6後）
    └── Step 8: src/notify_telegram.py   → Telegram通知送信
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
| `src/indicators.py` | リスクスコア算出 |
| `src/ai_debate.py` | Gemini 3視点AIディベート（強気・弱気・中立） |
| `src/ai_agent.py` | Gemini Function Calling 自律エージェント |
| `src/technical_ai.py` | RSI/MACD/ボリンジャーバンド計算 |
| `src/portfolio.py` | ポートフォリオ損益管理 |
| `src/scenario.py` | 楽観/基本/悲観シナリオ生成 |
| `src/prediction_tracker.py` | 予測記録→翌日検証→正解率→Geminiフィードバック |
| `src/ai_memory.py` | 過去データを記憶・継続比較分析 |
| `src/historical_analysis.py` | 長期歴史データ分析（Yahoo Finance API直接取得・20年分） |
| `src/economic_calendar.py` | 週次経済カレンダー画像生成（月曜のみ） |
| `src/visualize.py` | matplotlibダッシュボード画像生成 |
| `src/notify_telegram.py` | Telegram Bot通知送信 |
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

---

## 🔑 必須環境変数（GitHub Secrets）

```
GEMINI_API_KEY      → Google AI Studio で発行（無料 gemini-1.5-flash）
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

4. **Telegramの基本3メッセージ構成を維持**
   → ① 相場まとめ ② AI分析チャート ③ レポートURL の順序を保つ

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
model = genai.GenerativeModel("gemini-1.5-flash")  # 無料枠：1500回/日
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
