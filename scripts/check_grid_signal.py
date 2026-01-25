#!/usr/bin/env python3
"""
scripts/check_grid_signal.py
Grid Signal 발생 여부 확인

목적:
- last_fill_price 설정 확인
- Grid signal 발생 조건 확인
- ATR, spacing 계산 확인
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
from dotenv import load_dotenv
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient
from src.infrastructure.exchange.bybit_ws_client import BybitWsClient
from src.infrastructure.exchange.bybit_adapter import BybitAdapter

load_dotenv()


def check_grid_signal():
    """Grid Signal 발생 여부 확인"""
    print("=" * 70)
    print("Grid Signal Check")
    print("=" * 70)

    # Testnet credentials
    api_key = os.getenv("BYBIT_TESTNET_API_KEY")
    api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")

    if not api_key or not api_secret:
        print("❌ ERROR: Testnet API credentials not found in .env")
        return False

    # REST/WS Client 초기화
    base_url = "https://api-testnet.bybit.com"
    wss_url = "wss://stream-testnet.bybit.com/v5/public/linear"

    rest_client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url
    )
    ws_client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url=wss_url
    )

    # BybitAdapter 초기화
    bybit_adapter = BybitAdapter(
        rest_client=rest_client,
        ws_client=ws_client,
        testnet=True
    )

    # Market data 업데이트
    print("\n⏳ Updating market data...")
    bybit_adapter.update_market_data()

    # 1. 기본 정보
    mark_price = bybit_adapter.get_mark_price()
    last_fill_price = bybit_adapter.get_last_fill_price()
    atr = bybit_adapter.get_atr()

    print(f"\n📊 Market Data:")
    print(f"   - Mark Price:      ${mark_price:,.2f} USD")
    print(f"   - Last Fill Price: ${last_fill_price:,.2f} USD" if last_fill_price else "   - Last Fill Price: None")
    print(f"   - ATR:             ${atr:,.2f} USD" if atr else "   - ATR: None")

    # 2. Grid signal 조건 확인
    if last_fill_price is None:
        print(f"\n⚠️  Last fill price is None → No Grid signal possible")
        return False

    if atr is None:
        print(f"\n⚠️  ATR is None → No Grid signal possible")
        return False

    # Grid spacing: 2 × ATR
    grid_spacing = 2 * atr
    price_diff = abs(mark_price - last_fill_price)
    diff_pct = (price_diff / last_fill_price) * 100

    print(f"\n🔍 Grid Signal Analysis:")
    print(f"   - Grid Spacing:    ${grid_spacing:,.2f} USD (2 × ATR)")
    print(f"   - Price Diff:      ${price_diff:,.2f} USD ({diff_pct:.2f}%)")
    print(f"   - Condition:       |current - last_fill| >= 2 × ATR")
    print(f"   - Check:           ${price_diff:,.2f} >= ${grid_spacing:,.2f}")

    if price_diff >= grid_spacing:
        print(f"\n✅ Grid signal SHOULD TRIGGER!")
        if mark_price > last_fill_price:
            print(f"   → Direction: SELL (Grid down, price went up)")
        else:
            print(f"   → Direction: BUY (Grid up, price went down)")
        return True
    else:
        print(f"\n⚠️  Grid signal NOT triggered")
        print(f"   → Need ${grid_spacing - price_diff:,.2f} more price movement")
        return False


if __name__ == "__main__":
    success = check_grid_signal()
    sys.exit(0 if success else 1)
