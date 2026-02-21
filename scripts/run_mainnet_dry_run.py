#!/usr/bin/env python3
"""
scripts/run_mainnet.py
Phase 12b: Mainnet Dry-Run Script (⚠️ 실거래 환경)

목표:
- Mainnet에서 30회 거래 실행 (실제 USD)
- Session Risk / Kill Switch 발동 증거 확보
- 로그 완전성 검증

⚠️ 경고:
- 실제 돈으로 거래합니다 (Testnet 아님!)
- 최소 $100 필요
- 초기 제한: 30 trades, Daily -5%, Per-trade $3

실행:
    python scripts/run_mainnet.py --target-trades 30

⚠️ 안전 장치:
- 초기 잔고 >= $100 검증
- Daily Loss Cap: -5% equity
- Per-Trade Loss Cap: $3 (Stage 1)
- Loss Streak: 3연패 HALT
- BYBIT_TESTNET=false 강제 검증
"""

import argparse
import time
import logging
import sys
import os
import traceback
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

# Setup logging (Mainnet 전용 디렉토리)
Path("logs/mainnet").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/mainnet/mainnet.log'),
        logging.StreamHandler()
    ]
)
# signal_generator만 DEBUG (no_signal 디버깅용)
logging.getLogger("application.signal_generator").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)


class MainnetMonitor:
    """Mainnet Dry-Run 모니터링 및 통계"""

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
        self.entry_time = None  # Entry 시간 추적
        self.entry_price = None  # Entry 가격 추적

        # Mainnet 전용: 최대 손실 추적
        self.max_drawdown_usd = 0.0
        self.max_drawdown_pct = 0.0

    def log_cycle_complete(self, pnl_usd: float):
        """Full cycle 완료 기록"""
        self.successful_cycles += 1
        self.total_trades += 1
        self.cumulative_pnl_usd += pnl_usd

        # Drawdown 추적
        if self.cumulative_pnl_usd < self.max_drawdown_usd:
            self.max_drawdown_usd = self.cumulative_pnl_usd
            self.max_drawdown_pct = (self.cumulative_pnl_usd / self.initial_equity) * 100

        logger.info(f"✅ Cycle {self.total_trades} complete | PnL: ${pnl_usd:.2f} | Cumulative: ${self.cumulative_pnl_usd:.2f}")

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
        """포트폴리오 스냅샷 반환"""
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
        logger.info("Mainnet Dry-Run Summary (⚠️ 실거래)")
        logger.info("=" * 60)
        logger.info(f"Total trades: {self.total_trades}")
        logger.info(f"Successful cycles: {self.successful_cycles}")
        logger.info(f"Failed cycles: {self.failed_cycles}")
        logger.info(f"Session Risk halts: {self.session_risk_halts}")
        logger.info(f"Emergency halts: {self.emergency_halts}")
        logger.info(f"Stop loss hits: {self.stop_loss_hits}")
        logger.info(f"Duration: {duration}")
        logger.info(f"Initial Equity: ${self.initial_equity:.2f}")
        logger.info(f"Cumulative PnL: ${self.cumulative_pnl_usd:.2f}")
        logger.info(f"Max Drawdown: ${self.max_drawdown_usd:.2f} ({self.max_drawdown_pct:.2f}%)")
        logger.info(f"Final Equity (estimated): ${self.initial_equity + self.cumulative_pnl_usd:.2f}")
        logger.info("=" * 60)


def verify_mainnet_safety() -> bool:
    """
    Mainnet 실행 전 안전 검증

    Returns:
        bool: 검증 통과 여부
    """
    import os

    logger.info("🔍 Mainnet Safety Verification...")

    # 1. BYBIT_TESTNET=false 검증
    testnet_mode = os.getenv("BYBIT_TESTNET", "true").lower()
    if testnet_mode != "false":
        logger.error(f"❌ FAIL: BYBIT_TESTNET={testnet_mode} (must be 'false' for Mainnet)")
        logger.error("   Set BYBIT_TESTNET=false in .env file")
        return False
    logger.info("✅ BYBIT_TESTNET=false (Mainnet mode)")

    # 2. API credentials 존재 확인
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    if not api_key or not api_secret:
        logger.error("❌ FAIL: BYBIT_API_KEY or BYBIT_API_SECRET missing")
        return False
    logger.info("✅ API credentials present")

    # 3. Testnet credentials와 다른지 확인
    testnet_key = os.getenv("BYBIT_TESTNET_API_KEY")
    if api_key == testnet_key:
        logger.error("❌ FAIL: BYBIT_API_KEY same as BYBIT_TESTNET_API_KEY")
        logger.error("   Use separate Mainnet API credentials!")
        return False
    logger.info("✅ Mainnet credentials separate from Testnet")

    logger.info("✅ Mainnet Safety Verification PASSED")
    return True


