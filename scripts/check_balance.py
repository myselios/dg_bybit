#!/usr/bin/env python3
"""
scripts/check_balance.py
Testnet/Mainnet 잔고 확인 스크립트
"""

import os
from dotenv import load_dotenv
from infrastructure.exchange.bybit_rest_client import BybitRestClient

load_dotenv()

def check_balance(testnet=True):
    """잔고 조회"""

    if testnet:
        api_key = os.getenv("BYBIT_TESTNET_API_KEY")
        api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")
        base_url = "https://api-testnet.bybit.com"
        print("🔧 Testnet 모드")
    else:
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")
        base_url = "https://api.bybit.com"
        print("⚠️ MAINNET 모드")

    if not api_key or not api_secret:
        print("❌ API 키가 설정되지 않았습니다")
        return

    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url,
    )

    # Unified Account 잔고 조회
    print("\n📊 잔고 조회 중...")
    response = client.get_wallet_balance(accountType="UNIFIED", coin="USDT")

    if response["retCode"] != 0:
        print(f"❌ 잔고 조회 실패: {response['retMsg']}")
        return

    result = response.get("result", {})
    accounts = result.get("list", [])

    if not accounts:
        print("❌ 계정 정보 없음")
        return

    account = accounts[0]
    coins = account.get("coin", [])

    print(f"\n💰 Unified Trading Account:")
    print("=" * 50)

    total_equity = 0.0
    for coin_info in coins:
        coin = coin_info.get("coin", "")
        wallet_balance = float(coin_info.get("walletBalance", "0"))
        equity = float(coin_info.get("equity", "0"))
        unrealized_pnl = float(coin_info.get("unrealisedPnl", "0"))

        if equity > 0:
            print(f"\n{coin}:")
            print(f"  Wallet Balance: {wallet_balance}")
            print(f"  Equity: {equity}")
            print(f"  Unrealized PnL: {unrealized_pnl}")

            if coin == "USDT":
                total_equity = equity

    print("\n" + "=" * 50)
    print(f"📈 Total USDT Equity: ${total_equity:.2f}")

    if total_equity < 100:
        print("\n⚠️ 경고: 잔고가 $100 미만입니다!")
        if testnet:
            print("📌 해결 방법:")
            print("   1. https://testnet.bybit.com 로그인")
            print("   2. Assets → Get Test Funds 클릭")
            print("   3. USDT 10,000 요청")
    else:
        print(f"\n✅ 잔고 충분: ${total_equity:.2f} >= $100")

if __name__ == "__main__":
    import sys

    testnet = "--mainnet" not in sys.argv

    if "--mainnet" in sys.argv:
        print("⚠️⚠️⚠️ MAINNET 모드 - 실제 계정! ⚠️⚠️⚠️\n")

    check_balance(testnet=testnet)
