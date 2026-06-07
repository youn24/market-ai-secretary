# /check-accuracy

AI予測の正解率と学習状況を確認します。

以下を実行してください：
1. `data/predictions.json` を読み込む
2. 直近10日・30日・全期間の正解率を計算して表示
3. 強気予測・弱気予測・中立予測それぞれの正解率を比較
4. 「どんな相場状況のときに外れやすいか」をパターン分析
5. 改善提案があれば `src/prediction_tracker.py` の `_extract_direction()` 関数の調整案を提示

```python
# 確認用コマンド
python -c "
import sys; sys.path.insert(0,'.')
from src.prediction_tracker import calc_accuracy
import json
stats = calc_accuracy()
print('10日正解率:', stats['10d']['rate'], '%')
print('30日正解率:', stats['30d']['rate'], '%')
print('検証済件数:', stats['total_verified'])
"
```
