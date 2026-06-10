#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
完全自律AIディベートシステム - テスト実行スクリプト
本格的なAIディベート機能を確認
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# テストの簡易版を実行
def test_ai_debate():
    """ai_debate.py の新規関数をテスト"""
    print("\n" + "="*70)
    print("🤖 【テスト】完全自律AIディベートシステム")
    print("="*70)
    
    # サンプル市場データ
    market_data_str = """
    【市場データ】
    日経平均: 28500円 (+1.2%)
    S&P500: 5200 (+0.8%)
    VIX: 18.5
    ドル円: 160.50円 (+0.3%)
    リスクスコア: 35.0
    Fear&Greed: 72 (強気)
    """
    
    news_text = """
    ・日銀が金利を0.2%に据え置く方針を示唆
    ・米テク企業の決算が好調、ガイダンス上方修正
    ・新興国通貨が上昇、リスクオンムード
    """
    
    print("\n【市場データ】")
    print(market_data_str)
    print("\n【ニュース】")
    print(news_text)
    
    try:
        from src.ai_debate import run_team_debate
        
        print("\n" + "="*70)
        print("🤝 チームディベート実行中...\n")
        
        # チームディベート実行
        result = run_team_debate(market_data_str, news_text)
        
        if result.get("status") == "success":
            print("\n" + "="*70)
            print("✅ チームディベート完了！\n")
            
            # 各メンバーの意見と投票
            print("【各メンバーの独立分析と投票】")
            for member_name, member_data in result.get("members", {}).items():
                print(f"\n{member_data['emoji']} {member_name}")
                print(f"   意見: {member_data['opinion'][:80]}...")
                print(f"   投票: 「{member_data['vote']}」")
            
            # 相互反論・賛成
            print("\n【相互反論・賛成フェーズ】")
            for member_name, responses in result.get("debate_responses", {}).items():
                print(f"\n{member_name} の反応:")
                for target_name, response in responses.items():
                    print(f"  → {target_name}: {response[:100]}...")
            
            # 投票結果
            print("\n【投票結果】")
            for vote, count in result.get("votes", {}).items():
                print(f"  投票: {vote}")
            
            # 最終決定
            print("\n" + "-"*70)
            print(f"🎯 最終決定: 「{result.get('final_decision')}」")
            print(f"   信頼度: {result.get('confidence'):.1%} ({result.get('confidence')*5:.0f}/5 票)")
            print(f"   理由: {result.get('summary', '')}")
            print("-"*70)
            
            print("\n✅ テスト成功！\n")
            return True
        else:
            print(f"\n❌ エラー: {result.get('status', '不明')}")
            return False
            
    except ImportError as e:
        print(f"❌ インポートエラー: {e}")
        print("   src/ai_debate.py が見つかりません")
        return False
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_autonomous_team():
    """autonomous_team.py の完全自律システムをテスト"""
    print("\n" + "="*70)
    print("🤖 【テスト】完全自律AIチームシステム")
    print("="*70)
    
    try:
        from src.autonomous_team import AutonomousTeamSystem
        
        # システム初期化
        system = AutonomousTeamSystem()
        
        # サンプル市場データ
        market_data = {
            "vix": 22.5,
            "trend": "uptrend",
            "momentum": 0.15,
            "max_drawdown": -2.5,
            "correlation": 0.65,
            "recent_accuracy": 0.68,
            "trend_accuracy": 0.62,
            "risk_accuracy": 0.75,
            "news": [
                {"headline": "日銀が金利を維持", "impact": 0.8, "category": "金融政策"},
                {"headline": "テック企業が決算好調", "impact": 0.6, "category": "決算"},
            ]
        }
        
        # 日次サイクル実行
        result = system.run_daily_cycle(market_data)
        
        print("\n✅ 完全自律チームシステムテスト成功！")
        return True
        
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║      🤖 完全自律AIディベートシステム - テスト実行スクリプト               ║
║                                                                            ║
║      本格的なAIディベート機能を確認します                                ║
║      • マーケット太郎、ニュース花子、リスク次郎が独立分析                ║
║      • 相互に反論・賛成                                                   ║
║      • 多数決で最終判定                                                   ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
""")
    
    # Test 1: AIディベート
    success1 = test_ai_debate()
    
    # Test 2: 完全自律チーム
    input("\nPress Enter to continue to full autonomous team test...")
    success2 = test_autonomous_team()
    
    # Summary
    print("\n" + "="*70)
    print("📊 テスト結果サマリー")
    print("="*70)
    print(f"AIディベート:      {'✅ 成功' if success1 else '❌ 失敗'}")
    print(f"完全自律チーム:    {'✅ 成功' if success2 else '❌ 失敗'}")
    print("="*70)
    
    if success1 and success2:
        print("\n🎉 すべてのテストが成功しました！")
        sys.exit(0)
    else:
        print("\n⚠️ 一部のテストに失敗しました")
        sys.exit(1)
