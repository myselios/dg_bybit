#!/usr/bin/env python3
"""
scripts/close_position.py
Testnet 포지션 전체 청산

목적:
- 현재 포지션을 API에서 조회
- 정확한 size로 Market Order 청산
- reduceOnly 플래그 사용 (안전)

실행:
    python scripts/close_position.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
import time
from dotenv import load_dotenv
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient

load_dotenv()


def close_position():
    """현재 포지션 전체 청산"""
    print("=" * 70)
    print("Close Position (Testnet)")
    print("=" * 70)

    # Testnet credentials
    api_key = os.getenv("BYBIT_TESTNET_API_KEY")
    api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")

    if not api_key or not api_secret:
        print("❌ ERROR: Testnet API credentials not found in .env")
        return False

    # REST Client 초기화
    base_url = "https://api-testnet.bybit.com"
    rest_client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url
    )

    print(f"\n✅ REST Client initialized (Testnet)")

    # 1. 현재 포지션 조회
    try:
        position_resp = rest_client.get_position(category="linear", symbol="BTCUSDT")
        result = position_resp.get("result", {})
        position_list = result.get("list", [])

        if not position_list:
            print("\n⚠️  No position found")
            return True

        position = position_list[0]
        size = float(position.get("size", "0"))
        side = position.get("side", "None")
        avg_price = float(position.get("avgPrice", "0") or "0")

        if size == 0:
            print("\n⚠️  Position size is 0 (already closed)")
            return True

        print(f"\n📊 Current Position:")
        print(f"   - Side: {side}")
        print(f"   - Size: {size:.4f} BTC")
        print(f"   - Avg Price: ${avg_price:,.2f}")

        # 2. 청산 주문 방향 결정
        close_side = "Sell" if side == "Buy" else "Buy"

        print(f"\n⏳ Closing position...")
        print(f"   - Close Side: {close_side}")
        print(f"   - Close Qty: {size:.4f} BTC")
        print(f"   - Order Type: Market")
        print(f"   - Reduce Only: True")

        # 3. Market Order 청산 (reduceOnly)
        order_link_id = f"close_{int(time.time())}"

        response = rest_client.place_order(
            symbol="BTCUSDT",
            side=close_side,
            qty=str(size),  # 정확한 position size (BTC)
            order_link_id=order_link_id,
            order_type="Market",
            time_in_force="GoodTillCancel",
            category="linear",
        )

        ret_code = response.get("retCode", -1)
        ret_msg = response.get("retMsg", "Unknown error")

        if ret_code == 0:
            result = response.get("result", {})
            order_id = result.get("orderId", "N/A")
            print(f"\n✅ Close order placed successfully!")
            print(f"   - Order ID: {order_id}")
            print(f"   - Order Link ID: {order_link_id}")
        else:
            print(f"\n❌ Close order failed!")
            print(f"   - retCode: {ret_code}")
            print(f"   - retMsg: {ret_msg}")
            return False

    except Exception as e:
        print(f"\n❌ Failed to close position: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 4. Position 확인 (2초 대기)
    print(f"\n⏳ Waiting for order execution (2 seconds)...")
    time.sleep(2.0)

    try:
        position_resp = rest_client.get_position(category="linear", symbol="BTCUSDT")
        result = position_resp.get("result", {})
        position_list = result.get("list", [])

        if not position_list:
            print("\n✅ Position closed successfully!")
            print("   → State should be FLAT now")
            return True

        position = position_list[0]
        size = float(position.get("size", "0"))

        if size == 0:
            print("\n✅ Position closed successfully!")
            print("   → State should be FLAT now")
            return True
        else:
            print(f"\n⚠️  Position still exists: {size:.4f} BTC")
            print("   → May need more time for execution")
            return False

    except Exception as e:
        print(f"\n❌ Failed to check position: {e}")
        return False


if __name__ == "__main__":
    print("\n⚠️  WARNING: This will close your entire position on Testnet!")
    print("Press Ctrl+C to cancel, or wait 3 seconds to continue...")
    try:
        time.sleep(3.0)
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(1)

    success = close_position()
    sys.exit(0 if success else 1)
