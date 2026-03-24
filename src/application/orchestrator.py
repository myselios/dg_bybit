"""
src/application/orchestrator.py
Orchestrator — Tick loop에서 Flow 순서대로 실행 (application layer 통합)

SSOT:
- FLOW.md Section 2: Tick Ordering (Emergency-first)
- FLOW.md Section 4.2: God Object 금지 (책임 분리)
- task_plan.md Phase 6: Tick 순서 고정 (Emergency → Events → Position → Entry)

원칙:
1. Thin wrapper: 각 책임은 이미 구현된 모듈에 위임
2. Tick 순서 고정: Emergency → Events → Position → Entry
3. 상태 관리: transition() 호출로 state 전환

Exports:
- Orchestrator: Tick loop orchestrator
- TickResult: Tick 실행 결과 (state, execution_order, halt_reason 등)
"""

import logging
import time
import datetime
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from domain.state import State, Position, Direction, StopStatus

logger = logging.getLogger(__name__)
from infrastructure.exchange.market_data_interface import MarketDataInterface
from application.exit_manager import check_stop_hit, create_exit_intent
from domain.intent import ExitIntent

# Phase 11b: Entry Flow imports
from application.entry_allowed import check_entry_allowed, EntryDecision
from application.signal_generator import generate_signal, calculate_grid_spacing, Signal
from application.threshold_calibrator import ThresholdCalibrator, ThresholdConfig, DEFAULT_THRESHOLD_CONFIG
from application.sizing import calculate_contracts, SizingResult
from application.event_processor import match_pending_order, create_position_from_fill  # Phase 12a-4c: REST API fallback

# Phase 11b: Refactored modules (God Object mitigation)
from application.emergency_checker import check_emergency_status
from application.drawdown_recovery import check_drawdown_recovery, DrawdownState  # Wave 5 Stream C
from application.entry_coordinator import (
    get_stage_params,
    build_signal_context,
    build_sizing_params,
    generate_signal_id,
)
from application.event_processor import (
    verify_state_consistency,
    match_pending_order,
    create_position_from_fill,
)

# Phase 11b: Trade Log Integration
from infrastructure.storage.log_storage import LogStorage
from application.trade_logging import log_estimated_trade, log_completed_trade

# Stop Manager Integration (Codex Review Fix #1)
from application.stop_manager import should_update_stop, determine_stop_action, execute_stop_update

# KillSwitch Integration (Codex Review Fix #2)
from infrastructure.safety.killswitch import KillSwitch

# Agentic v1: ReflectionAgent 자동 실행
from application.agents.reflection_agent import ReflectionAgent


def _compute_adaptive_trail_distance(
    trail_atr: float,
    entry_price: float,
    trail_price: float,
    direction: "Direction",
) -> float:
    """
    수익 수준에 따른 adaptive trailing stop 거리 계산 (Wave5 Stream B: 조기 청산 방지)

    Args:
        trail_atr: 진입 시점 ATR
        entry_price: 진입가
        trail_price: 현재 최고/최저 유리가격
        direction: 포지션 방향 (LONG/SHORT)

    Returns:
        trail_distance: trailing stop 거리 (USD)

    Policy:
    - 수익 < ATR*0.8: trailing 비활성화 (trail_price보다 큰 값 반환 → 미발동)
    - 수익 >= ATR*0.8: trailing 활성화 (기본 ATR*0.5)
    - 수익 >= ATR*1.0: ATR*0.3 (수익 보호 강화)
    - 수익 >= ATR*2.0: ATR*0.2 (최대 수익 보호)
    """
    if direction == Direction.LONG:
        unrealized_profit = trail_price - entry_price
    else:
        unrealized_profit = entry_price - trail_price

    # Wave5 Stream B: ATR*0.8 미만이면 trailing 비활성화
    # trail_price보다 큰 값 반환 → 가격이 trail_price - trail_distance 아래로 내려가지 않음
    if unrealized_profit < trail_atr * 0.8:
        return trail_price + 1.0  # 사실상 무한대 → trailing 미발동

    if unrealized_profit >= trail_atr * 2.0:
        return trail_atr * 0.2
    if unrealized_profit >= trail_atr * 1.0:
        return trail_atr * 0.3
    return trail_atr * 0.5


@dataclass
class TickResult:
    """Tick 실행 결과"""

    state: State
    execution_order: List[str]
    halt_reason: Optional[str] = None
    entry_blocked: bool = False
    entry_block_reason: Optional[str] = None
    exit_intent: Optional[ExitIntent] = None  # Exit 주문 의도 (Phase 11)


