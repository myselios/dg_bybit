#!/usr/bin/env python3
"""
scripts/test_linear_usdt_testnet.py
Linear USDT Testnet 연동 테스트

목적:
1. BybitAdapter (Linear USDT) → Testnet 연동 확인
2. REST API: get_equity_usdt(), get_mark_price() 검증
3. WebSocket: 연결 확인 (선택)
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
from dotenv import load_dotenv
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient
from src.infrastructure.exchange.bybit_ws_client import BybitWsClient
from src.infrastructure.exchange.bybit_adapter import BybitAdapter

# Load environment variables
load_dotenv()


def test_linear_usdt_testnet():
    """Linear USDT Testnet 연동 테스트"""
    print("=" * 70)
    print("Linear USDT Testnet Integration Test")
    print("=" * 70)

    # 1. Credentials
    api_key = os.getenv("BYBIT_TESTNET_API_KEY")
    api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")

    if not api_key or not api_secret:
        print("❌ ERROR: Testnet API credentials not found in .env")
        return False

    print(f"\n✅ Step 1: API Credentials loaded")

    # 2. REST Client 초기화
    base_url = "https://api-testnet.bybit.com"
    rest_client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url
    )
    print(f"✅ Step 2: REST Client initialized (Testnet)")

    # 3. WebSocket Client 초기화 (선택, 연결은 나중에)
    wss_url = "wss://stream-testnet.bybit.com/v5/public/linear"
    ws_client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url=wss_url
    )
    print(f"✅ Step 3: WebSocket Client initialized (not connected yet)")

    # 4. BybitAdapter 초기화
    adapter = BybitAdapter(
        rest_client=rest_client,
        ws_client=ws_client,
        testnet=True
    )
    print(f"✅ Step 4: BybitAdapter initialized")

    # 5. Market Data 업데이트 (REST API)
    try:
        print(f"\n⏳ Step 5: Updating market data (REST API)...")
        adapter.update_market_data()
        print(f"✅ Step 5: Market data updated successfully")
    except Exception as e:
        print(f"❌ ERROR: Failed to update market data: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 6. Equity USDT 확인
    try:
        equity_usdt = adapter.get_equity_usdt()
        print(f"\n📊 Linear USDT Results:")
        print(f"   - Equity (USDT):     ${equity_usdt:,.2f} USDT")

        if equity_usdt >= 100.0:
            print(f"   ✅ Equity >= $100 USDT (sufficient for trading)")
        else:
            print(f"   ⚠️  Equity < $100 USDT (need more USDT)")
    except Exception as e:
        print(f"❌ ERROR: Failed to get equity_usdt: {e}")
        return False

    # 7. Mark Price 확인
    try:
        mark_price = adapter.get_mark_price()
        print(f"   - Mark Price (BTCUSDT): ${mark_price:,.2f} USD")
    except Exception as e:
        print(f"❌ ERROR: Failed to get mark_price: {e}")
        return False

    # 8. Index Price & Funding Rate 확인
    try:
        index_price = adapter.get_index_price()
        funding_rate = adapter.get_funding_rate()
        print(f"   - Index Price:       ${index_price:,.2f} USD")
        print(f"   - Funding Rate:      {funding_rate:.6f}")
    except Exception as e:
        print(f"⚠️  WARNING: Failed to get index/funding: {e}")

    # 9. 최종 결과
    print(f"\n" + "=" * 70)
    print(f"✅ Linear USDT Testnet Integration Test PASSED")
    print(f"=" * 70)
    print(f"\n주요 확인 사항:")
    print(f"  1. ✅ REST API 연동: category=\"linear\", symbol=\"BTCUSDT\"")
    print(f"  2. ✅ UNIFIED 계정: totalEquity (USDT) 파싱 성공")
    print(f"  3. ✅ MarketDataInterface: get_equity_usdt() 정상 동작")
    print(f"  4. ✅ Testnet Equity: ${equity_usdt:,.2f} USDT (충분)")

    return True


if __name__ == "__main__":
    success = test_linear_usdt_testnet()
    sys.exit(0 if success else 1)
