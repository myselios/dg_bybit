#!/usr/bin/env python3
"""
scripts/check_testnet_equity.py
Testnet equity 확인 스크립트 (Phase 12a-4 DoD 검증용)

Linear USDT 기준:
- UNIFIED 계정 totalEquity (USDT) 확인
- 최소 요구사항: >= $100 USDT
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
from dotenv import load_dotenv
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient

# Load environment variables
load_dotenv()


def check_testnet_equity():
    """Testnet equity 확인 (Linear USDT)"""
    print("=" * 60)
    print("Testnet Equity Check - Linear USDT (Phase 12a-4)")
    print("=" * 60)

    # Load Testnet credentials from .env
    api_key = os.getenv("BYBIT_TESTNET_API_KEY")
    api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")

    if not api_key or not api_secret:
        print("❌ ERROR: Testnet API credentials not found in .env")
        print("   Required: BYBIT_TESTNET_API_KEY, BYBIT_TESTNET_API_SECRET")
        return False

    # REST client 초기화 (Testnet)
    base_url = "https://api-testnet.bybit.com"
    rest_client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url
    )

    try:
        # GET /v5/account/wallet-balance (accountType=UNIFIED 필수)
        response = rest_client.get_wallet_balance(accountType="UNIFIED", coin="BTC")

        # Debug: Print raw response
        import json
        print(f"\n[DEBUG] Raw response:")
        print(json.dumps(response, indent=2))

        # Parse response
        result = response.get("result", {})
        coin_list = result.get("list", [])

        if not coin_list:
            print("\n❌ ERROR: No wallet data found")
            print(f"   Result keys: {list(result.keys())}")
            return False

        # Extract equity (BTC)
        wallet_data = coin_list[0]
        coin_data = wallet_data.get("coin", [])

        if not coin_data:
            print("❌ ERROR: No coin data found")
            return False

        btc_data = coin_data[0]

        # Handle empty strings from API
        equity_str = btc_data.get("equity", "0")
        equity_btc = float(equity_str) if equity_str else 0.0

        available_str = btc_data.get("availableToWithdraw", "0")
        available_balance_btc = float(available_str) if available_str else 0.0

        # Total equity (USDT) from account level (Linear USDT)
        total_equity_usdt = float(wallet_data.get("totalEquity", "0"))

        # Display results
        print(f"\n📊 Testnet Wallet Balance (Linear USDT):")
        print(f"   - Total Equity (USDT):     ${total_equity_usdt:,.2f} USDT")
        print(f"   - BTC Equity:              {equity_btc:.8f} BTC")
        print(f"   - BTC Available Balance:   {available_balance_btc:.8f} BTC")

        # Check DoD requirement (Linear USDT: >= $100 USDT)
        min_required_usdt = 100.0
        if total_equity_usdt >= min_required_usdt:
            print(f"\n✅ DoD PASS: Equity (${total_equity_usdt:,.2f} USDT) >= ${min_required_usdt} USDT")
            print(f"   → Linear USDT 테스트 준비 완료!")
            return True
        else:
            print(f"\n❌ DoD FAIL: Equity (${total_equity_usdt:,.2f} USDT) < ${min_required_usdt} USDT")
            print(f"   → Testnet에서 USDT를 추가로 받아야 합니다.")
            print(f"   → https://testnet.bybit.com/app/user/api-management")
            return False

    except Exception as e:
        print(f"❌ ERROR: Failed to fetch wallet balance: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = check_testnet_equity()
    sys.exit(0 if success else 1)
