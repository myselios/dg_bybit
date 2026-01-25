#!/usr/bin/env python3
"""
scripts/check_orchestrator_state.py
Orchestrator 현재 상태 확인

목적:
- Position 존재 여부 → IN_POSITION 상태 확인
- Stop loss 설정 여부 확인
- Grid signal 확인
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
from dotenv import load_dotenv
from pathlib import Path
from src.application.orchestrator import Orchestrator
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient
from src.infrastructure.exchange.bybit_ws_client import BybitWsClient
from src.infrastructure.exchange.bybit_adapter import BybitAdapter
from src.infrastructure.storage.log_storage import LogStorage

load_dotenv()


def check_orchestrator_state():
    """Orchestrator 상태 확인"""
    print("=" * 70)
    print("Orchestrator State Check")
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

    # LogStorage 초기화
    log_dir = Path("logs/testnet_dry_run")
    log_storage = LogStorage(log_dir=log_dir)

    # Orchestrator 초기화
    print("\n⏳ Initializing Orchestrator...")
    bybit_adapter.update_market_data()

    orchestrator = Orchestrator(
        market_data=bybit_adapter,
        rest_client=rest_client,
        log_storage=log_storage,
    )

    # 현재 상태 출력
    print(f"\n📊 Orchestrator Status:")
    print(f"   - Current State: {orchestrator.state}")

    # Position 확인
    mark_price = bybit_adapter.get_mark_price()
    position = bybit_adapter._current_position

    if position:
        size = float(position.get("size", "0"))
        side = position.get("side", "None")
        avg_price = float(position.get("avgPrice", "0") or "0")

        print(f"\n📊 Position Info:")
        print(f"   - Size: {size:.4f} BTC")
        print(f"   - Side: {side}")
        print(f"   - Avg Price: ${avg_price:,.2f}")
        print(f"   - Mark Price: ${mark_price:,.2f}")

        if size > 0:
            print(f"\n✅ Position exists → State should be IN_POSITION")
        else:
            print(f"\n⚠️  No position → State should be FLAT")

    # Grid signal 확인
    last_fill_price = bybit_adapter.get_last_fill_price()
    atr = bybit_adapter.get_atr()

    print(f"\n📊 Grid Signal:")
    print(f"   - Last Fill: ${last_fill_price:,.2f}" if last_fill_price else "   - Last Fill: None")
    print(f"   - ATR: ${atr:,.2f}" if atr else "   - ATR: None")

    if last_fill_price and atr:
        grid_spacing = 2 * atr
        price_diff = abs(mark_price - last_fill_price)

        print(f"   - Grid Spacing: ${grid_spacing:,.2f}")
        print(f"   - Price Diff: ${price_diff:,.2f}")

        if price_diff >= grid_spacing:
            print(f"\n✅ Grid signal triggered!")
        else:
            print(f"\n⚠️  Grid signal NOT triggered")

    # Single tick 실행
    print(f"\n⏳ Running single tick...")
    result = orchestrator.run_tick()

    print(f"\n📊 Tick Result:")
    print(f"   - State: {result.state}")
    print(f"   - Execution Order: {result.execution_order}")

    if result.halt_reason:
        print(f"   - ⚠️  HALT: {result.halt_reason}")

    if result.entry_blocked:
        print(f"   - Entry Blocked: {result.entry_block_reason}")

    if result.exit_intent:
        print(f"   - Exit Intent: {result.exit_intent}")

    print(f"\n" + "=" * 70)
    return True


if __name__ == "__main__":
    success = check_orchestrator_state()
    sys.exit(0 if success else 1)
