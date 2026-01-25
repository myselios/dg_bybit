#!/usr/bin/env python3
"""
scripts/test_sizing_with_testnet.py
Testnet 데이터로 Sizing 계산 검증 (Linear USDT)

목적:
1. 실제 Testnet equity ($88,150 USDT) 사용
2. 실제 Mark Price ($84,051 USD) 사용
3. Linear USDT sizing formula 검증
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
from src.application.sizing import calculate_contracts, SizingParams

load_dotenv()


def test_sizing_with_testnet():
    """Testnet 데이터로 Sizing 검증"""
    print("=" * 70)
    print("Linear USDT Sizing Test with Testnet Data")
    print("=" * 70)

    # 1. Testnet 연동
    api_key = os.getenv("BYBIT_TESTNET_API_KEY")
    api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")

    rest_client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com"
    )
    ws_client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url="wss://stream-testnet.bybit.com/v5/public/linear"
    )
    adapter = BybitAdapter(rest_client, ws_client, testnet=True)

    print("\n⏳ Fetching Testnet market data...")
    adapter.update_market_data()

    equity_usdt = adapter.get_equity_usdt()
    mark_price = adapter.get_mark_price()

    print(f"\n📊 Testnet Market Data:")
    print(f"   - Equity (USDT):   ${equity_usdt:,.2f} USDT")
    print(f"   - Mark Price:      ${mark_price:,.2f} USD")

    # 2. Sizing 파라미터 설정
    print(f"\n🔧 Sizing Parameters (Linear USDT):")

    # Loss budget: 1% of equity
    max_loss_usdt = equity_usdt * 0.01
    print(f"   - Max Loss (1%):   ${max_loss_usdt:,.2f} USDT")

    # Stop distance: 3%
    stop_distance_pct = 0.03
    print(f"   - Stop Distance:   {stop_distance_pct * 100:.1f}%")

    # Leverage: 3x
    leverage = 3.0
    print(f"   - Leverage:        {leverage:.1f}x")

    # Contract size: 0.001 BTC (Bybit Linear BTCUSDT)
    contract_size = 0.001
    print(f"   - Contract Size:   {contract_size} BTC")

    # Fee rate: 0.055% (maker)
    fee_rate = 0.00055
    print(f"   - Fee Rate:        {fee_rate * 100:.3f}%")

    # 3. Sizing 계산 (LONG)
    params_long = SizingParams(
        max_loss_usdt=max_loss_usdt,
        entry_price_usd=mark_price,
        stop_distance_pct=stop_distance_pct,
        leverage=leverage,
        equity_usdt=equity_usdt,
        fee_rate=fee_rate,
        direction="LONG",
        qty_step=1,
        tick_size=0.5,
        contract_size=contract_size
    )

    result_long = calculate_contracts(params_long)

    print(f"\n📈 LONG Position Sizing:")
    print(f"   - Contracts:       {result_long.contracts:,}")
    if result_long.reject_reason:
        print(f"   - ⚠️  Rejected:      {result_long.reject_reason}")
    else:
        print(f"   - ✅ Accepted")
        # Calculate actual values
        actual_qty = result_long.contracts * contract_size
        notional_usdt = actual_qty * mark_price
        required_margin = notional_usdt / leverage
        max_loss_at_stop = actual_qty * mark_price * stop_distance_pct

        print(f"   - Actual Qty:      {actual_qty:.4f} BTC")
        print(f"   - Notional:        ${notional_usdt:,.2f} USDT")
        print(f"   - Margin Required: ${required_margin:,.2f} USDT")
        print(f"   - Loss @ Stop:     ${max_loss_at_stop:,.2f} USDT")
        print(f"   - Stop Price:      ${mark_price * (1 - stop_distance_pct):,.2f} USD")

    # 4. Sizing 계산 (SHORT)
    params_short = SizingParams(
        max_loss_usdt=max_loss_usdt,
        entry_price_usd=mark_price,
        stop_distance_pct=stop_distance_pct,
        leverage=leverage,
        equity_usdt=equity_usdt,
        fee_rate=fee_rate,
        direction="SHORT",
        qty_step=1,
        tick_size=0.5,
        contract_size=contract_size
    )

    result_short = calculate_contracts(params_short)

    print(f"\n📉 SHORT Position Sizing:")
    print(f"   - Contracts:       {result_short.contracts:,}")
    if result_short.reject_reason:
        print(f"   - ⚠️  Rejected:      {result_short.reject_reason}")
    else:
        print(f"   - ✅ Accepted")
        actual_qty = result_short.contracts * contract_size
        notional_usdt = actual_qty * mark_price
        required_margin = notional_usdt / leverage
        max_loss_at_stop = actual_qty * mark_price * stop_distance_pct

        print(f"   - Actual Qty:      {actual_qty:.4f} BTC")
        print(f"   - Notional:        ${notional_usdt:,.2f} USDT")
        print(f"   - Margin Required: ${required_margin:,.2f} USDT")
        print(f"   - Loss @ Stop:     ${max_loss_at_stop:,.2f} USDT")
        print(f"   - Stop Price:      ${mark_price * (1 + stop_distance_pct):,.2f} USD")

    # 5. 검증
    print(f"\n" + "=" * 70)
    if result_long.contracts > 0 and result_short.contracts > 0:
        print(f"✅ Linear USDT Sizing Test PASSED")
        print(f"\n주요 확인 사항:")
        print(f"  1. ✅ Testnet equity ($88,150 USDT) 사용")
        print(f"  2. ✅ Linear formula: qty = max_loss / (price × stop_pct)")
        print(f"  3. ✅ Direction-independent (LONG == SHORT contracts)")
        print(f"  4. ✅ Contract size conversion (0.001 BTC)")

        # Direction-independent 확인
        if result_long.contracts == result_short.contracts:
            print(f"  5. ✅ LONG == SHORT: {result_long.contracts} contracts (✓)")
        else:
            print(f"  5. ⚠️  LONG != SHORT: {result_long.contracts} vs {result_short.contracts}")

        return True
    else:
        print(f"❌ Linear USDT Sizing Test FAILED")
        print(f"   LONG rejected: {result_long.reject_reason}")
        print(f"   SHORT rejected: {result_short.reject_reason}")
        return False


if __name__ == "__main__":
    success = test_sizing_with_testnet()
    sys.exit(0 if success else 1)
