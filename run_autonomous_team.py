#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
完全自律AIチームシステム - 統合実行スクリプト
毎朝7:30 に GitHub Actions または タスクスケジューラーから自動実行

使用例:
  python run_autonomous_team.py --mode morning      # 朝の分析実行
  python run_autonomous_team.py --mode verification  # 予測検証
  python run_autonomous_team.py --mode full         # 完全ループ
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
import pytz
import json

# プロジェクトパスを追加
sys.path.insert(0, str(Path(__file__).parent))

from src.autonomous_team import AutonomousTeamSystem
from src.fetch_prices import fetch_prices  # 既存のデータ取得
from src.fetch_news import fetch_news  # 既存のニュース取得
from src.indicators import calc_risk_score  # 既存のリスク計算

# ロギング設定
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('logs/autonomous_team.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

JST = pytz.timezone('Asia/Tokyo')


class AutonomousTeamRunner:
    """完全自律AIチームの統合実行管理"""
    
    def __init__(self):
        self.team_system = AutonomousTeamSystem()
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        
        logger.info("✅ AutonomousTeamRunner 初期化完了")
    
    def fetch_market_data(self) -> dict:
        """リアルタイム市場データを取得"""
        logger.info("📊 市場データを取得中...")
        
        try:
            # 既存の価格取得機能を使用
            prices = fetch_prices()
            
            # VIX取得
            vix = prices.get("^VIX", {}).get("latest", 20) or 20
            
            # S&P500トレンド判定
            sp500 = prices.get("^GSPC", {})
            change_pct = sp500.get("change_pct", 0) or 0
            
            trend = "uptrend" if change_pct > 0.5 else ("downtrend" if change_pct < -0.5 else "neutral")
            
            # モメンタム計算
            momentum = change_pct / 100 if change_pct else 0
            
            # ドローダウン（簡易版）
            high = sp500.get("high", 0) or 0
            low = sp500.get("low", 0) or 0
            current = sp500.get("close", 0) or 0
            max_drawdown = -((high - current) / high * 100) if high > 0 else 0
            
            market_data = {
                "vix": vix,
                "trend": trend,
                "momentum": momentum,
                "max_drawdown": max_drawdown,
                "correlation": 0.65,  # 簡易版
                "recent_accuracy": 0.68,
                "trend_accuracy": 0.62,
                "risk_accuracy": 0.75,
                "sp500_change": change_pct,
                "prices": prices
            }
            
            logger.info(f"✅ VIX={vix}, トレンド={trend}, S&P500={change_pct:.2f}%")
            return market_data
            
        except Exception as e:
            logger.warning(f"⚠️ 市場データ取得エラー: {e}. デモデータを使用します。")
            return self._get_demo_market_data()
    
    def fetch_news_data(self) -> list:
        """ニュースデータを取得"""
        logger.info("📰 ニュースを取得中...")
        
        try:
            # 既存のニュース取得機能を使用
            news_items = fetch_news()
            
            # ニュースに影響度を追加
            for item in news_items:
                category = item.get("category", "その他")
                if "日銀" in str(item.get("headline", "")):
                    item["impact"] = 0.85
                elif "FOMC" in str(item.get("headline", "")):
                    item["impact"] = 0.80
                elif "決算" in str(item.get("headline", "")):
                    item["impact"] = 0.60
                else:
                    item["impact"] = 0.40
            
            logger.info(f"✅ ニュース {len(news_items)} 件を取得")
            return news_items[:5]  # 上位5件
            
        except Exception as e:
            logger.warning(f"⚠️ ニュース取得エラー: {e}. デモデータを使用します。")
            return self._get_demo_news_data()
    
    def run_morning_analysis(self):
        """朝の分析（毎朝7:30実行）"""
        logger.info("="*70)
        logger.info("🌅 朝の完全自律分析を開始します（7:30 JST）")
        logger.info("="*70)
        
        # リアルタイムデータを取得
        market_data = self.fetch_market_data()
        news_data = self.fetch_news_data()
        market_data["news"] = news_data
        
        # チームシステムで日次分析を実行
        result = self.team_system.run_daily_cycle(market_data)
        
        # 結果を保存
        self._save_result(result, "morning_analysis")
        
        # レポートを出力
        self._output_report(result)
        
        logger.info("✅ 朝の分析が完了しました")
        return result
    
    def run_verification(self):
        """予測検証（翌朝に実行）"""
        logger.info("="*70)
        logger.info("🔬 前日の予測を検証します")
        logger.info("="*70)
        
        # 本日の実績データを取得
        actual_market = self.fetch_market_data()
        actual_market["price_change_pct"] = actual_market.get("momentum", 0) * 100
        
        # 予測を検証
        verification_result = self.team_system.verify_predictions(actual_market)
        
        # 結果を保存
        self._save_result(verification_result, "verification")
        
        logger.info("✅ 検証が完了しました")
        return verification_result
    
    def run_full_cycle(self):
        """完全ループ（朝の分析 → 検証 → 改善）"""
        logger.info("🔄 完全自律ループを実行します")
        
        # ステップ1: 朝の分析
        morning_result = self.run_morning_analysis()
        
        # ステップ2: 予測検証（シミュレーション）
        logger.info("\n⏰ 翌朝のシーンをシミュレーション...")
        verification_result = self.run_verification()
        
        # ステップ3: 改善アクション提案
        improvements = self._suggest_improvements(verification_result)
        logger.info(f"\n💡 改善提案: {', '.join(improvements)}")
        
        return {
            "morning_analysis": morning_result,
            "verification": verification_result,
            "improvements": improvements
        }
    
    def _save_result(self, result: dict, result_type: str):
        """結果をJSONで保存"""
        timestamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
        filename = self.data_dir / f"team_{result_type}_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"💾 結果を保存: {filename}")
    
    def _output_report(self, result: dict):
        """レポートを標準出力"""
        print("\n" + "="*70)
        print("📋 【最終レポート】")
        print("="*70)
        print(result.get("report", "レポート生成中..."))
    
    def _suggest_improvements(self, verification_result: dict) -> list:
        """改善提案を生成"""
        improvements = []
        
        if not verification_result.get("correct"):
            lesson = verification_result.get("lesson_learned", "")
            
            if "ニュース" in lesson:
                improvements.append("ニュースサンプリングレートを上げる")
            
            if "ボラティリティ" in lesson:
                improvements.append("VIX急変検出アルゴリズムを改善")
            
            if "トレンド" in lesson:
                improvements.append("トレンド反転の早期検出機能を追加")
            
            if not improvements:
                improvements.append("データ多元化の継続")
        else:
            improvements.append("現在のロジックを維持")
        
        improvements.append("セクター別分析の精度向上を検討")
        
        return improvements
    
    @staticmethod
    def _get_demo_market_data() -> dict:
        """デモ用市場データ"""
        return {
            "vix": 22.5,
            "trend": "uptrend",
            "momentum": 0.15,
            "max_drawdown": -2.5,
            "correlation": 0.65,
            "recent_accuracy": 0.68,
            "trend_accuracy": 0.62,
            "risk_accuracy": 0.75,
            "sp500_change": 1.5
        }
    
    @staticmethod
    def _get_demo_news_data() -> list:
        """デモ用ニュースデータ"""
        return [
            {
                "headline": "日銀が金利を維持、慎重姿勢を強調",
                "impact": 0.85,
                "category": "金融政策"
            },
            {
                "headline": "NVIDIA が決算好調、ガイダンス上方修正",
                "impact": 0.70,
                "category": "決算"
            },
            {
                "headline": "新興国通貨が上昇、ドル円は160円近辺",
                "impact": 0.60,
                "category": "FX"
            }
        ]


def main():
    """メイン実行"""
    parser = argparse.ArgumentParser(
        description="完全自律AIチームシステム - 統合実行"
    )
    parser.add_argument(
        "--mode",
        choices=["morning", "verification", "full"],
        default="morning",
        help="実行モード: morning=朝の分析, verification=予測検証, full=完全ループ"
    )
    
    args = parser.parse_args()
    
    runner = AutonomousTeamRunner()
    
    if args.mode == "morning":
        runner.run_morning_analysis()
    
    elif args.mode == "verification":
        runner.run_verification()
    
    elif args.mode == "full":
        runner.run_full_cycle()
    
    logger.info("🎉 実行が完了しました")


if __name__ == "__main__":
    main()
