# Market AI Secretary
## 投資経済情報 自動収集・分析・通知システム

APIキー不要・ローカル動作・Windows対応の投資経済AI秘書です。

---

## ⚠️ 重要な注意事項

> **本システムは投資助言ではありません。分析補助目的の情報提供ツールです。**
> すべての投資判断はご自身の責任においてお願いします。
> データ取得失敗・遅延・誤差がある可能性があります。
> 「必ず上がる」「確実に下がる」などの断定表現は本システムでは使用しません。

---

## 機能一覧

| 機能 | 内容 |
|------|------|
| 価格データ取得 | 日経・TOPIX・S&P500・NASDAQ・Dow・ドル円・ユーロドル・米10年金利・金・原油・Bitcoin・VIX |
| ニュース収集 | Google News RSSから10キーワード×5件を自動収集 |
| チャート生成 | 指数・為替・コモディティ・リスクメーター・ニュース重要度のPNG |
| レポート出力 | Markdown + HTML（日本語・章立て構成） |
| Telegram通知 | 設定がない場合はスキップ。ローカルにレポートを保存 |
| 安全設計 | 取得失敗しても全体停止しない。失敗元はログに記録 |

---

## セットアップ手順（初回のみ）

### 1. Pythonのインストール確認

コマンドプロンプトまたは PowerShell を開いて実行：

```
python --version
```

`Python 3.10` 以上が表示されればOKです。
表示されない場合は https://www.python.org/downloads/ からインストールしてください。

---

### 2. フォルダへ移動

```
cd C:\Users\中田　洋介\Desktop\tousijouhou\market-ai-secretary
```

---

### 3. ライブラリのインストール

```
pip install -r requirements.txt
```

インストールには数分かかる場合があります。

---

### 4. .envファイルの作成（Telegram通知を使う場合）

`.env.example` をコピーして `.env` という名前で保存：

```
copy .env.example .env
```

メモ帳などで `.env` を開き、以下のように編集：

```
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFGxxxxxx（BotFatherから取得）
TELEGRAM_CHAT_ID=987654321（あなたのChat ID）
```

**Telegram通知が不要な場合は`.env`を作らなくてもOKです。**
その場合、通知はスキップされ、レポートはローカルに保存されます。

---

### 5. 動作テスト

```
python run_daily.py --mode test
```

以下のように表示されれば成功です：

```
テスト実行完了
  地合い: 中立
  価格取得件数: 10
  ニュース件数: 45
  チャート数:   5
  レポートMD:   reports\2025-01-01_test.md
  レポートHTML: reports\2025-01-01_test.html
```

---

## 実行コマンド

| コマンド | タイミング | 内容 |
|----------|-----------|------|
| `python run_daily.py --mode morning` | 朝（7〜9時） | 前日米国市場＋当日朝の日本市場分析 |
| `python run_daily.py --mode noon`    | 昼（12時前後） | 日本市場前場の振り返り |
| `python run_daily.py --mode evening` | 夕方（17〜18時） | 日本市場引け＋夜の米国市場開幕前 |
| `python run_daily.py --mode test`    | いつでも | 動作確認用（全機能を試す） |

---

## 出力ファイルの場所

```
market-ai-secretary/
├─ reports/
│  ├─ 2025-01-01_morning.md      ← Markdownレポート
│  ├─ 2025-01-01_morning.html    ← HTMLレポート（ブラウザで開ける）
│  ├─ charts/
│  │  ├─ 2025-01-01_indices.png       ← 主要指数チャート
│  │  ├─ 2025-01-01_forex.png         ← 為替チャート
│  │  ├─ 2025-01-01_commodities.png   ← コモディティチャート
│  │  ├─ 2025-01-01_risk_meter.png    ← リスク判定メーター
│  │  └─ 2025-01-01_news.png          ← ニュース重要度
│  └─ archive/                   ← バックアップ
├─ data/
│  ├─ raw/     ← 生データ（JSON）
│  ├─ processed/ ← 整形済みデータ（CSV）
│  └─ news/    ← ニュースデータ（JSON）
└─ logs/
   └─ 2025-01-01.log             ← 実行ログ
```

---

## レポートの構成

| 章 | 内容 |
|----|------|
| A. 今日の結論 | 地合い判定と主な材料 |
| B. 市場全体の地合い | 全指数の一覧表 |
| C. 為替 | ドル円・ユーロドルの動向と考察 |
| D. 米国株 | S&P500・NASDAQ・Dow・VIX |
| E. 日本株 | 日経平均・TOPIX・為替との関係 |
| F. 金利 | 米10年金利の動向 |
| G. コモディティ・仮想通貨 | 金・原油・Bitcoin |
| H. 注目ニュース | 重要度A→B→C順で表示 |
| I. 今日の監視ポイント | 地合いに応じた注意事項 |
| J. 事実・推測・意見の分離 | 本資料の区別方針 |
| K. 注意事項 | 免責事項 |

---

## 毎日自動実行する方法（Windowsタスクスケジューラ）

1. スタートメニューから「タスクスケジューラ」を検索して開く
2. 「基本タスクの作成」をクリック
3. 名前: `市場レポート_朝`
4. トリガー: 毎日 → 時刻 `7:30`
5. 操作: プログラムの開始
   - プログラム: `python`
   - 引数: `run_daily.py --mode morning`
   - 開始フォルダ: `C:\Users\中田　洋介\Desktop\tousijouhou\market-ai-secretary`
6. 完了

---

## データの取得先（APIキー不要）

| データ | 取得元 |
|--------|--------|
| 株価・為替・金利・コモディティ | yfinance（Yahoo Finance API経由） |
| フォールバック | Stooq 公開CSV |
| ニュース | Google News RSS |

---

## トラブルシューティング

### 「pip が見つからない」
→ `python -m pip install -r requirements.txt` で試してください。

### 「価格データ取得失敗が多い」
→ `logs/` フォルダのログを確認してください。Yahoo FinanceやStooqのアクセス制限が一時的にかかる場合があります。時間をおいて再実行してください。

### 「チャートが日本語化けする」
→ Windows の場合、`MS Gothic` フォントが自動で使われます。変化がない場合は `matplotlib` のキャッシュを削除してください（`%USERPROFILE%\.matplotlib` フォルダを削除）。

### 「Telegramに届かない」
→ `.env` ファイルのトークンとChat IDを再確認してください。`logs/` でエラー内容を確認できます。

---

## エージェント設計（将来拡張用）

| エージェント名 | 役割 |
|----------------|------|
| market-data-collector | データ収集専門 |
| market-visualizer | チャート生成専門 |
| macro-analyst | マクロ分析専門 |
| risk-auditor | レポート品質・リスクチェック |
| market-secretary | Telegram用ショートサマリー生成 |

---

## 絶対ルール（システムポリシー）

- 投資助言・売買指示は禁止
- 「必ず上がる」「確実に下がる」などの断定は禁止
- 事実・推測・意見を必ず分ける
- データ取得時刻を必ず表示
- データ元URLを保存
- 取得失敗時は処理を止めず、ログに残す
- 日本時間(JST)で表示
- APIキーが必要なサービスは使わない

---

*本システムはローカル完結型です。クラウドサービス・APIキーなしで動作します。*