class Orchestrator:
    """
    Orchestrator — Tick loop에서 Flow 순서대로 실행

    FLOW Section 4.2:
        - God Object 금지
        - 책임 분리: emergency/events/position/entry는 별도 모듈에 위임

    task_plan.md Phase 6:
        - Tick 순서 고정: Emergency → Events → Position → Entry
        - degraded/normal 분리, degraded 60s → halt
    """

    def __init__(
        self,
        market_data: MarketDataInterface,
        rest_client=None,  # Phase 11b: Order placement용 (Optional, type: BybitRestClient)
        log_storage: Optional[LogStorage] = None,  # Phase 11b: Trade Log 저장용 (Optional)
        killswitch: Optional[KillSwitch] = None,  # Codex Review Fix #2: Manual halt mechanism
        config_hash: str = "unknown",  # P0 fix: 실제 config hash (safety_limits.yaml 기반)
        git_commit: str = "unknown",  # P0 fix: 실제 git commit hash
    ):
        """
        Orchestrator 초기화

        Args:
            market_data: Market data interface (FakeMarketData or BybitAdapter)
            rest_client: Bybit REST client (Order placement용, Phase 11b)
            log_storage: LogStorage (Trade Log 저장용, Phase 11b)
            killswitch: KillSwitch (Manual halt mechanism, Codex Review Fix #2)
            config_hash: Config 해시 (safety_limits.yaml 기반, 재현성)
            git_commit: Git commit 해시 (코드 버전 추적)
        """
        self.market_data = market_data
        self.rest_client = rest_client
        self.log_storage = log_storage
        self.killswitch = killswitch if killswitch is not None else KillSwitch()
        self.config_hash = config_hash
        self.git_commit = git_commit
        self.tick_counter = 0  # Tick counter (general purpose)
        self._last_entry_attempt = 0.0  # TEST: Cooldown tracking
        # entry fill만 추적 (exit fill이 LFP를 오염시키는 것을 방지)
        # 초기값은 adapter LFP로 설정 (재시작 시 기존 그리드 기준점 유지)
        self._last_entry_fill_price: Optional[float] = (
            market_data.get_last_fill_price() if market_data is not None else None
        )

        # Position recovery: 기존 포지션이 있으면 State.IN_POSITION으로 시작
        self.state = State.FLAT
        self.position = None

        if rest_client is not None:
            try:
                pos_response = rest_client.get_position(symbol="BTCUSDT", category="linear")

                if pos_response.get("retCode", -1) == 0:
                    positions = pos_response["result"]["list"]

                    if positions and len(positions) > 0:
                        existing_pos = positions[0]
                        size_btc = float(existing_pos.get("size", "0"))

                        if size_btc > 0:
                            # 기존 포지션 발견 → State.IN_POSITION으로 복구
                            qty = int(size_btc * 1000)  # BTC to contracts
                            entry_price = float(existing_pos.get("avgPrice", "0"))
                            side = existing_pos.get("side", "")
                            direction = Direction.LONG if side == "Buy" else Direction.SHORT

                            self.position = Position(
                                qty=qty,
                                entry_price=entry_price,
                                direction=direction,
                                signal_id="recovered",  # Position recovery
                                stop_status=StopStatus.MISSING,  # Force stop recovery
                                stop_price=None,  # P0-4: None → check_stop_hit returns False → stop recovery 우선
                                base_qty=qty,
                            )
                            self.state = State.IN_POSITION

                            logger.info(f"✅ Position recovered: {side} {qty} contracts @ ${entry_price:.2f}")
                        else:
                            logger.info("✅ No existing position found (size=0)")
                    else:
                        logger.info("✅ No existing position found (empty list)")
                else:
                    logger.warning(f"⚠️ Position recovery API error: {pos_response['retMsg']}")
            except Exception as e:
                logger.warning(f"⚠️ Position recovery failed: {e} - Starting with State.FLAT")
                self.state = State.FLAT
                self.position = None

        # Phase 11b: Entry Flow tracking
        self.pending_order: Optional[dict] = None  # Pending order 정보 (FILL event 매칭용)
        self.pending_order_timestamp: Optional[float] = None  # Phase 12a-4c: Pending order 발주 시각 (timeout 체크용)
        self.current_signal_id: Optional[str] = None  # 현재 Signal ID
        self.last_halt_reason: Optional[str] = None
        self.grid_spacing: float = 0.0  # Grid spacing (ATR * 2.0)

        # S6 ThresholdCalibrator: 동적 임계값 보정 (최초 1회)
        self._threshold_calibrator = ThresholdCalibrator()
        self._threshold_config: Optional[ThresholdConfig] = None

        # Agentic v1: ReflectionAgent (트레이드 완료 후 자동 분석)
        self._reflection_agent = ReflectionAgent()
        self._recent_trades: List[Dict[str, Any]] = []  # 최근 트레이드 버퍼 (최대 20건)

        # Session Risk Policy 설정 (Phase 9c)
        self.daily_loss_cap_pct = 5.0  # 5% equity
        self.weekly_loss_cap_pct = 12.5  # 12.5% equity
        self.fee_spike_threshold = 1.5  # Fee ratio threshold
        self.slippage_threshold_usd = 2.0  # Slippage threshold ($)
        self.slippage_window_seconds = 600.0  # 10 minutes
        self.current_timestamp = None  # Slippage anomaly용

        # Stop Manager 상태 (Codex Review Fix #1)
        self.last_stop_update_at: float = 0.0  # 마지막 stop 갱신 시각
        self.amend_fail_count: int = 0  # Amend 실패 횟수

        # Trailing Stop 상태 (2026-03-07)
        self.trail_price: Optional[float] = None  # 포지션 중 최고/최저 유리가격
        self.entry_atr: Optional[float] = None    # 진입 시점 ATR (Trailing 거리 계산용)

        # Wave 2A: klines 캐시 (30초 갱신, API 호출 최소화)
        self._klines_cache: Optional[Dict[str, Any]] = None  # {"prices": list, "volumes": list, "ts": float}
        self._KLINES_CACHE_TTL = 30.0  # 30초

        # Wave 5A: Entry signal 정보 보존 (EXIT pending_order로 덮어써져도 유지)
        self._entry_signal_score: Optional[int] = None
        self._entry_signal_components: Optional[Dict[str, Any]] = None

        # Wave 5 Stream C: DrawdownRecovery 상태 추적
        self._drawdown_last_reset_date: str = ""  # 마지막 날짜 초기화 기준 (YYYY-MM-DD)
        self._drawdown_state: Optional[DrawdownState] = None  # 최신 DrawdownState 캐시

    def run_tick(self) -> TickResult:
        """
        Tick 실행 (Emergency → Events → Position → Entry)

        Returns:
            TickResult: Tick 실행 결과

        FLOW Section 2:
            - Emergency check (최우선)
            - Events processing (WS 이벤트)
            - Position management (stop 갱신)
            - Entry decision (signal → gate → sizing)
        """
        import logging
        logger = logging.getLogger(__name__)

        # Tick counter increment
        self.tick_counter += 1

        # Phase 9d: current_timestamp 초기화 (Slippage anomaly 체크용)
        self.current_timestamp = self.market_data.get_timestamp()

        # TEST 2026-03-06: Cooldown after failed entry
        if hasattr(self, '_last_entry_attempt') and self._last_entry_attempt > 0:
            time_since_last = self.current_timestamp - self._last_entry_attempt
            if time_since_last < 10.0:  # 10 second cooldown
                return TickResult(
                    state=self.state,
                    execution_order=["entry_cooldown"],
                    entry_blocked=True,
                    entry_block_reason=f"entry_cooldown: {10 - time_since_last:.1f}s remaining",
                )

        execution_order = []
        halt_reason = None
        entry_blocked = False
        entry_block_reason = None

        # (0a) KillSwitch check (최우선, Codex Review Fix #2)
        if self.killswitch.is_halted():
            self.state = State.HALT
            halt_reason = "manual_halt_killswitch"
            return TickResult(
                state=self.state,
                execution_order=["killswitch_check"],
                halt_reason=halt_reason,
            )

        # (0) Self-healing check (Position vs State 일관성, Phase 11b)
        inconsistency_reason = verify_state_consistency(
            position=self.position,
            state=self.state,
        )
        if inconsistency_reason is not None:
            self.state = State.HALT
            halt_reason = inconsistency_reason
            return TickResult(
                state=self.state,
                execution_order=["self_healing_check"],
                halt_reason=halt_reason,
            )

        # (1) Emergency check (최우선)
        execution_order.append("emergency")
        emergency_result = self._check_emergency()
        if emergency_result["status"] == "HALT":
            self.state = State.HALT
            halt_reason = emergency_result["reason"]
            return TickResult(
                state=self.state,
                execution_order=execution_order,
                halt_reason=halt_reason,
            )

        # (2) Events processing
        execution_order.append("events")
        self._process_events()

        # (3) Position management + Exit decision
        execution_order.append("position")
        exit_intent = self._manage_position()

        # Position 단계에서 HALT 전환되면 이유를 채워서 즉시 반환
        if self.state == State.HALT:
            halt_reason = self.last_halt_reason or "position_management_halt"
            return TickResult(
                state=self.state,
                execution_order=execution_order,
                halt_reason=halt_reason,
                exit_intent=exit_intent,
            )

        # (4) Entry decision
        execution_order.append("entry")
        entry_result = self._decide_entry()
        if entry_result["blocked"]:
            entry_blocked = True
            entry_block_reason = entry_result["reason"]

        return TickResult(
            state=self.state,
            execution_order=execution_order,
            halt_reason=halt_reason,
            entry_blocked=entry_blocked,
            entry_block_reason=entry_block_reason,
            exit_intent=exit_intent,  # Phase 11: Exit intent
        )

    def _log_estimated_trade(self, reason: str) -> None:
        """Thin delegate to trade_logging.log_estimated_trade()"""
        if self.position is None or self.log_storage is None:
            return
        log_estimated_trade(
            market_data=self.market_data,
            log_storage=self.log_storage,
            config_hash=self.config_hash,
            git_commit=self.git_commit,
            position=self.position,
            reason=reason,
        )

    def _log_completed_trade(self, event: Dict[str, Any], position: Optional[Position]) -> None:
        """트레이드 완료 로그 + ReflectionAgent 자동 분석 + 파라미터 자동 갱신"""
        if position is None:
            return

        # Wave 5A: _entry_signal_score 우선 사용 (EXIT pending_order로 덮어써져도 유지)
        # pending_order는 EXIT 시점에 exit order 정보로 교체되어 signal_score가 없음
        _signal_score = self._entry_signal_score
        _signal_components = self._entry_signal_components
        if _signal_score is None and self.pending_order:
            _signal_score = self.pending_order.get("signal_score")
            _signal_components = self.pending_order.get("signal_components")

        # 기본 로그 기록
        log_completed_trade(
            market_data=self.market_data,
            log_storage=self.log_storage,
            config_hash=self.config_hash,
            git_commit=self.git_commit,
            position=position,
            pending_order=self.pending_order,
            pending_order_timestamp=self.pending_order_timestamp,
            event=event,
            t_trend=self._threshold_config.t_trend if self._threshold_config else None,
            signal_score=_signal_score,
            signal_components=_signal_components,
        )

        # ReflectionAgent: 트레이드 결과 분석
        self._run_reflection(position, event)

    def _run_reflection(self, position: Position, event: Dict[str, Any]) -> None:
        """ReflectionAgent 실행 + 파라미터 자동 갱신 + Telegram 알림."""
        try:
            # 진입 가격, 청산 가격으로 PnL 계산
            if hasattr(event, 'exec_price'):
                exit_price = float(event.exec_price)
            else:
                exit_price = float(event.get("execPrice", position.entry_price))

            qty_btc = position.qty * 0.001
            if position.direction == Direction.LONG:
                pnl_usd = (exit_price - position.entry_price) * qty_btc
            else:
                pnl_usd = (position.entry_price - exit_price) * qty_btc

            _signal_score = None
            if self.pending_order:
                _signal_score = self.pending_order.get("signal_score")

            trade_data = {
                "trade_id": f"T-{int(time.time())}",
                "direction": position.direction.value,
                "entry_price": position.entry_price,
                "exit_price": exit_price,
                "pnl_usd": pnl_usd,
                "hold_seconds": getattr(position, "entry_time", 0) and (time.time() - position.entry_time) or 0,
                "ma_slope_pct": self.market_data.get_ma_slope_pct(),
                "funding_rate": self.market_data.get_funding_rate(),
                "signal_score": _signal_score,
            }

            result = self._reflection_agent.analyze(trade_data)
            logger.info(
                f"[Reflection] {result.outcome} | pattern={result.pattern} | "
                f"{result.hypothesis[:80]}"
            )

            # 최근 트레이드 버퍼 갱신 (최대 20건)
            self._recent_trades = (self._recent_trades + [trade_data])[-20:]

            # param_delta 있으면 즉시 자동 적용
            if result.param_delta and "T_TREND" in result.param_delta:
                new_t_trend = result.param_delta["T_TREND"]
                if new_t_trend and isinstance(new_t_trend, float):
                    old_t_trend = self._threshold_config.t_trend if self._threshold_config else 0.05
                    self._threshold_config = ThresholdConfig(
                        t_trend=new_t_trend,
                        t_range_entry=new_t_trend * 0.25,
                    )
                    logger.info(
                        f"[AutoParam] T_TREND 자동 갱신: {old_t_trend:.4f}% → {new_t_trend:.4f}% "
                        f"(pattern={result.pattern})"
                    )
                    # Telegram 알림 (단방향)
                    if hasattr(self, "telegram") and self.telegram:
                        self.telegram.send_param_change(
                            param_name="T_TREND",
                            old_val=old_t_trend,
                            new_val=new_t_trend,
                            reason=result.hypothesis,
                        )

        except Exception as e:
            logger.error(f"[Reflection] 분석 중 오류 (무시): {type(e).__name__}: {e}")

    def get_state(self) -> State:
        """현재 상태 반환"""
        return self.state

    def _check_emergency(self) -> dict:
        """
        Emergency 체크 (최우선)

        Returns:
            {"status": "PASS" or "HALT", "reason": str}

        FLOW Section 7.1 + Phase 9c Session Risk Policy
        Refactored: Delegates to emergency_checker.check_emergency_status()
        """
        return check_emergency_status(
            market_data=self.market_data,
            daily_loss_cap_pct=self.daily_loss_cap_pct,
            weekly_loss_cap_pct=self.weekly_loss_cap_pct,
            fee_spike_threshold=self.fee_spike_threshold,
            slippage_threshold_usd=self.slippage_threshold_usd,
            slippage_window_seconds=self.slippage_window_seconds,
            current_timestamp=self.current_timestamp,
        )

    def _process_events(self) -> None:
        """
        Events 처리 (FILL -> Position update)

        1. REST API fallback (WebSocket timeout 시) → rest_fallback 모듈에 위임
        2. WebSocket FILL event 처리 (match → position create → state transition)
        """
        from application.rest_fallback import check_pending_order_fallback, _NO_CHANGE
        from application.rest_fallback import _recover_position_from_api

        # (0) Orphan state 안전망: pending=None인데 ENTRY/EXIT_PENDING 상태 → 강제 복구
        # 원인: REST fallback이 clear_pending=True + new_state=None 반환 시 발생
        if (self.state in [State.ENTRY_PENDING, State.EXIT_PENDING] and
                self.pending_order is None and
                self.rest_client is not None):
            logger.warning(
                f"Orphan state detected: state={self.state}, pending=None — recovering via position API"
            )
            try:
                position = _recover_position_from_api(self.rest_client, pending_order=None)
                if self.state == State.ENTRY_PENDING:
                    if position is not None:
                        self.position = position
                        self.state = State.IN_POSITION
                        logger.info("Orphan ENTRY_PENDING recovered → IN_POSITION")
                    else:
                        self.state = State.FLAT
                        logger.info("Orphan ENTRY_PENDING recovered → FLAT (no exchange position)")
                elif self.state == State.EXIT_PENDING:
                    if position is None:
                        self.state = State.FLAT
                        self._last_entry_fill_price = None
                        logger.info("Orphan EXIT_PENDING recovered → FLAT")
                    # position이 있으면 EXIT_PENDING 유지 (아직 청산 중)
            except Exception as e:
                logger.error(f"Orphan state recovery failed: {type(e).__name__}: {e}")
            return  # 이번 tick은 여기서 종료, 다음 tick에서 정상 진행

        # (1) REST API polling fallback (WebSocket timeout 시)
        WEBSOCKET_TIMEOUT = 10.0
        skip_ws = False
        if (self.state in [State.ENTRY_PENDING, State.EXIT_PENDING] and
            self.pending_order is not None and
            self.pending_order_timestamp is not None):

            elapsed = time.time() - self.pending_order_timestamp
            if elapsed > WEBSOCKET_TIMEOUT and self.rest_client is not None:
                try:
                    result = check_pending_order_fallback(
                        rest_client=self.rest_client,
                        state=self.state,
                        pending_order=self.pending_order,
                        elapsed=elapsed,
                    )
                    self._apply_fallback_result(result)
                    skip_ws = result.skip_ws_processing
                except Exception as e:
                    logger.error(f"REST API polling failed: {type(e).__name__}: {e}")

        if skip_ws:
            return

        # (2) WebSocket FILL event 처리
        fill_events = self.market_data.get_fill_events()
        if fill_events:
            logger.info(f"Got {len(fill_events)} FILL events from WS")

        for event in fill_events:
            try:
                matched = match_pending_order(event=event, pending_order=self.pending_order)
                if not matched:
                    continue

                position = create_position_from_fill(event=event, pending_order=self.pending_order)

                if self.state == State.ENTRY_PENDING:
                    self.position = position
                    self.state = State.IN_POSITION
                    self._last_entry_fill_price = position.entry_price  # entry fill만 LFP 갱신
                    self.pending_order = None
                    self.pending_order_timestamp = None
                elif self.state == State.EXIT_PENDING:
                    if self.log_storage is not None:
                        self._log_completed_trade(event=event, position=self.position)
                    self.position = None
                    self.state = State.FLAT
                    self._last_entry_fill_price = None  # exit 후 Grid 초기화 (역추세 재진입 방지)
                    self.pending_order = None
                    self.pending_order_timestamp = None
                    # Wave 5A: 트레이드 완료 후 entry signal 정보 초기화
                    self._entry_signal_score = None
                    self._entry_signal_components = None

            except Exception as e:
                logger.error(f"Exception in _process_events: {type(e).__name__}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")

    def _apply_fallback_result(self, result) -> None:
        """FallbackResult를 self.* 상태에 적용"""
        from application.rest_fallback import _NO_CHANGE

        # Estimated trade 로그 (state 변경 전에 기록)
        if result.log_estimated_reason and self.log_storage is not None and self.position is not None:
            self._log_estimated_trade(reason=result.log_estimated_reason)

        # Completed trade 로그
        if result.log_completed_event is not None and self.log_storage is not None:
            self._log_completed_trade(event=result.log_completed_event, position=self.position)

        # State 변경
        if result.new_state is not None:
            prev_state = self.state
            self.state = result.new_state
            # _last_entry_fill_price: fallback으로 FLAT 전환 시 리셋
            if result.new_state == State.FLAT and prev_state == State.EXIT_PENDING:
                self._last_entry_fill_price = None

        # Position 변경
        if result.new_position is not _NO_CHANGE:
            self.position = result.new_position

        # Pending 초기화
        if result.clear_pending:
            self.pending_order = None
            self.pending_order_timestamp = None

    def _manage_position(self) -> Optional[ExitIntent]:
        """
        Position 관리 (stop 갱신 + exit decision)

        FLOW Section 2.5:
            - stop_manager.should_update_stop()
            - stop_manager.determine_stop_action()
            - Phase 11b: Exit decision (stop hit 체크 + Exit order placement)

        Returns:
            ExitIntent: Exit 주문 의도 (stop hit 시)
        """
        # IN_POSITION이 아니면 건너뛰기
        if self.state != State.IN_POSITION or self.position is None:
            return None

        # 거래소 실포지션과 내부 상태 동기화 (레이스컨디션 방어)
        if self.rest_client is not None:
            try:
                pos_resp = self.rest_client.get_position(category="linear", symbol="BTCUSDT")
                plist = pos_resp.get("result", {}).get("list", [])
                ex_size = float(plist[0].get("size", "0") or 0) if plist else 0.0
                if ex_size == 0.0:
                    logger.warning("IN_POSITION but exchange size=0 -> sync to FLAT")
                    self.state = State.FLAT
                    self.position = None
                    self.pending_order = None
                    self.pending_order_timestamp = None
                    return None
            except Exception as e:
                logger.warning(f"Position sync check failed (continue): {e}")

        # P0-1: Stop 복구 실패(ERROR) → 즉시 HALT (Stop 없는 포지션 운영 금지)
        if self.position.stop_status == StopStatus.ERROR:
            logger.error("🚨 Stop recovery failed (ERROR), HALT — 포지션에 Stop 없음")
            self.state = State.HALT
            self.last_halt_reason = "stop_recovery_failed_no_protective_stop"
            return None

        # 포지션 진입가 기반 청산 로직 (2026-03-07 개편)
        current_price = self.market_data.get_current_price()

        should_exit = False
        exit_reason = "stop_loss_hit"
        exit_qty_contracts = self.position.qty

        # Trailing Stop: trail_price 갱신
        if self.trail_price is None:
            self.trail_price = current_price
        elif self.position.direction == Direction.LONG:
            if current_price > self.trail_price:
                self.trail_price = current_price
        else:  # SHORT
            if current_price < self.trail_price:
                self.trail_price = current_price

        # 1) Hard SL 체크 (거래소 stop_price 기준 안전장치)
        if check_stop_hit(current_price=current_price, position=self.position):
            should_exit = True
            exit_reason = "stop_loss_hit"

        # 2) Trailing Stop 체크 (Wave4: adaptive trail - 수익 수준별 trail 좁힘)
        # 기본: ATR*0.5 / 수익>=ATR*1: ATR*0.3 / 수익>=ATR*2: ATR*0.2 / fallback: trail*1.5%
        if not should_exit:
            trail_atr = self.entry_atr or 0.0
            if trail_atr > 0:
                trail_distance = _compute_adaptive_trail_distance(
                    trail_atr=trail_atr,
                    entry_price=self.position.entry_price,
                    trail_price=self.trail_price,
                    direction=self.position.direction,
                )
            else:
                trail_distance = self.trail_price * 0.015  # fallback 1.5%
            if self.position.direction == Direction.LONG:
                if current_price < self.trail_price - trail_distance:
                    should_exit = True
                    exit_reason = "trailing_stop"
                    logger.info(
                        f"Trailing Stop LONG: price=${current_price:,.2f} < trail=${self.trail_price:,.2f} - dist=${trail_distance:,.2f}"
                    )
            else:  # SHORT
                if current_price > self.trail_price + trail_distance:
                    should_exit = True
                    exit_reason = "trailing_stop"
                    logger.info(
                        f"Trailing Stop SHORT: price=${current_price:,.2f} > trail=${self.trail_price:,.2f} + dist=${trail_distance:,.2f}"
                    )

        if should_exit:
            # Exit intent 생성
            intents = create_exit_intent(position=self.position, reason=exit_reason)
            intents.exit_intent.qty = exit_qty_contracts

            # Phase 11b: Exit order 발주 (DoD: "Place exit order")
            if self.rest_client is not None:
                try:
                    # Exit order 발주 (Market order for immediate execution)
                    exit_side = "Sell" if self.position.direction == Direction.LONG else "Buy"

                    exit_qty_btc = round(exit_qty_contracts * 0.001, 3)
                    exit_order = self.rest_client.place_order(
                        symbol="BTCUSDT",
                        side=exit_side,
                        qty=str(exit_qty_btc),  # BTC 단위 (contracts * 0.001)
                        order_link_id=f"exit_{self.position.signal_id}_{int(time.time())}",
                        order_type="Market",
                        time_in_force="GTC",
                        price=None,  # Market order: no price
                        category="linear",
                        reduce_only=True,  # P0-2: 반대 방향 포지션 오픈 방지
                    )

                    # Bybit V5 API response structure: {"result": {"orderId": "...", "orderLinkId": "..."}}
                    ret_code = exit_order.get("retCode", -1)
                    result = exit_order.get("result", {})
                    order_id = result.get("orderId")
                    order_link_id = result.get("orderLinkId")

                    if ret_code != 0 or not order_id:
                        logger.error(f"❌ Exit order failed: retCode={ret_code}, response={exit_order}")
                        # 주문 실패 시 IN_POSITION 유지 (다음 tick에서 재시도)
                        return intents.exit_intent

                    logger.info(f"✅ Exit order placed: orderId={order_id}, side={exit_side}, reason={exit_reason}")

                    # Trailing Stop 상태 초기화
                    self.trail_price = None
                    self.entry_atr = None

                    # State 전이: IN_POSITION → EXIT_PENDING
                    self.state = State.EXIT_PENDING
                    self.pending_order = {
                        "order_id": order_id,
                        "order_link_id": order_link_id,
                        "side": exit_side,
                        "qty": exit_qty_contracts,
                        "price": current_price,  # Market price (참고용)
                        "signal_id": self.position.signal_id,
                    }
                    # Phase 12a-4c: Pending order 발주 시각 기록
                    self.pending_order_timestamp = time.time()
                except Exception as e:
                    # Exit order 실패 → IN_POSITION 유지 (다음 tick에서 재시도)
                    logger.error(f"❌ Exit order exception: {type(e).__name__}: {e}")
                    # HALT 대신 IN_POSITION 유지 → 다음 tick에서 재시도

            return intents.exit_intent

        # Codex Review Fix #1: Stop Manager 통합
        # FLOW Section 2.5: Stop 갱신 정책 (should_update_stop + determine_stop_action)
        current_time = self.market_data.get_timestamp()

        # Step 1: Stop 갱신 필요 여부 판단
        # ACTIVE 상태는 30초 debounce, 초기(MISSING/PENDING)는 2초
        _stop_debounce = 30.0 if self.position.stop_status == StopStatus.ACTIVE else 2.0
        if should_update_stop(
            position_qty=self.position.qty,
            stop_qty=self.position.qty if self.position.stop_order_id else 0,
            last_stop_update_at=self.last_stop_update_at,
            current_time=current_time,
            entry_working=self.position.entry_working,
            debounce_seconds=_stop_debounce,
        ):
            # Step 2: Stop action 결정 (AMEND/CANCEL_AND_PLACE/PLACE)
            action = determine_stop_action(
                stop_status=self.position.stop_status,
                amend_fail_count=self.amend_fail_count,
            )

            # Step 3: Stop 갱신 실행 (stop_manager에 위임)
            if self.rest_client is not None:
                try:
                    stop_result = execute_stop_update(
                        rest_client=self.rest_client,
                        entry_price=self.position.entry_price,
                        direction=self.position.direction,
                        current_price=self.market_data.get_current_price(),
                        atr=self.market_data.get_atr(),
                    )

                    if stop_result.stop_already_breached:
                        self.position.stop_price = stop_result.new_stop_price
                        self.position.stop_status = StopStatus.ACTIVE
                        return None

                    self.position.stop_price = stop_result.new_stop_price
                    self.position.stop_status = StopStatus.ACTIVE
                    self.position.stop_recovery_fail_count = 0
                    self.amend_fail_count = 0
                    self.last_stop_update_at = current_time

                except Exception as e:
                    err = str(e)

                    # 거래소 기준 "제로 포지션"이면 stop 복구 실패로 누적하지 말고 상태 동기화
                    if "zero position" in err.lower() and self.rest_client is not None:
                        try:
                            pos_resp = self.rest_client.get_position(category="linear", symbol="BTCUSDT")
                            plist = pos_resp.get("result", {}).get("list", [])
                            size = 0.0
                            if plist:
                                size = float(plist[0].get("size", "0") or 0)
                            if size == 0.0:
                                logger.warning("Stop update skipped: exchange position is zero -> syncing to FLAT")
                                self.state = State.FLAT
                                self.position = None
                                self.pending_order = None
                                self.pending_order_timestamp = None
                                self.amend_fail_count = 0
                                return None
                        except Exception as sync_err:
                            logger.warning(f"Position sync after stop failure failed: {sync_err}")

                    self.amend_fail_count += 1
                    self.position.stop_recovery_fail_count += 1
                    logger.warning(f"Stop update failed ({self.position.stop_recovery_fail_count}/3): {type(e).__name__}: {e}")

                    if self.position.stop_recovery_fail_count >= 3:
                        self.position.stop_status = StopStatus.ERROR

        return None

    def _decide_entry(self) -> dict:
        """
        Entry 결정 (signal → gate → sizing → order placement)

        Returns:
            {"blocked": bool, "reason": str}

        FLOW Section 2.4:
            - Step 1: FLAT 상태 확인
            - Step 2: degraded_mode 체크
            - Step 3: Signal generation (Grid-based)
            - Step 4: Entry gates 검증 (8 gates)
            - Step 5: Position sizing (loss budget + margin)
            - Step 6: Order placement (REST API)
            - Step 7: FLAT → ENTRY_PENDING 전환

        Phase 11b: Full Entry Flow 구현
        """

        # Step 1: FLAT 상태 확인
        if self.state != State.FLAT:
            return {"blocked": True, "reason": "state_not_flat"}

        # 거래소 실포지션 재확인 (고스트 진입 방지)
        if self.rest_client is not None:
            try:
                pos_resp = self.rest_client.get_position(category="linear", symbol="BTCUSDT")
                plist = pos_resp.get("result", {}).get("list", [])
                ex_size = float(plist[0].get("size", "0") or 0) if plist else 0.0
                if ex_size > 0.0:
                    # 거래소 포지션 복구 시도
                    try:
                        from application.rest_fallback import _recover_position_from_api
                        recovered = _recover_position_from_api(self.rest_client, pending_order=None)
                        if recovered is not None:
                            self.position = recovered
                            self.state = State.IN_POSITION
                            logger.warning(
                                f"exchange_position_not_flat: recovered position "
                                f"{recovered.direction.value} qty={recovered.qty} "
                                f"@ {recovered.entry_price} -> IN_POSITION"
                            )
                            return {"blocked": True, "reason": "state_not_flat"}
                    except Exception as recovery_err:
                        logger.warning(f"exchange_position_not_flat recovery failed: {recovery_err}")
                    return {"blocked": True, "reason": "exchange_position_not_flat"}
            except Exception as e:
                logger.warning(f"Entry precheck position query failed: {e}")
                return {"blocked": True, "reason": "exchange_position_not_flat"}

        # Step 2: degraded_mode 체크
        ws_degraded = self.market_data.is_ws_degraded()
        if ws_degraded:
            return {"blocked": True, "reason": "degraded_mode"}

        degraded_timeout = self.market_data.is_degraded_timeout()
        if degraded_timeout:
            self.state = State.HALT
            return {"blocked": True, "reason": "degraded_mode_timeout"}

        # Step 3: Signal generation
        # ATR 가져오기 (Grid spacing 계산용)
        atr = self.market_data.get_atr()
        if atr is None:
            return {"blocked": True, "reason": "atr_unavailable"}

        # Grid spacing 계산 (ATR * 0.3 → Wave5 Stream B: 건당 수익 기대값 50% 증가)
        self.grid_spacing = calculate_grid_spacing(atr=atr, multiplier=0.3)

        # 현재 가격
        current_price = self.market_data.get_current_price()

        # 마지막 체결 가격 (entry fill만, Grid 기준점)
        # exit fill이 LFP를 오염시키는 것을 방지하기 위해 adapter LFP 대신 직접 관리
        last_fill_price = self._last_entry_fill_price

        # Funding rate + MA slope (첫 진입 방향 결정용, Phase 13c)
        funding_rate = self.market_data.get_funding_rate()
        ma_slope_pct = self.market_data.get_ma_slope_pct()

        # S6 ThresholdCalibrator: 최초 1회 임계값 보정
        if self._threshold_config is None:
            try:
                klines = self.market_data.get_klines(500)
                self._threshold_config = self._threshold_calibrator.calibrate(klines)
                logger.info(
                    f"[Calibrate] T_TREND={self._threshold_config.t_trend:.4f}% "
                    f"T_RANGE={self._threshold_config.t_range_entry:.4f}%"
                )
            except Exception as e:
                logger.warning(f"[Calibrate] kline 데이터 미준비, 안전 기본값 사용 (T_TREND=0.05%): {e}")
                self._threshold_config = DEFAULT_THRESHOLD_CONFIG

        # Wave 2A+4: 앙상블용 klines (30초 캐시, None이면 MA slope 모드 fallback)
        # Wave 4 Stream C: highs/lows 추가 → Breakout 지표 활성화
        ens_prices, ens_volumes, ens_highs, ens_lows = self._get_price_volume_history()

        # Signal 생성 (Grid up/down, Regime-aware initial direction)
        signal: Optional[Signal] = generate_signal(
            current_price=current_price,
            last_fill_price=last_fill_price,
            grid_spacing=self.grid_spacing,
            qty=0,  # Sizing에서 계산
            funding_rate=funding_rate,
            ma_slope_pct=ma_slope_pct,
            threshold_config=self._threshold_config,
            prices=ens_prices,
            volumes=ens_volumes,
            highs=ens_highs,
            lows=ens_lows,
        )

        # Signal이 없으면 차단 (Grid spacing 범위 밖)
        if signal is None:
            logger.debug(
                f"→ Entry blocked: no_signal "
                f"(ma_slope={ma_slope_pct:.4f}%, "
                f"t_trend={self._threshold_config.t_trend:.4f}%)"
            )
            return {"blocked": True, "reason": "no_signal"}

        # Wave 5A: Regime 방향 필터 (trending 레짐에서 역방향 진입 차단)
        # trending_down → LONG(Buy) 차단, trending_up → SHORT(Sell) 차단
        # ranging / high_vol은 양방향 허용
        atr_percentile = self.market_data.get_atr_percentile()
        current_regime = self._classify_regime(ma_slope_pct=ma_slope_pct, atr_percentile=atr_percentile)
        if current_regime == "trending_down" and signal.side == "Buy":
            logger.info(
                f"→ Entry blocked: regime_direction_filter "
                f"(regime=trending_down, signal_side=Buy, ma_slope={ma_slope_pct:.4f}%)"
            )
            return {"blocked": True, "reason": "regime_direction_filter"}
        if current_regime == "trending_up" and signal.side == "Sell":
            logger.info(
                f"→ Entry blocked: regime_direction_filter "
                f"(regime=trending_up, signal_side=Sell, ma_slope={ma_slope_pct:.4f}%)"
            )
            return {"blocked": True, "reason": "regime_direction_filter"}

        # Wave 6 Stream B: ranging 레짐 진입 threshold 강화
        # ranging + score=4 → 차단 (score < 5), ranging + score=None(MA slope 모드) → 허용
        if not self._is_ranging_score_sufficient(regime=current_regime, score=signal.score):
            logger.info(
                f"→ Entry blocked: ranging_score_below_threshold "
                f"(regime={current_regime}, score={signal.score}, required>=5)"
            )
            return {"blocked": True, "reason": "ranging_score_below_threshold"}

        # Step 4: Entry gates 검증
        stage = get_stage_params()
        trades_today = self.market_data.get_trades_today()
        atr_pct_24h = self.market_data.get_atr_pct_24h()

        # Sizing 먼저 계산 (EV gate용 qty 필요)
        sizing_params = build_sizing_params(signal=signal, market_data=self.market_data, atr=atr)
        sizing_result: SizingResult = calculate_contracts(params=sizing_params)

        logger.info(f"📐 Sizing: equity=${sizing_params.equity_usdt:.2f}, price=${sizing_params.entry_price_usd:,.2f}, "
                     f"max_loss=${sizing_params.max_loss_usdt:.2f}, lev={sizing_params.leverage}x → "
                     f"contracts={sizing_result.contracts} (reject={sizing_result.reject_reason})")

        if sizing_result.contracts == 0:
            return {"blocked": True, "reason": sizing_result.reject_reason}

        # Wave 5 Stream C: DrawdownRecovery 체크 (sizing 후, entry 전)
        _today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        _daily_loss_raw = self.market_data.get_daily_realized_pnl_usd()
        _daily_loss = abs(_daily_loss_raw) if (_daily_loss_raw is not None and _daily_loss_raw < 0) else 0.0
        _drawdown_state = check_drawdown_recovery(
            daily_loss_usd=_daily_loss,
            max_loss_usd=sizing_params.max_loss_usdt,
            last_reset_date=self._drawdown_last_reset_date or _today,
            today=_today,
        )
        if _drawdown_state.reset_occurred:
            self._drawdown_last_reset_date = _today
        self._drawdown_state = _drawdown_state

        if _drawdown_state.status == "HALT":
            logger.warning(f"🛑 DrawdownRecovery HALT: {_drawdown_state.halt_reason}")
            return {"blocked": True, "reason": f"drawdown_halt: {_drawdown_state.halt_reason}"}

        if _drawdown_state.status == "REDUCE":
            logger.info(f"⚠️ DrawdownRecovery REDUCE (×{_drawdown_state.size_multiplier}): {_drawdown_state.halt_reason}")

        # Signal에 qty 업데이트 (DrawdownRecovery size_multiplier 적용)
        _effective_contracts = int(sizing_result.contracts * _drawdown_state.size_multiplier)
        if _effective_contracts == 0 and _drawdown_state.status == "REDUCE":
            logger.info("⚠️ DrawdownRecovery: size_multiplier 적용 후 contracts=0 → blocked")
            return {"blocked": True, "reason": "drawdown_reduce_contracts_zero"}
        signal.qty = sizing_result.contracts if _drawdown_state.status == "NORMAL" else _effective_contracts

        # Signal context 생성 (EV gate용)
        signal_context = build_signal_context(signal=signal, grid_spacing=self.grid_spacing)

        winrate = self.market_data.get_winrate()
        position_mode = self.market_data.get_position_mode()
        cooldown_until = None  # COOLDOWN 구현 시 추가
        current_time = self.market_data.get_timestamp()

        # Entry gates 검증
        entry_decision: EntryDecision = check_entry_allowed(
            state=self.state,
            stage=stage,
            trades_today=trades_today,
            atr_pct_24h=atr_pct_24h,
            signal=signal_context,
            winrate=winrate,
            position_mode=position_mode,
            cooldown_until=cooldown_until,
            current_time=current_time,
        )

        # Gate 거절 시 차단
        if not entry_decision.allowed:
            return {"blocked": True, "reason": entry_decision.reject_reason}

        # Step 5: Position sizing (이미 Step 4에서 계산 완료)
        contracts = sizing_result.contracts

        # Step 6: Order placement
        if self.rest_client is None:
            # REST client 없으면 차단 (Unit test에서는 None)
            return {"blocked": True, "reason": "rest_client_unavailable"}

        try:
            # Signal ID 생성
            self.current_signal_id = generate_signal_id()

            entry_qty_btc = round(contracts * 0.001, 3)  # BTC 단위 (contracts * 0.001)
            order_link_id_entry = f"entry_{self.current_signal_id}_{int(time.time())}"
            logger.info(f"📤 Entry order: {signal.side} {contracts} contracts ({entry_qty_btc} BTC) @ ${signal.price:,.2f}")
            order_result = self.rest_client.place_order(
                symbol="BTCUSDT",
                side=signal.side,
                order_type="Limit",
                qty=str(entry_qty_btc),
                price=str(signal.price),
                time_in_force="GTC",
                order_link_id=order_link_id_entry,
                category="linear",
                is_post_only=True,  # Wave5 Stream B: Maker fee 보장 (0.01% vs Taker 0.06%)
            )

            # Bybit V5 API response structure: {"result": {"orderId": "...", "orderLinkId": "..."}}
            ret_code = order_result.get("retCode", -1)
            result = order_result.get("result", {})
            order_id = result.get("orderId")
            order_link_id = result.get("orderLinkId")

            # Phase 12b Fix: Validate retCode and order_id
            if ret_code != 0 or not order_id:
                # TEST: Record failed attempt time for cooldown
                self._last_entry_attempt = time.time()
                raise ValueError(f"Entry order failed: retCode={ret_code}, response={order_result}")

        except Exception as e:
            # Order placement 실패 → 차단
            logger.error(f"❌ place_order FAILED: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # TEST: Record failed attempt time for cooldown
            self._last_entry_attempt = time.time()
            return {"blocked": True, "reason": f"order_placement_failed: {str(e)}"}

        # Step 7: FLAT → ENTRY_PENDING 전환
        self.state = State.ENTRY_PENDING

        # Trailing Stop 상태 초기화 (진입 시점)
        self.trail_price = signal.price
        self.entry_atr = atr

        # Stop distance (ATR 기반, sizing_params와 동일 계산, Wave4: ATR*0.8 clamp 0.4%~1.5%)
        if atr > 0 and signal.price > 0:
            stop_distance_pct = max(0.004, min(0.015, (atr * 0.8) / signal.price))
        else:
            stop_distance_pct = 0.01

        # Pending order 저장 (FILL event 매칭용)
        self.pending_order = {
            "order_id": order_id,
            "order_link_id": order_link_id,
            "side": signal.side,
            "qty": contracts,
            "price": signal.price,
            "signal_id": self.current_signal_id,
            "stop_distance_pct": stop_distance_pct,
            # Wave 2A: 앙상블 결과 (MA slope 모드이면 None)
            "signal_score": signal.score,
            "signal_components": signal.components,
        }

        # Wave 5A: entry signal 정보 보존 (EXIT pending_order 교체 후에도 참조 가능)
        self._entry_signal_score = signal.score
        self._entry_signal_components = signal.components

        # Phase 12a-4c: Pending order 발주 시각 기록
        self.pending_order_timestamp = time.time()

        return {"blocked": False, "reason": None}

    @staticmethod
    def _classify_regime(ma_slope_pct: float, atr_percentile: float) -> str:
        """
        Wave 5A: 현재 시장 레짐 분류.

        규칙:
        - atr_percentile >= 80 → "high_vol" (우선)
        - atr_percentile < 50 and ma_slope_pct > 0.1 → "trending_up"
        - atr_percentile < 50 and ma_slope_pct < -0.1 → "trending_down"
        - 그 외 → "ranging"

        Args:
            ma_slope_pct: MA slope (%)
            atr_percentile: ATR percentile (0-100)

        Returns:
            str: "trending_up" | "trending_down" | "ranging" | "high_vol"
        """
        if atr_percentile >= 80:
            return "high_vol"
        if atr_percentile < 50:
            if ma_slope_pct > 0.1:
                return "trending_up"
            if ma_slope_pct < -0.1:
                return "trending_down"
        return "ranging"

    @staticmethod
    def _is_ranging_score_sufficient(regime: str, score: Optional[int]) -> bool:
        """
        Wave 6 Stream B: ranging 레짐에서 앙상블 score 충분성 검증.

        ranging 레짐은 명확한 방향성이 없어 수수료 후 순손실 발생 가능.
        score >= 5를 요구하여 신호 품질을 높인다.

        규칙:
        - regime != "ranging" → 항상 True (ranging 규칙 미적용)
        - score is None (MA slope 모드) → True (체크 스킵)
        - ranging + score >= 5 → True (허용)
        - ranging + score < 5 → False (차단)

        Args:
            regime: 현재 레짐 ("ranging" | "trending_up" | "trending_down" | "high_vol")
            score: 앙상블 score (None = MA slope 모드)

        Returns:
            bool: True = 진입 허용, False = 차단
        """
        if regime != "ranging":
            return True
        if score is None:
            return True
        return score >= 5

    def _get_price_volume_history(self) -> tuple:
        """
        klines에서 prices/volumes/highs/lows 추출 (30초 캐시).

        Returns:
            (prices, volumes, highs, lows): 각 리스트.
            데이터 미준비 시 (None, None, None, None) 반환 → generate_signal은 MA slope 모드로 fallback.
        """
        now = time.time()
        if (
            self._klines_cache is not None
            and now - self._klines_cache["ts"] < self._KLINES_CACHE_TTL
        ):
            return (
                self._klines_cache["prices"],
                self._klines_cache["volumes"],
                self._klines_cache.get("highs"),
                self._klines_cache.get("lows"),
            )

        try:
            klines = self.market_data.get_klines(200)
            if not klines or len(klines) < 26:
                return None, None, None, None

            prices = [float(k.close) for k in klines]
            volumes = [float(k.volume) for k in klines]
            highs_raw = [float(k.high) for k in klines if hasattr(k, "high") and k.high is not None]
            lows_raw = [float(k.low) for k in klines if hasattr(k, "low") and k.low is not None]

            # highs/lows 길이 불일치 시 graceful fallback
            if len(highs_raw) == len(prices) and len(lows_raw) == len(prices):
                highs = highs_raw
                lows = lows_raw
            else:
                highs = None
                lows = None

            self._klines_cache = {
                "prices": prices,
                "volumes": volumes,
                "highs": highs,
                "lows": lows,
                "ts": now,
            }
            return prices, volumes, highs, lows
        except Exception as e:
            logger.warning(f"[Ensemble] klines 조회 실패 (MA slope 모드 fallback): {e}")
            return None, None, None, None
