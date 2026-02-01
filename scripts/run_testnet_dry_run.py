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
from infrastructure.notification.telegram_notifier import TelegramNotifier
from domain.state import State

# Load environment variables (명시적 경로 + override)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

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

    def __init__(self, initial_equity: float):
        self.total_trades = 0
        self.successful_cycles = 0
        self.failed_cycles = 0
        self.session_risk_halts = 0
        self.emergency_halts = 0
        self.stop_loss_hits = 0
        self.start_time = datetime.now(timezone.utc)

        # 포트폴리오 추적
        self.initial_equity = initial_equity
        self.cumulative_pnl_usd = 0.0
        self.entry_time = None  # Entry 시간 추적 (보유 시간 계산용)
        self.entry_price = None  # Entry 가격 추적

    def log_cycle_complete(self, pnl_usd: float):
        """Full cycle 완료 기록"""
        self.successful_cycles += 1
        self.total_trades += 1
        self.cumulative_pnl_usd += pnl_usd
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

    def log_entry(self, entry_price: float):
        """Entry 기록 (진입 시간 및 가격 추적)"""
        self.entry_time = datetime.now(timezone.utc)
        self.entry_price = entry_price

    def get_hold_duration(self) -> str:
        """보유 시간 계산 (한글 포맷)"""
        if not self.entry_time:
            return "0분"

        duration = datetime.now(timezone.utc) - self.entry_time
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        if hours > 0:
            return f"{hours}시간 {minutes}분"
        else:
            return f"{minutes}분"

    def get_portfolio_snapshot(
        self, wallet_balance: float, positions_count: int, total_invested: float, total_value: float
    ) -> Dict[str, Any]:
        """
        포트폴리오 스냅샷 반환

        Args:
            wallet_balance: USDT 잔고 (BybitAdapter에서 조회)
            positions_count: 보유 포지션 개수 (0 or 1)
            total_invested: 투자 금액 (포지션 size * entry_price)
            total_value: 평가 금액 (포지션 size * current_price)

        Returns:
            Dict: 포트폴리오 정보
        """
        total_pnl_pct = (
            (self.cumulative_pnl_usd / self.initial_equity) * 100 if self.initial_equity > 0 else 0.0
        )

        return {
            "wallet_balance": wallet_balance,
            "positions_count": positions_count,
            "total_invested": total_invested,
            "total_value": total_value,
            "total_pnl_pct": total_pnl_pct,
            "total_pnl_usd": self.cumulative_pnl_usd,
        }

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


