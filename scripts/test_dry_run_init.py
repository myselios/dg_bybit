#!/usr/bin/env python3
"""
scripts/test_dry_run_init.py
Dry-Run 초기화 테스트 (Phase 12a-4)

목적:
- run_testnet_dry_run.py 초기화 단계만 테스트
- Testnet 연결 확인
- Orchestrator 생성 확인
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
import logging
from dotenv import load_dotenv
from src.application.orchestrator import Orchestrator
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient
from src.infrastructure.exchange.bybit_ws_client import BybitWsClient
from src.infrastructure.exchange.bybit_adapter import BybitAdapter
from src.infrastructure.storage.log_storage import LogStorage

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_dry_run_init():
    """Dry-Run 초기화 테스트"""
    print("=" * 70)
    print("Testnet Dry-Run Initialization Test")
    print("=" * 70)

    # 1. API Credentials
    api_key = os.getenv("BYBIT_TESTNET_API_KEY")
    api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")

    if not api_key or not api_secret:
        print("❌ Testnet API credentials not found in .env")
        return False

    print("\n✅ Step 1: API credentials loaded")

    # 2. Log Storage
    log_dir = Path("logs/testnet_dry_run")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_storage = LogStorage(log_dir=log_dir)
    print(f"✅ Step 2: LogStorage initialized ({log_dir})")

    # 3. REST Client
    base_url = "https://api-testnet.bybit.com"
    rest_client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url
    )
    print(f"✅ Step 3: REST Client initialized (Testnet)")

    # 4. WebSocket Client
    wss_url = "wss://stream-testnet.bybit.com/v5/public/linear"
    ws_client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url=wss_url
    )
    print(f"✅ Step 4: WebSocket Client initialized")

    # 5. BybitAdapter
    bybit_adapter = BybitAdapter(
        rest_client=rest_client,
        ws_client=ws_client,
        testnet=True
    )
    print(f"✅ Step 5: BybitAdapter initialized")

    # 6. Market Data Update
    try:
        bybit_adapter.update_market_data()
        equity_usdt = bybit_adapter.get_equity_usdt()
        mark_price = bybit_adapter.get_mark_price()
        print(f"✅ Step 6: Market data updated")
        print(f"   - Equity: ${equity_usdt:,.2f} USDT")
        print(f"   - Mark Price: ${mark_price:,.2f} USD")
    except Exception as e:
        print(f"❌ Step 6 FAILED: {e}")
        return False

    # 7. Orchestrator 초기화
    try:
        orchestrator = Orchestrator(
            market_data=bybit_adapter,
            rest_client=rest_client,
            log_storage=log_storage,
        )
        print(f"✅ Step 7: Orchestrator initialized")
        print(f"   - Initial state: {orchestrator.state}")
    except Exception as e:
        print(f"❌ Step 7 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 8. Single Tick Test
    try:
        print(f"\n⏳ Step 8: Running single tick test...")
        result = orchestrator.run_tick()
        print(f"✅ Step 8: Single tick executed successfully")
        print(f"   - State after tick: {result.state}")
        print(f"   - Entry blocked: {result.entry_blocked}")
        if result.entry_blocked:
            print(f"   - Block reason: {result.entry_block_reason}")
        if result.halt_reason:
            print(f"   - ⚠️  HALT reason: {result.halt_reason}")
    except Exception as e:
        print(f"❌ Step 8 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Success
    print(f"\n" + "=" * 70)
    print(f"✅ Dry-Run Initialization Test PASSED")
    print(f"=" * 70)
    print(f"\n다음 단계:")
    print(f"  python scripts/run_testnet_dry_run.py --target-trades 5")
    print(f"  (소규모 테스트: 5회 거래)")

    return True


if __name__ == "__main__":
    success = test_dry_run_init()
    sys.exit(0 if success else 1)
