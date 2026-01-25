#!/usr/bin/env python3
"""
scripts/debug_signature.py
Bybit Signature 생성 디버그

목적:
- 서명 생성 방식 확인
- origin_string 순서 확인
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import hmac
import hashlib
import time

# Test data
timestamp = int(time.time() * 1000)
api_key = "TEST_API_KEY"
api_secret = "TEST_API_SECRET"

params = {
    "category": "linear",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "orderType": "Market",
    "qty": 1,
    "timeInForce": "GoodTillCancel",
    "orderLinkId": "manual_buy_123456"
}

print("=" * 70)
print("Bybit V5 POST Signature Debug")
print("=" * 70)

print(f"\n1. Original params dict:")
print(f"   {params}")

print(f"\n2. JSON with separators=(',', ':'), sort_keys=True:")
params_json = json.dumps(params, separators=(',', ':'), sort_keys=True)
print(f"   {params_json}")

print(f"\n3. Origin string (timestamp + apiKey + recvWindow + JSON):")
recv_window = 5000
origin_string = f"{timestamp}{api_key}{recv_window}{params_json}"
print(f"   {origin_string}")

print(f"\n4. Signature (HMAC SHA256):")
signature = hmac.new(
    api_secret.encode("utf-8"),
    origin_string.encode("utf-8"),
    hashlib.sha256,
).hexdigest()
print(f"   {signature}")

print(f"\n5. 예상 origin_string (Bybit 에러 메시지 형식):")
expected = f'{timestamp}{api_key}{recv_window}{{"category":"linear","orderLinkId":"manual_buy_123456","orderType":"Market","qty":1,"side":"Buy","symbol":"BTCUSDT","timeInForce":"GoodTillCancel"}}'
print(f"   {expected}")

print(f"\n6. Match: {origin_string == expected}")
