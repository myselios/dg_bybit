#!/usr/bin/env python3
"""
scripts/check_all_executions.py
모든 체결 내역 확인 (필터 없음)
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
from dotenv import load_dotenv
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient

load_dotenv()


def check_all_executions():
    """모든 체결 내역 확인 (symbol/category 필터 없음)"""
    print("=" * 70)
    print("All Execution History Check")
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

    # Test 1: Linear BTCUSDT
    print("\n1️⃣ Linear BTCUSDT:")
    try:
        response = rest_client.get_execution_list(
            category="linear",
            symbol="BTCUSDT",
            limit=10
        )
        executions = response.get("result", {}).get("list", [])
        print(f"   Found {len(executions)} executions")
        if executions:
            latest = executions[0]
            print(f"   Latest: {latest.get('side')} {latest.get('execQty')} @ ${latest.get('execPrice')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 2: Inverse BTCUSD
    print("\n2️⃣ Inverse BTCUSD:")
    try:
        response = rest_client.get_execution_list(
            category="inverse",
            symbol="BTCUSD",
            limit=10
        )
        executions = response.get("result", {}).get("list", [])
        print(f"   Found {len(executions)} executions")
        if executions:
            latest = executions[0]
            print(f"   Latest: {latest.get('side')} {latest.get('execQty')} @ ${latest.get('execPrice')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 3: Linear 전체 (symbol 필터 없음)
    print("\n3️⃣ Linear All Symbols:")
    try:
        response = rest_client.get_execution_list(
            category="linear",
            limit=10
        )
        executions = response.get("result", {}).get("list", [])
        print(f"   Found {len(executions)} executions")
        if executions:
            for i, exec in enumerate(executions[:3], 1):
                print(f"   {i}. {exec.get('symbol')} {exec.get('side')} {exec.get('execQty')} @ ${exec.get('execPrice')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 4: Inverse 전체 (symbol 필터 없음)
    print("\n4️⃣ Inverse All Symbols:")
    try:
        response = rest_client.get_execution_list(
            category="inverse",
            limit=10
        )
        executions = response.get("result", {}).get("list", [])
        print(f"   Found {len(executions)} executions")
        if executions:
            for i, exec in enumerate(executions[:3], 1):
                print(f"   {i}. {exec.get('symbol')} {exec.get('side')} {exec.get('execQty')} @ ${exec.get('execPrice')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    check_all_executions()
