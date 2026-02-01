#!/usr/bin/env python3
"""
scripts/force_close_position.py
기존 포지션을 강제 청산하는 긴급 스크립트

사용법:
    python scripts/force_close_position.py --testnet
    python scripts/force_close_position.py --mainnet (⚠️ 실거래 주의!)
"""

import argparse
import os
from dotenv import load_dotenv
from infrastructure.exchange.bybit_rest_client import BybitRestClient

load_dotenv()

def close_all_positions(testnet=True):
    """모든 포지션 강제 청산"""

    if testnet:
        api_key = os.getenv("BYBIT_TESTNET_API_KEY")
        api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")
        base_url = "https://api-testnet.bybit.com"
        print("🔧 Testnet 모드")
    else:
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")
        base_url = "https://api.bybit.com"
        print("⚠️ MAINNET 모드 (실제 거래!)")

    if not api_key or not api_secret:
        print("❌ API 키가 설정되지 않았습니다")
        return

    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url,
    )

    # 1. 현재 포지션 조회
    print("\n📊 현재 포지션 조회 중...")
    pos_response = client.get_position(symbol="BTCUSDT", category="linear")

    if pos_response["retCode"] != 0:
        print(f"❌ 포지션 조회 실패: {pos_response['retMsg']}")
        return

    positions = pos_response["result"]["list"]

    if not positions or len(positions) == 0:
        print("✅ 포지션 없음 (이미 청산됨)")
        return

    pos = positions[0]
    size_btc = float(pos.get("size", "0"))

    if size_btc == 0:
        print("✅ 포지션 없음 (size=0)")
        return

    # 2. 포지션 정보 출력
    side = pos.get("side", "")
    entry_price = float(pos.get("avgPrice", "0"))
    mark_price = float(pos.get("markPrice", "0"))
    unrealized_pnl = float(pos.get("unrealisedPnl", "0"))

    print(f"\n📍 발견된 포지션:")
    print(f"  Side: {side}")
    print(f"  Size: {size_btc} BTC")
    print(f"  Entry Price: ${entry_price:,.2f}")
    print(f"  Mark Price: ${mark_price:,.2f}")
    print(f"  Unrealized PnL: ${unrealized_pnl:,.2f}")

    # 3. 청산 확인
    confirm = input(f"\n⚠️ 이 포지션을 Market Order로 청산하시겠습니까? (yes/no): ")
    if confirm.lower() != "yes":
        print("❌ 취소됨")
        return

    # 4. Market Order로 청산
    print(f"\n🔨 청산 중... (Market Order)")

    close_side = "Sell" if side == "Buy" else "Buy"

    try:
        result = client.place_order(
            symbol="BTCUSDT",
            category="linear",
            side=close_side,
            order_type="Market",
            qty=str(size_btc),
            reduce_only=True,
        )

        if result.get("retCode") == 0:
            order_id = result["result"]["orderId"]
            print(f"✅ 청산 주문 성공!")
            print(f"  Order ID: {order_id}")
            print(f"  Side: {close_side}")
            print(f"  Qty: {size_btc} BTC")
        else:
            print(f"❌ 청산 실패: {result.get('retMsg')}")
    except Exception as e:
        print(f"❌ 청산 오류: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Force close all positions")
    parser.add_argument("--testnet", action="store_true", help="Use Testnet")
    parser.add_argument("--mainnet", action="store_true", help="Use Mainnet (⚠️ Real money!)")

    args = parser.parse_args()

    if args.mainnet:
        print("⚠️⚠️⚠️ MAINNET 모드 - 실제 거래! ⚠️⚠️⚠️")
        confirm = input("정말로 Mainnet 포지션을 청산하시겠습니까? (YES 입력): ")
        if confirm != "YES":
            print("❌ 취소됨")
            exit(0)
        close_all_positions(testnet=False)
    elif args.testnet:
        close_all_positions(testnet=True)
    else:
        print("❌ --testnet 또는 --mainnet 플래그 필요")
        print("예: python scripts/force_close_position.py --testnet")
