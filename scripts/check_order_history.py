#!/usr/bin/env python3
"""
scripts/check_order_history.py
Testnet 주문 히스토리 확인

목적:
- 최근 주문 체결 여부 확인
- 주문 상태 (Filled, Cancelled, Rejected) 확인
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
from dotenv import load_dotenv
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient

load_dotenv()


def check_order_history():
    """Testnet 주문 히스토리 확인"""
    print("=" * 70)
    print("Testnet Order History Check")
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
        # 최근 체결 내역 확인 (최근 10개)
        response = rest_client.get_execution_list(
            category="linear",
            symbol="BTCUSDT",
            limit=10
        )

        executions = response.get("result", {}).get("list", [])

        if not executions:
            print("\n⚠️  No execution history found")
            print("   → 아직 체결된 주문이 없습니다.")
            return False

        print(f"\n📊 Recent Executions (last {len(executions)}):")
        print("-" * 70)

        for i, exec in enumerate(executions, 1):
            order_id = exec.get("orderId", "N/A")
            order_link_id = exec.get("orderLinkId", "N/A")
            side = exec.get("side", "N/A")
            exec_type = exec.get("execType", "N/A")
            exec_qty = exec.get("execQty", "0")
            exec_price = exec.get("execPrice", "0")
            closed_pnl = exec.get("closedSize", "0")
            exec_time = exec.get("execTime", "0")

            print(f"\n{i}. Execution:")
            print(f"   - Order ID: {order_id}")
            print(f"   - Order Link ID: {order_link_id}")
            print(f"   - Side: {side} ({exec_type})")
            print(f"   - Exec Qty: {exec_qty}")
            print(f"   - Exec Price: ${exec_price}")
            print(f"   - Exec Time: {exec_time}")

        # 가장 최근 체결이 있으면 성공
        latest_exec = executions[0]
        print(f"\n✅ Found {len(executions)} execution(s)!")
        print(f"   → Latest Exec Price: ${latest_exec.get('execPrice', '0')}")
        print(f"   → Latest Exec Qty: {latest_exec.get('execQty', '0')}")
        return True

    except Exception as e:
        print(f"\n❌ Failed to check order history: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = check_order_history()
    sys.exit(0 if success else 1)
