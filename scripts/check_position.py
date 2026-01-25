#!/usr/bin/env python3
"""
scripts/check_position.py
Testnet Position 확인

목적:
- 현재 Position 상태 확인
- last_fill_price 설정 여부 확인
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
from dotenv import load_dotenv
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient

load_dotenv()


def check_position():
    """Testnet Position 확인"""
    print("=" * 70)
    print("Testnet Position Check")
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

    try:
        # Position 확인
        position_resp = rest_client.get_position(
            category="linear",
            symbol="BTCUSDT"
        )

        positions = position_resp.get("result", {}).get("list", [])

        if not positions:
            print("\n⚠️  No position found")
            print("   → 아직 체결되지 않았거나, Position이 없습니다.")
            return False

        position = positions[0]
        size_str = position.get("size", "0")
        size = float(size_str) if size_str else 0.0
        side = position.get("side", "None")
        avg_price_str = position.get("avgPrice", "0")
        avg_price = float(avg_price_str) if avg_price_str else 0.0
        unrealized_pnl_str = position.get("unrealisedPnl", "0")
        unrealized_pnl = float(unrealized_pnl_str) if unrealized_pnl_str else 0.0

        print(f"\n📊 Position Status:")
        print(f"   - Side: {side}")
        print(f"   - Size: {size} ({size * 0.001:.4f} BTC)")
        print(f"   - Avg Price: ${avg_price:,.2f} USD")
        print(f"   - Unrealized PnL: ${unrealized_pnl:,.2f} USDT")

        if size > 0:
            print(f"\n✅ Position found!")
            print(f"   → last_fill_price = ${avg_price:,.2f}")
            print(f"   → Grid strategy is ready!")
            return True
        else:
            print(f"\n⚠️  Position size = 0")
            print(f"   → Position이 청산되었거나, 아직 체결되지 않았습니다.")
            return False

    except Exception as e:
        print(f"\n❌ Failed to check position: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = check_position()
    sys.exit(0 if success else 1)
