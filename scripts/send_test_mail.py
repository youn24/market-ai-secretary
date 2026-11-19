# -*- coding: utf-8 -*-
"""HTMLメールの設定を確かめて、テストを1通送る（scripts/send_test_mail.py）

    python -m scripts.send_test_mail            # 設定の確認だけ（送らない）
    python -m scripts.send_test_mail --send     # 実際に1通送る

⚠️ パスワードは画面に出しません。設定されているかどうかだけを表示します。
"""
import os
import sys

sys.path.insert(0, ".")

from dotenv import load_dotenv  # noqa: E402

# ⚠️ パスを明示する。load_dotenv() は呼び出し元ファイルの場所から上へ探すので、
#    scripts/ から実行すると .env を取り違えることがある。
load_dotenv(os.path.join(os.getcwd(), ".env"))

NEED = [
    ("SMTP_HOST", "送信サーバー", "smtp.gmail.com"),
    ("SMTP_PORT", "ポート番号", "587"),
    ("SMTP_USER", "送信に使うアドレス", "……@gmail.com"),
    ("SMTP_PASS", "アプリパスワード", "16文字"),
    ("MAIL_TO", "受け取るアドレス", "iPhoneで見るもの"),
]


def main() -> int:
    print("── メールの設定 ──")
    missing = []
    for key, label, hint in NEED:
        v = (os.getenv(key) or "").strip()
        if v:
            # 値は出さない。長さと、分かっても困らない部分だけ。
            shown = v if key in ("SMTP_HOST", "SMTP_PORT") else f"設定あり（{len(v)}文字）"
            print(f"  ✅ {label:18} {shown}")
        else:
            print(f"  ❌ {label:18} 未設定（例: {hint}）")
            missing.append(key)

    if missing:
        print(f"\n{len(missing)}個たりません。.env に書き足してください。")
        print("Gmailの場合、アプリパスワードの発行はこちら:")
        print("  https://myaccount.google.com/apppasswords")
        print("（先に2段階認証を有効にしないと、この画面は出ません）")
        return 1

    if "--send" not in sys.argv:
        print("\n設定はそろっています。実際に送るには:")
        print("  python -m scripts.send_test_mail --send")
        return 0

    print("\n今の相場データで1通作って送ります…")
    from src.fetch_prices import run as fetch_prices
    from src.indicators import calc_risk_score
    from src.notify_email import run as send_mail

    prices = fetch_prices()
    if isinstance(prices, tuple):
        prices = prices[0]
    risk = calc_risk_score(prices)

    def _safe(fn, label, *a):
        try:
            return fn(*a)
        except Exception as e:
            print(f"  （{label}は取れませんでした: {e}）")
            return {}

    from src.nikkei_market_data import run as nd
    from src.fear_watch import run as fr
    from src.policy_watch import run as pw

    ok = send_mail(prices=prices, risk=risk,
                   internals=_safe(nd, "日経内部データ"),
                   fear=_safe(fr, "恐怖指数"),
                   policy=_safe(pw, "政策金利"),
                   mode="test")
    if ok:
        print("\n✅ 送信しました。iPhoneのメールを確認してください。")
        print("   届かないときは迷惑メールも見てください（初回は入りやすい）。")
        return 0
    print("\n❌ 送れませんでした。上のログに理由が出ています。")
    print("   よくある原因: アプリパスワードではなく通常のパスワードを入れている")
    return 1


if __name__ == "__main__":
    sys.exit(main())