def run_dry_run(target_trades: int = 30, max_duration_hours: int = 72):
    """
    Testnet Dry-Run 실행

    Args:
        target_trades: 목표 거래 횟수 (default: 30)
        max_duration_hours: 최대 실행 시간 (default: 72시간 = 3일)
    """
    logger.info(f"🚀 Starting Testnet Dry-Run (target: {target_trades} trades)")

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
    )

    # Market data 초기 로드 (equity, mark price 조회)
    logger.info("📊 Loading initial market data...")
    bybit_adapter.update_market_data()

    # Phase 13b: 이전 체결 가격 무시 (Clean start)
    bybit_adapter._last_fill_price = None

    initial_equity = bybit_adapter.get_equity_usdt()
    logger.info(f"✅ Equity: ${initial_equity:.2f} USDT")

    # WebSocket 시작 (execution events 수신)
    logger.info("🔌 Starting WebSocket connection...")
    ws_client.start()
    # Wait for connection/auth/subscribe (3초 대기)
    time.sleep(3)
    if ws_client.is_connected():
        logger.info("✅ WebSocket connected and subscribed to execution.linear")
    else:
        logger.warning("⚠️ WebSocket connection in progress...")

    # Monitor 초기화 (initial_equity 전달)
    monitor = DryRunMonitor(initial_equity=initial_equity)

    # Telegram notifier 초기화 (환경변수 자동 로드)
    telegram = TelegramNotifier()
    if telegram.enabled:
        logger.info("✅ Telegram notifier enabled")
    else:
        logger.info("ℹ️ Telegram notifier disabled (no bot token/chat ID)")

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
                logger.info(f">>> Tick complete: state={result.state}, entry_blocked={result.entry_blocked}, entry_block_reason={result.entry_block_reason}")
                current_state = result.state

                # Entry 차단 이유 로깅 (처음 20 tick만)
                if result.entry_blocked and tick_count <= 20:
                    if result.entry_block_reason == "atr_too_low":
                        atr_pct = bybit_adapter.get_atr_pct_24h()
                        logger.info(f"  → Entry blocked: {result.entry_block_reason} (ATR: {atr_pct:.2f}% < 3.0%)")
                    elif result.entry_block_reason == "no_signal":
                        # Regime-aware entry debug: 실제 ma_slope_pct, funding_rate 값 표시
                        ma_slope = bybit_adapter.get_ma_slope_pct()
                        funding = bybit_adapter.get_funding_rate()
                        logger.info(f"  → Entry blocked: no_signal (ma_slope={ma_slope:.4f}%, funding={funding:.6f})")
                    else:
                        logger.info(f"  → Entry blocked: {result.entry_block_reason}")

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

                # Telegram HALT 알림
                equity = bybit_adapter.get_equity_usdt()
                telegram.send_halt(reason=halt_reason, equity=equity)

                # HALT 발생 시 중단 (또는 복구 로직 추가 가능)
                break

            # State 전환 감지: Entry (? → IN_POSITION)
            logger.debug(f"🔍 State check: previous={previous_state}, current={current_state}")
            if previous_state != State.IN_POSITION and current_state == State.IN_POSITION:
                if orchestrator.position:
                    # Convert Direction to side string
                    from domain.state import Direction
                    side_str = "Buy" if orchestrator.position.direction == Direction.LONG else "Sell"

                    # Entry 근거 생성
                    entry_reason = f"Grid {side_str}: 목표가 ${orchestrator.position.entry_price:,.2f} 도달"

                    # Entry 시간 추적
                    monitor.log_entry(orchestrator.position.entry_price)

                    # 포트폴리오 정보 조회
                    bybit_adapter.update_market_data()
                    wallet_balance = bybit_adapter.get_equity_usdt()
                    position_qty_btc = orchestrator.position.qty / 1000  # contracts to BTC
                    total_invested = position_qty_btc * orchestrator.position.entry_price
                    total_value = total_invested  # Entry 시점에는 동일

                    portfolio = monitor.get_portfolio_snapshot(
                        wallet_balance=wallet_balance,
                        positions_count=1,
                        total_invested=total_invested,
                        total_value=total_value,
                    )

                    position_size_pct = (total_invested / wallet_balance) * 100 if wallet_balance > 0 else 0.0

                    # Telegram Entry 알림
                    telegram.send_entry(
                        side=side_str,
                        qty=position_qty_btc,
                        price=orchestrator.position.entry_price,
                        entry_reason=entry_reason,
                        equity_before=wallet_balance,
                        position_size_pct=position_size_pct,
                        wallet_balance=portfolio["wallet_balance"],
                        positions_count=portfolio["positions_count"],
                        total_invested=portfolio["total_invested"],
                        total_value=portfolio["total_value"],
                        total_pnl_pct=portfolio["total_pnl_pct"],
                        total_pnl_usd=portfolio["total_pnl_usd"],
                    )

            # State 전환 감지: Exit (IN_POSITION → FLAT)
            if previous_state != State.FLAT and current_state == State.FLAT:
                # Full cycle 완료 (IN_POSITION or ENTRY_PENDING → FLAT)
                # PnL 계산 (마지막 trade log에서 가져오기)
                trade_logs = log_storage.read_trade_logs_v1()
                if trade_logs:
                    last_trade = trade_logs[-1]
                    pnl_usd = last_trade.get("realized_pnl_usd", 0.0)
                    entry_price = last_trade.get("entry_price", 0.0)
                    exit_price = last_trade.get("exit_price", 0.0)
                    qty_btc = last_trade.get("qty_btc", 0.0)

                    # 수익률 계산
                    pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0

                    # Exit 근거 생성
                    if pnl_usd >= 0:
                        exit_reason = f"목표 수익 달성: ${exit_price:,.2f} 도달 (+{pnl_pct:.2f}% 수익)"
                    else:
                        exit_reason = f"손절가 도달: ${exit_price:,.2f} 도달 ({pnl_pct:.2f}% 손실 제한)"

                    # 보유 시간 계산
                    hold_duration = monitor.get_hold_duration()

                    # 포트폴리오 정보 조회
                    bybit_adapter.update_market_data()
                    wallet_balance = bybit_adapter.get_equity_usdt()

                    portfolio = monitor.get_portfolio_snapshot(
                        wallet_balance=wallet_balance, positions_count=0, total_invested=0.0, total_value=0.0
                    )

                    # Telegram Exit 알림
                    telegram.send_exit(
                        side="Sell" if last_trade.get("side") == "Buy" else "Buy",
                        qty=qty_btc,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        pnl_usd=pnl_usd,
                        pnl_pct=pnl_pct,
                        exit_reason=exit_reason,
                        equity_after=wallet_balance,
                        hold_duration=hold_duration,
                        wallet_balance=portfolio["wallet_balance"],
                        positions_count=portfolio["positions_count"],
                        total_invested=portfolio["total_invested"],
                        total_value=portfolio["total_value"],
                        total_pnl_pct=portfolio["total_pnl_pct"],
                        total_pnl_usd=portfolio["total_pnl_usd"],
                    )

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

        # Telegram Summary 전송
        telegram.send_summary(
            trades=monitor.total_trades,
            wins=monitor.successful_cycles,
            losses=monitor.failed_cycles,
            pnl=monitor.cumulative_pnl_usd,
        )

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

    args = parser.parse_args()

    run_dry_run(
        target_trades=args.target_trades,
        max_duration_hours=args.max_hours,
    )


if __name__ == "__main__":
    main()
