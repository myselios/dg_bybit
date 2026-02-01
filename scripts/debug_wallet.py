#!/usr/bin/env python3
"""
scripts/debug_wallet.py
Wallet API 응답 디버깅 스크립트 - 정확한 문제 진단
"""

import os
import json
from dotenv import load_dotenv
from infrastructure.exchange.bybit_rest_client import BybitRestClient

load_dotenv()

def debug_wallet():
    """Wallet API 모든 응답 출력"""

    api_key = os.getenv("BYBIT_TESTNET_API_KEY")
    api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")

    if not api_key or not api_secret:
        print("❌ API 키 없음")
        return

    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com",
    )

    print("=" * 60)
    print("🔍 Wallet API 디버깅")
    print("=" * 60)

    # 1. UNIFIED + BTC
    print("\n1️⃣ UNIFIED + BTC 조회:")
    try:
        response1 = client.get_wallet_balance(accountType="UNIFIED", coin="BTC")
        print(json.dumps(response1, indent=2))
    except Exception as e:
        print(f"❌ 에러: {e}")

    # 2. UNIFIED + USDT
    print("\n2️⃣ UNIFIED + USDT 조회:")
    try:
        response2 = client.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        print(json.dumps(response2, indent=2))
    except Exception as e:
        print(f"❌ 에러: {e}")

    # 3. UNIFIED + USD
    print("\n3️⃣ UNIFIED + USD 조회:")
    try:
        response3 = client.get_wallet_balance(accountType="UNIFIED", coin="USD")
        print(json.dumps(response3, indent=2))
    except Exception as e:
        print(f"❌ 에러: {e}")

    # 4. CONTRACT 계정
    print("\n4️⃣ CONTRACT + USDT 조회:")
    try:
        response4 = client.get_wallet_balance(accountType="CONTRACT", coin="USDT")
        print(json.dumps(response4, indent=2))
    except Exception as e:
        print(f"❌ 에러: {e}")

    print("\n" + "=" * 60)
    print("✅ 디버깅 완료")
    print("=" * 60)

if __name__ == "__main__":
    debug_wallet()
