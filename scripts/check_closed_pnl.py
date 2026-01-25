#!/usr/bin/env python3
"""
scripts/check_closed_pnl.py
청산된 거래 내역 확인

목적:
- Closed PnL 확인
- 청산 시각, 가격 확인
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
from dotenv import load_dotenv
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient

load_dotenv()


def check_closed_pnl():
    """청산된 거래 내역 확인"""
    print("=" * 70)
    print("Closed PnL Check")
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
        # Execution list 가져오기 (closedSize > 0인 것만)
        response = rest_client.get_execution_list(
            category="linear",
            symbol="BTCUSDT",
            limit=50
        )

        executions = response.get("result", {}).get("list", [])

        if not executions:
            print("\n⚠️  No execution history found")
            return False

        # 청산 내역 필터링
        closures = []
        for exec in executions:
            closed_size = exec.get("closedSize", "0")
            if closed_size and float(closed_size) > 0:
                closures.append(exec)

        print(f"\n📊 Total Executions: {len(executions)}")
        print(f"📊 Closed Positions: {len(closures)}")
        print("-" * 70)

        if closures:
            total_closed_pnl = 0.0
            for i, closure in enumerate(closures, 1):
                order_id = closure.get("orderId", "N/A")
                side = closure.get("side", "N/A")
                exec_qty = closure.get("execQty", "0")
                exec_price = closure.get("execPrice", "0")
                closed_size = closure.get("closedSize", "0")
                closed_pnl = closure.get("closedPnl", "0")
                exec_time = closure.get("execTime", "0")

                print(f"\n{i}. Closed Position:")
                print(f"   - Side: {side}")
                print(f"   - Exec Qty: {exec_qty} BTC")
                print(f"   - Exec Price: ${exec_price}")
                print(f"   - Closed Size: {closed_size} BTC")
                print(f"   - Closed PnL: ${closed_pnl} USDT")
                print(f"   - Time: {exec_time}")

                if closed_pnl:
                    total_closed_pnl += float(closed_pnl)

            print(f"\n" + "=" * 70)
            print(f"Total Closed PnL: ${total_closed_pnl:.2f} USDT")
        else:
            print("\n⚠️  No closed positions found")
            print("   → Position이 청산되지 않았습니다.")

        # 모든 execution 요약
        print(f"\n" + "=" * 70)
        print(f"All Executions Summary:")
        print("-" * 70)

        buy_qty = 0.0
        sell_qty = 0.0
        for exec in executions:
            side = exec.get("side", "")
            exec_qty = exec.get("execQty", "0")
            if side == "Buy":
                buy_qty += float(exec_qty)
            elif side == "Sell":
                sell_qty += float(exec_qty)

        print(f"Total Buy:  {buy_qty:.4f} BTC")
        print(f"Total Sell: {sell_qty:.4f} BTC")
        print(f"Net Position: {buy_qty - sell_qty:.4f} BTC")

        return True

    except Exception as e:
        print(f"\n❌ Failed to check closed PnL: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = check_closed_pnl()
    sys.exit(0 if success else 1)
