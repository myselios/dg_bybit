#!/usr/bin/env python3
"""
scripts/run_testnet_dry_run.py
Phase 12a: Testnet Dry-Run Script

목표:
- Testnet에서 30-50회 거래 실행
- Session Risk 발동 증거 확보
- 로그 완전성 검증

실행:
    python scripts/run_testnet_dry_run.py --target-trades 30
"""

import argparse
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

from dotenv import load_dotenv
from application.orchestrator import Orchestrator
from infrastructure.exchange.bybit_rest_client import BybitRestClient
from infrastructure.exchange.bybit_ws_client import BybitWsClient
from infrastructure.exchange.bybit_adapter import BybitAdapter
from infrastructure.storage.log_storage import LogStorage
from domain.state import State

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/testnet_dry_run.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DryRunMonitor:
    """Dry-Run 모니터링 및 통계"""

    def __init__(self):
        self.total_trades = 0
        self.successful_cycles = 0
        self.failed_cycles = 0
        self.session_risk_halts = 0
        self.emergency_halts = 0
        self.stop_loss_hits = 0
        self.start_time = datetime.now(timezone.utc)

    def log_cycle_complete(self, pnl_usd: float):
        """Full cycle 완료 기록"""
        self.successful_cycles += 1
        self.total_trades += 1
        logger.info(f"✅ Cycle {self.total_trades} complete | PnL: ${pnl_usd:.2f}")

    def log_halt(self, reason: str):
        """HALT 발생 기록"""
        if "session_risk" in reason.lower():
            self.session_risk_halts += 1
            logger.warning(f"⚠️ Session Risk HALT: {reason}")
        else:
            self.emergency_halts += 1
            logger.error(f"🚨 Emergency HALT: {reason}")

    def log_stop_hit(self):
        """Stop loss hit 기록"""
        self.stop_loss_hits += 1
        logger.info(f"🛑 Stop loss hit (total: {self.stop_loss_hits})")

    def print_summary(self):
        """통계 요약 출력"""
        duration = datetime.now(timezone.utc) - self.start_time
        logger.info("=" * 60)
        logger.info("Testnet Dry-Run Summary")
        logger.info("=" * 60)
        logger.info(f"Total trades: {self.total_trades}")
        logger.info(f"Successful cycles: {self.successful_cycles}")
        logger.info(f"Failed cycles: {self.failed_cycles}")
        logger.info(f"Stop loss hits: {self.stop_loss_hits}")
        logger.info(f"Session Risk halts: {self.session_risk_halts}")
        logger.info(f"Emergency halts: {self.emergency_halts}")
        logger.info(f"Duration: {duration}")
        logger.info("=" * 60)


