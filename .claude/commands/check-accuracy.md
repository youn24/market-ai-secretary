# /check-accuracy

AI予測の正解率を分析して改善提案を行います。

## 手順

### Step 1: データ読み込み
`data/predictions.json` を Read して全予測データを取得。
`src/prediction_tracker.py` も Read して _extract_direction 関数を確認。

### Step 2: 以下を計算
- 直近10日・30日の正解率（%）
- 強気/弱気/中立 それぞれの正解率
- 外れたときのVIX・riskスコアの傾向（苦手な市場環境）
- verified: false のレコードは集計から除外する

### Step 3: このフォーマットで表示

```
📊 AI予測精度レポート
━━━━━━━━━━━━━━━━━━━━
🎯 直近10日: X% (X勝X敗)
📅 直近30日: X% (X勝X敗)
📈 全期間:   X件検証済み

💪 方向別成績
  📈 強気(上昇予測): X%
  📉 弱気(下落予測): X%
  ➡️  中立(横ばい予測): X%

📅 直近5日の結果
  ✅/❌ [日付] [予測] → 実際[騰落率]%

📌 得意・苦手
  ・得意: （例: VIX低いときの強気予測）
  ・苦手: （例: 急変時の方向判断）

🔧 改善アクション
  （正解率に応じた提案）
```

### Step 4: 正解率に応じた対応

**65%超 →** 「🏆 高精度維持中！」と報告して終了。

**50〜65% →** `_extract_direction()` のシナリオ確率閾値（現在45）を調整する案をユーザーに確認してから実施。

**50%未満 →** `src/prediction_tracker.py` の `_extract_direction()` を改善して
`git add src/prediction_tracker.py && git commit -m "fix: 予測ロジック改善" && git push origin main` を実行。

### 注意
- データが3件未満なら「データ蓄積中」と返す
- 免責表示・投資助言の文言は絶対に追加しない
