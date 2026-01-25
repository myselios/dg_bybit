#!/usr/bin/env python3
"""
scripts/place_manual_order.py
Testnet 수동 주문 실행 (Grid 첫 거래 설정용)

목적:
- Testnet에서 Market Order 1회 실행
- last_fill_price 설정 (Grid 작동 조건 충족)
- API 동작 검증

실행:
    python scripts/place_manual_order.py --side Buy --qty 1
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
import argparse
from dotenv import load_dotenv
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient

load_dotenv()


def place_manual_order(side: str, qty: int):
    """
    Testnet Market Order 실행

    Args:
        side: "Buy" or "Sell"
        qty: 수량 (contracts, 1 contract = 0.001 BTC)
    """
    print("=" * 70)
    print("Testnet Manual Order Placement")
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

    # 현재 가격 확인
    try:
        ticker = rest_client.get_tickers(category="linear", symbol="BTCUSDT")
        mark_price = float(ticker["result"]["list"][0]["markPrice"])
        print(f"\n📊 Current Mark Price: ${mark_price:,.2f} USD")
    except Exception as e:
        print(f"❌ Failed to get mark price: {e}")
        return False

    # Market Order 실행
    try:
        print(f"\n⏳ Placing {side} Market Order...")
        print(f"   - Symbol: BTCUSDT")
        print(f"   - Side: {side}")
        print(f"   - Qty: {qty} contracts ({qty * 0.001:.4f} BTC)")
        print(f"   - Order Type: Market")

        # Order Link ID (클라이언트 ID)
        import time
        order_link_id = f"manual_{side.lower()}_{int(time.time())}"

        response = rest_client.place_order(
            symbol="BTCUSDT",
            side=side,
            qty=qty,
            order_link_id=order_link_id,
            order_type="Market",
            time_in_force="GoodTillCancel",
        )

        print(f"\n✅ Order response received!")
        print(f"   Full response: {response}")

        result = response.get("result", {})
        order_id = result.get("orderId", "N/A")
        order_link_id_resp = result.get("orderLinkId", "N/A")

        print(f"\n   - Order ID: {order_id}")
        print(f"   - Order Link ID: {order_link_id_resp}")

        # 주문 체결 확인 (2초 대기 후)
        print(f"\n⏳ Waiting for order execution (2 seconds)...")
        time.sleep(2.0)

        # Position 확인
        position_resp = rest_client.get_position(
            category="linear",
            symbol="BTCUSDT"
        )

        positions = position_resp.get("result", {}).get("list", [])
        if positions:
            position = positions[0]
            size = float(position.get("size", "0"))
            avg_price = float(position.get("avgPrice", "0"))
            unrealized_pnl = float(position.get("unrealisedPnl", "0"))

            print(f"\n📊 Position Status:")
            print(f"   - Size: {size} ({size * 0.001:.4f} BTC)")
            print(f"   - Avg Price: ${avg_price:,.2f} USD")
            print(f"   - Unrealized PnL: ${unrealized_pnl:,.2f} USDT")

            if size > 0:
                print(f"\n✅ Position opened successfully!")
                print(f"   → last_fill_price will be set to ${avg_price:,.2f}")
                print(f"   → Grid strategy can now activate!")
                return True
            else:
                print(f"\n⚠️  Position size = 0 (order may not be filled yet)")
                return False
        else:
            print(f"\n⚠️  No position found (order may not be filled yet)")
            return False

    except Exception as e:
        print(f"\n❌ Order placement failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Place manual order on Testnet")
    parser.add_argument(
        "--side",
        type=str,
        required=True,
        choices=["Buy", "Sell"],
        help="Order side (Buy or Sell)"
    )
    parser.add_argument(
        "--qty",
        type=int,
        default=1,
        help="Order quantity in contracts (default: 1, min: 1)"
    )

    args = parser.parse_args()

    # Validation
    if args.qty < 1:
        print("❌ ERROR: Quantity must be >= 1 contract")
        sys.exit(1)

    # Execute
    success = place_manual_order(side=args.side, qty=args.qty)

    if success:
        print(f"\n" + "=" * 70)
        print(f"✅ Manual Order Complete!")
        print(f"=" * 70)
        print(f"\n다음 단계:")
        print(f"  python scripts/run_testnet_dry_run.py --target-trades 5")
        print(f"  (Grid signal이 발생하면 자동 거래 시작)")
        sys.exit(0)
    else:
        print(f"\n" + "=" * 70)
        print(f"❌ Manual Order Failed")
        print(f"=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