def run_dry_run(target_trades: int = 30, max_duration_hours: int = 72, force_entry: bool = False):
    """
    Testnet Dry-Run 실행

    Args:
        target_trades: 목표 거래 횟수 (default: 30)
        max_duration_hours: 최대 실행 시간 (default: 72시간 = 3일)
        force_entry: Force Entry 모드 (테스트용, Grid spacing 무시)
    """
    logger.info(f"🚀 Starting Testnet Dry-Run (target: {target_trades} trades)")

    if force_entry:
        logger.warning("⚠️  Force Entry Mode: Grid spacing ignored (TEST MODE ONLY)")

    # Log storage 초기화
    log_dir = Path("logs/testnet_dry_run")
    log_storage = LogStorage(log_dir=log_dir)

    # REST/WS 클라이언트 초기화 (실제 Testnet 연결)
    import os
    api_key = os.getenv("BYBIT_TESTNET_API_KEY")
    api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")

    if not api_key or not api_secret:
        logger.error("❌ BYBIT_TESTNET_API_KEY and BYBIT_TESTNET_API_SECRET required in .env")
        return

    rest_client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com",
    )
    ws_client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url="wss://stream-testnet.bybit.com/v5/private",
        category="linear",  # BTCUSDT Linear Futures
    )

    # BybitAdapter 초기화 (Phase 12a-2 통합)
    bybit_adapter = BybitAdapter(
        rest_client=rest_client,
        ws_client=ws_client,
        testnet=True
    )

    # Orchestrator 초기화 (BybitAdapter 사용)
    orchestrator = Orchestrator(
        market_data=bybit_adapter,
        rest_client=rest_client,
        log_storage=log_storage,
        force_entry=force_entry,  # Phase 12a-4: Force Entry 모드 전달
    )

    # Market data 초기 로드 (equity, mark price 조회)
    logger.info("📊 Loading initial market data...")
    bybit_adapter.update_market_data()
    logger.info(f"✅ Equity: ${bybit_adapter.get_equity_usdt():.2f} USDT")

    # WebSocket 시작 (execution events 수신)
    logger.info("🔌 Starting WebSocket connection...")
    ws_client.start()
    # Wait for connection/auth/subscribe (3초 대기)
    time.sleep(3)
    if ws_client.is_connected():
        logger.info("✅ WebSocket connected and subscribed to execution.linear")
    else:
        logger.warning("⚠️ WebSocket connection in progress...")

    # Monitor 초기화
    monitor = DryRunMonitor()

    # Previous state tracking (State 전환 감지용)
    previous_state = State.FLAT

    # Main loop
    start_time = time.time()
    max_duration_seconds = max_duration_hours * 3600

    try:
        logger.info("🔄 Starting main loop...")
        while monitor.total_trades < target_trades:
            # 시간 제한 체크
            if time.time() - start_time > max_duration_seconds:
                logger.warning(f"⏰ Time limit reached ({max_duration_hours}h)")
                break

            # Tick 실행
            logger.info(f">>> Executing Tick #{monitor.total_trades+1}")
            try:
                logger.info(">>> Calling orchestrator.run_tick()...")
                result = orchestrator.run_tick()
                logger.info(f">>> Tick complete: state={result.state}, entry_blocked={result.entry_blocked}")
                current_state = result.state
            except Exception as e:
                logger.error(f"❌ Tick execution failed: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                break

            # HALT 감지
            if current_state == State.HALT:
                halt_reason = result.halt_reason or "Unknown"
                monitor.log_halt(halt_reason)
                logger.error(f"🚨 HALT detected: {halt_reason}")
                # HALT 발생 시 중단 (또는 복구 로직 추가 가능)
                break

            # State 전환 감지 (FLAT → Entry → Exit → FLAT 사이클)
            if previous_state != State.FLAT and current_state == State.FLAT:
                # Full cycle 완료 (IN_POSITION or ENTRY_PENDING → FLAT)
                # PnL 계산 (마지막 trade log에서 가져오기)
                trade_logs = log_storage.read_trade_logs_v1()
                if trade_logs:
                    last_trade = trade_logs[-1]
                    pnl_usd = last_trade.get("realized_pnl_usd", 0.0)
                    monitor.log_cycle_complete(pnl_usd)

            # Stop loss hit 감지 (exit_intent 확인)
            if result.exit_intent and result.exit_intent.reason == "STOP_LOSS":
                monitor.log_stop_hit()

            # Previous state 업데이트
            previous_state = current_state

            # Tick interval (1초)
            time.sleep(1.0)

    except KeyboardInterrupt:
        logger.info("🛑 Dry-Run interrupted by user")

    finally:
        # 최종 통계 출력
        monitor.print_summary()

        # Trade log 검증
        verify_trade_logs(log_storage, expected_count=monitor.successful_cycles)


def verify_trade_logs(log_storage: LogStorage, expected_count: int):
    """Trade log 완전성 검증"""
    logger.info("📊 Verifying trade logs...")

    trade_logs = log_storage.read_trade_logs_v1()
    actual_count = len(trade_logs)

    if actual_count == expected_count:
        logger.info(f"✅ Trade log completeness: {actual_count}/{expected_count}")
    else:
        logger.error(f"❌ Trade log mismatch: {actual_count}/{expected_count}")
        logger.error("Some trades were NOT logged!")


def main():
    parser = argparse.ArgumentParser(description="Testnet Dry-Run")
    parser.add_argument(
        "--target-trades",
        type=int,
        default=30,
        help="Target number of trades (default: 30)"
    )
    parser.add_argument(
        "--max-hours",
        type=int,
        default=72,
        help="Maximum duration in hours (default: 72)"
    )
    parser.add_argument(
        "--force-entry",
        action="store_true",
        help="Force Entry mode (TEST MODE ONLY, bypasses Grid spacing check)"
    )

    args = parser.parse_args()

    run_dry_run(
        target_trades=args.target_trades,
        max_duration_hours=args.max_hours,
        force_entry=args.force_entry,
    )


if __name__ == "__main__":
    main()