def confirm_mainnet_execution() -> bool:
    """
    사용자에게 Mainnet 실행 확인 요청

    Returns:
        bool: 사용자 승인 여부
    """
    print("\n" + "=" * 60)
    print("⚠️  MAINNET DRY-RUN WARNING ⚠️")
    print("=" * 60)
    print("You are about to run trading bot on MAINNET (REAL MONEY)!")
    print("")
    print("Safety Limits:")
    print("  - Daily Loss Cap: -5% equity")
    print("  - Per-Trade Loss Cap: $3 (Stage 1)")
    print("  - Loss Streak: 3 consecutive losses → HALT")
    print("  - Initial Max Trades: 30 trades")
    print("")
    print("Requirements:")
    print("  - Minimum equity: $100 USDT")
    print("  - Unified Trading Account (UTA)")
    print("  - BTCUSDT Linear Perpetual")
    print("=" * 60)
    print("")

    response = input("Type 'MAINNET' to confirm execution (or anything else to cancel): ")
    return response.strip() == "MAINNET"


def run_mainnet(
    target_trades: int = 30,
    max_duration_hours: int = 24,
):
    """
    Mainnet Dry-Run 실행

    Args:
        target_trades: 목표 거래 횟수 (default: 30)
        max_duration_hours: 최대 실행 시간 (default: 24 hours)
    """
    logger.info("=" * 60)
    logger.info("🚀 Mainnet Dry-Run Started")
    logger.info("=" * 60)
    logger.info(f"Target trades: {target_trades}")
    logger.info(f"Max duration: {max_duration_hours} hours")

    # Telegram notifier 초기화 (전역 에러 처리용)
    telegram = TelegramNotifier()

    try:
        # Bybit clients 초기화 (Mainnet)
        api_key = os.getenv("BYBIT_API_KEY", "")
        api_secret = os.getenv("BYBIT_API_SECRET", "")
        mainnet_rest_url = "https://api.bybit.com"
        mainnet_ws_url = "wss://stream.bybit.com/v5/private"

        rest_client = BybitRestClient(
            api_key=api_key,
            api_secret=api_secret,
            base_url=mainnet_rest_url
        )

        ws_client = BybitWsClient(
            api_key=api_key,
            api_secret=api_secret,
            wss_url=mainnet_ws_url
        )

        log_storage = LogStorage(log_dir=Path("logs/mainnet"))

        # BybitAdapter 초기화 (Mainnet mode)
        bybit_adapter = BybitAdapter(
            rest_client=rest_client,
            ws_client=ws_client,
            testnet=False  # Mainnet
        )

        # Market data 초기 로드 (equity, mark price 조회)
        logger.info("📊 Loading initial market data...")
        bybit_adapter.update_market_data()

        # Phase 13b: 이전 체결 가격 무시 (Clean start)
        bybit_adapter._last_fill_price = None

        initial_equity = bybit_adapter.get_equity_usdt()
        logger.info(f"✅ Equity: ${initial_equity:.2f} USDT")

        # 초기 잔고 검증 (최소 $100)
        if initial_equity < 100.0:
            logger.error(f"❌ FAIL: Insufficient equity (${initial_equity:.2f} < $100.00)")
            logger.error("   Minimum $100 required for Mainnet Dry-Run")
            return

        # Leverage 설정 (2026-02-20: 3x → 5x)
        try:
            leverage_result = rest_client.set_margin_mode(
                symbol="BTCUSDT",
                buy_leverage="5",
                sell_leverage="5",
                category="linear",
                trade_mode=0,  # Isolated Margin
            )
            logger.info(f"✅ Leverage set to 5x (Isolated Margin): retCode={leverage_result.get('retCode')}")
        except Exception as e:
            logger.warning(f"⚠️ Leverage setting failed (may already be set): {e}")

        # WebSocket 시작 (execution events 수신)
        logger.info("🔌 Starting WebSocket connection...")
        ws_client.start()
        time.sleep(3)  # Wait for connection/auth/subscribe
        if ws_client.is_connected():
            logger.info("✅ WebSocket connected and subscribed to execution.linear")
        else:
            logger.warning("⚠️ WebSocket connection in progress...")

        # Monitor 초기화
        monitor = MainnetMonitor(initial_equity=initial_equity)

        # Telegram notifier 활성화 확인 + 시작 알림
        if telegram.enabled:
            logger.info("✅ Telegram notifier enabled")
            telegram.send_summary(trades=0, wins=0, losses=0, pnl=0.0)
            logger.info("📱 Telegram startup notification sent")
        else:
            logger.info("ℹ️ Telegram notifier disabled")

        # Git commit hash + Config hash 계산
        import subprocess
        import hashlib
        git_commit = os.getenv("GIT_COMMIT", "").strip()
        if not git_commit or git_commit == "unknown":
            try:
                git_commit = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=Path(__file__).parent.parent,
                    stderr=subprocess.DEVNULL,
                ).decode().strip()[:12]
            except Exception:
                git_commit = "unknown"

        config_path = Path(__file__).parent.parent / "config" / "safety_limits.yaml"
        if config_path.exists():
            config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()[:12]
        else:
            config_hash = "unknown"

        logger.info(f"📋 git_commit={git_commit}, config_hash={config_hash}")

        # Orchestrator 초기화
        logger.info("🔍 About to initialize Orchestrator...")
        orchestrator = Orchestrator(
            market_data=bybit_adapter,
            rest_client=rest_client,
            log_storage=log_storage,
            config_hash=config_hash,
            git_commit=git_commit,
        )
        logger.info("✅ Orchestrator initialized successfully")

    except Exception as e:
        logger.error(f"❌ Initialization failed: {type(e).__name__}: {e}")
        traceback.print_exc()

        # Telegram 에러 알림
        telegram.send_error(
            error_type="InitializationError",
            error_message=f"{type(e).__name__}: {str(e)}",
            context="Bot initialization"
        )
        return

    # Main loop
    previous_state = State.FLAT

    start_time = time.time()

    tick_interval = 1.0  # 1초마다 tick (WS 이벤트 처리용)
    market_data_refresh_interval = 30.0  # 30초마다 시장 데이터 갱신
    last_market_refresh = 0.0  # 즉시 첫 갱신 트리거

    # 초기 상태 로깅
    logger.info(f"📊 Initial state: {orchestrator.state}")
    logger.info(f"📊 Initial position: {orchestrator.position}")
    logger.info(f"🔄 Starting main loop (target_trades={target_trades}, max_duration={max_duration_hours}h)")
    logger.info(f"📊 Market data refresh interval: {market_data_refresh_interval}s")

    try:
        tick_count = 0

        while True:
            tick_count += 1
            logger.info(f"🔄 Tick {tick_count} (trades: {monitor.total_trades}/{target_trades})")

            # 종료 조건 확인
            if monitor.total_trades >= target_trades:
                logger.info(f"✅ Target trades reached: {monitor.total_trades}/{target_trades}")
                break

            if (time.time() - start_time) > (max_duration_hours * 3600):
                logger.info(f"⏱️ Max duration reached: {max_duration_hours} hours")
                break

            # Market data 갱신 (30초 간격)
            now = time.time()
            if now - last_market_refresh >= market_data_refresh_interval:
                try:
                    bybit_adapter.update_market_data()
                    last_market_refresh = now
                    if tick_count <= 5 or tick_count % 60 == 0:
                        pos = bybit_adapter.get_position()
                        logger.info(f"  📊 Market data refreshed: equity=${bybit_adapter.get_equity_usdt():,.2f}, "
                                    f"mark_price=${bybit_adapter.get_mark_price():,.2f}, "
                                    f"position={pos.get('side', 'None')} {pos.get('size', '0')}, "
                                    f"ma_slope={bybit_adapter.get_ma_slope_pct():.4f}%, "
                                    f"funding={bybit_adapter.get_funding_rate():.6f}, "
                                    f"atr={bybit_adapter.get_atr()}")
                except Exception as e:
                    logger.warning(f"⚠️ Market data refresh failed: {e}")

            # Tick 실행
            try:
                result = orchestrator.run_tick()
                current_state = result.state

                # Tick 결과 로깅 (상태 변경 시 또는 10 tick마다)
                if tick_count % 10 == 0 or current_state != previous_state:
                    logger.info(f"  → State: {current_state}, Halt: {result.halt_reason}")

                # Entry 차단 이유 로깅 (처음 발생 시 또는 이유 변경 시)
                if result.entry_blocked and tick_count <= 20:
                    # ATR 값 추가 로깅
                    if result.entry_block_reason == "atr_too_low":
                        atr_pct = bybit_adapter.get_atr_pct_24h()
                        logger.info(f"  → Entry blocked: {result.entry_block_reason} (ATR: {atr_pct:.2f}% < 3.0%)")
                    elif result.entry_block_reason == "no_signal":
                        # Regime-aware entry debug: 실제 ma_slope_pct, funding_rate 값 표시
                        ma_slope = bybit_adapter.get_ma_slope_pct()
                        funding = bybit_adapter.get_funding_rate()
                        lfp = bybit_adapter.get_last_fill_price()
                        gs = orchestrator.grid_spacing if hasattr(orchestrator, 'grid_spacing') else None
                        logger.info(f"  → Entry blocked: no_signal (ma_slope={ma_slope:.4f}%, funding={funding:.6f}, last_fill={lfp}, grid_spacing={gs})")
                    else:
                        logger.info(f"  → Entry blocked: {result.entry_block_reason}")

            except Exception as e:
                logger.error(f"❌ Tick error: {type(e).__name__}: {e}")
                traceback.print_exc()

                # Telegram 에러 알림
                telegram.send_error(
                    error_type="TickError",
                    error_message=f"{type(e).__name__}: {str(e)}",
                    context=f"Tick {tick_count}"
                )

                break

            # HALT 감지
            if current_state == State.HALT:
                halt_reason = result.halt_reason or "Unknown"
                monitor.log_halt(halt_reason)
                logger.error(f"🚨 HALT detected: {halt_reason}")

                # Telegram HALT 알림
                equity = bybit_adapter.get_equity_usdt()
                telegram.send_halt(reason=halt_reason, equity=equity)

                # HALT 발생 시 중단
                break

            # State 전환 감지: Entry (? → IN_POSITION)
            if previous_state != State.IN_POSITION and current_state == State.IN_POSITION:
                if orchestrator.position:
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
                # Full cycle 완료
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

            # Stop loss hit 감지
            if result.exit_intent and result.exit_intent.reason == "STOP_LOSS":
                monitor.log_stop_hit()

            # Previous state 업데이트
            previous_state = current_state

            # Sleep
            time.sleep(tick_interval)

    except KeyboardInterrupt:
        logger.info("🛑 Mainnet Dry-Run interrupted by user")

    except Exception as e:
        logger.error(f"❌ Fatal error in main loop: {type(e).__name__}: {e}")
        traceback.print_exc()

        # Telegram 에러 알림
        telegram.send_error(
            error_type="FatalError",
            error_message=f"{type(e).__name__}: {str(e)}",
            context="Main loop"
        )

    finally:
        # WebSocket 정리
        ws_client.stop()

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
        logger.info(f"✅ Trade log complete: {actual_count}/{expected_count}")
    else:
        logger.warning(f"⚠️ Trade log mismatch: {actual_count}/{expected_count}")

    logger.info(f"📂 Trade logs saved: logs/mainnet/")


def main():
    parser = argparse.ArgumentParser(description="Mainnet Dry-Run Script (⚠️ 실거래)")
    parser.add_argument(
        "--target-trades",
        type=int,
        default=30,
        help="목표 거래 횟수 (default: 30, max: 50)"
    )
    parser.add_argument(
        "--max-hours",
        type=int,
        default=24,
        help="최대 실행 시간 (hours, default: 24)"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt (⚠️ 위험: 자동 승인)"
    )
    args = parser.parse_args()

    # 안전 검증
    if not verify_mainnet_safety():
        logger.error("❌ Mainnet Safety Verification FAILED")
        sys.exit(1)

    # 사용자 확인 (--yes 플래그 없으면)
    if not args.yes:
        if not confirm_mainnet_execution():
            logger.info("❌ User cancelled Mainnet execution")
            sys.exit(0)

    # Mainnet Dry-Run 실행
    run_mainnet(
        target_trades=min(args.target_trades, 50),  # Max 50 trades
        max_duration_hours=args.max_hours,
    )


if __name__ == "__main__":
    main()
