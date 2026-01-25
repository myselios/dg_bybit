"""
Fake Market Data (Phase 1: Deterministic Test Data Injection)

Purpose:
  emergency.py와 ws_health.py 테스트를 위한 deterministic data provider.

Usage:
  ```python
  fake_data = FakeMarketData()
  fake_data.inject_price_drop(pct_1m=-0.12, pct_5m=-0.08)
  fake_data.inject_latency(value_s=6.0)

  emergency_status = check_emergency(fake_data)
  assert emergency_status.is_blocked == True  # latency >= 5.0s
  ```

Design:
  - MarketDataInterface 구현
  - 테스트에서 상태 주입 가능 (inject_* 메서드)
  - Default 값은 모두 "정상" 상태 (emergency 트리거 안 됨)
"""

import time
from typing import Optional, List, Dict, Any


class FakeMarketData:
    """
    Deterministic Market Data Provider for Testing.

    Implements MarketDataInterface with injectable state.
    """

    def __init__(
        self,
        current_price: float = 42000.0,
        equity_btc: float = 0.0025,
        equity_usdt: Optional[float] = None,
    ):
        """
        Initialize with safe defaults (no emergency triggers).

        Args:
            current_price: Mark price (USD, default 42000.0)
            equity_btc: Equity (BTC, default 0.0025) — DEPRECATED, Linear USDT 전환 후 제거
            equity_usdt: Equity (USDT, Linear) — 지정 시 이 값 사용, 미지정 시 equity_btc * current_price

        Defaults:
          - mark_price: 42000.0 (USD)
          - equity_btc: 0.0025 (safe, > 0)
          - equity_usdt: None (auto-calculated from equity_btc)
          - rest_latency_p95_1m: 0.15 (safe, < 5.0s)
          - ws_last_heartbeat_ts: current time (fresh)
          - ws_event_drop_count: 0 (no drops)
          - timestamp: current time
          - price_1m_ago: 42000.0 (no drop)
          - price_5m_ago: 42000.0 (no drop)
        """
        self._mark_price = current_price
        self._equity_btc = equity_btc
        self._equity_usdt = equity_usdt if equity_usdt is not None else (equity_btc * current_price)
        self._rest_latency_p95_1m = 0.15
        self._ws_last_heartbeat_ts = time.time()
        self._ws_event_drop_count = 0
        self._timestamp = time.time()

        # Price history (for drop calculation)
        self._price_1m_ago = current_price
        self._price_5m_ago = current_price

        # Balance staleness control
        self._balance_ts = time.time()

        # Phase 6: Orchestrator test support
        self._ws_degraded = False
        self._degraded_entered_at = None
        self._signal = None
        self._events = []

        # Phase 9: Session Risk test support
        self._daily_realized_pnl_usd: Optional[float] = None
        self._weekly_realized_pnl_usd: Optional[float] = None
        self._loss_streak_count: Optional[int] = None
        self._fee_ratio_history: Optional[List[float]] = None
        self._slippage_history: Optional[List[Dict[str, Any]]] = None

        # Phase 11b: Entry Flow test support
        self._atr: Optional[float] = 100.0  # Default ATR (Grid spacing용)
        self._last_fill_price: Optional[float] = None  # Default None (Entry 불가 상태)
        self._trades_today: int = 0  # Default 0 (거래 없음)
        self._atr_pct_24h: float = 0.03  # Default 3% (ATR gate 통과)
        self._winrate: float = 0.6  # Default 60% (winrate gate 통과)
        self._position_mode: str = "MergedSingle"  # Default one-way mode

    # ========== MarketDataInterface Implementation ==========

    def get_mark_price(self) -> float:
        """현재 BTC Mark Price (USD)."""
        return self._mark_price

    def get_equity_btc(self) -> float:
        """계정 Equity (BTC) — DEPRECATED."""
        return self._equity_btc

    def get_equity_usdt(self) -> float:
        """계정 Equity (USDT) — Linear USDT-Margined."""
        # Linear USDT: equity_usdt = equity_btc * mark_price (근사)
        # 하지만 Fake에서는 직접 값 저장 (테스트 제어 편의성)
        return getattr(self, '_equity_usdt', self._equity_btc * self._mark_price)

    def get_rest_latency_p95_1m(self) -> float:
        """REST latency p95 (seconds)."""
        return self._rest_latency_p95_1m

    def get_ws_last_heartbeat_ts(self) -> float:
        """WS 마지막 heartbeat timestamp."""
        return self._ws_last_heartbeat_ts

    def get_ws_event_drop_count(self) -> int:
        """WS event drop 누적 카운트."""
        return self._ws_event_drop_count

    def get_timestamp(self) -> float:
        """현재 timestamp."""
        return self._timestamp

    # ========== Test Injection Methods ==========

    def inject_price_drop(self, pct_1m: float, pct_5m: float):
        """
        Price drop 주입 (emergency 트리거 테스트용).

        Args:
            pct_1m: 1분 가격 변화율 (e.g., -0.12 = -12%)
            pct_5m: 5분 가격 변화율 (e.g., -0.22 = -22%)

        Example:
            fake_data.inject_price_drop(pct_1m=-0.12, pct_5m=-0.08)
            # → price_drop_1m: -12% (COOLDOWN 트리거)
        """
        self._price_1m_ago = self._mark_price / (1 + pct_1m)
        self._price_5m_ago = self._mark_price / (1 + pct_5m)

    def inject_latency(self, value_s: float):
        """
        REST latency 주입.

        Args:
            value_s: latency p95 (seconds, e.g., 6.0)

        Example:
            fake_data.inject_latency(value_s=6.0)
            # → latency >= 5.0s (emergency_block 트리거)
        """
        self._rest_latency_p95_1m = value_s

    def inject_balance_anomaly(self):
        """
        Balance anomaly 주입 (HALT 트리거 테스트용).

        Options:
          - (A) equity <= 0
          - (B) stale timestamp > 30s

        현재는 (A) equity = 0 주입.
        """
        self._equity_btc = 0.0

    def inject_ws_event(self, heartbeat_ok: bool, event_drop_count: int):
        """
        WS health event 주입.

        Args:
            heartbeat_ok: True이면 fresh, False이면 timeout > 10s
            event_drop_count: event drop 누적 카운트 (>= 3이면 degraded)

        Example:
            fake_data.inject_ws_event(heartbeat_ok=False, event_drop_count=0)
            # → heartbeat timeout > 10s (degraded 트리거)

            fake_data.inject_ws_event(heartbeat_ok=True, event_drop_count=5)
            # → event drop >= 3 (degraded 트리거)
        """
        if heartbeat_ok:
            self._ws_last_heartbeat_ts = time.time()
        else:
            # 11초 전으로 설정 (timeout > 10s 트리거)
            self._ws_last_heartbeat_ts = time.time() - 11.0

        self._ws_event_drop_count = event_drop_count

    def inject_stale_balance(self, stale_seconds: float):
        """
        Balance staleness 주입 (> 30s → HALT).

        Args:
            stale_seconds: balance 데이터가 얼마나 오래되었는지 (seconds)

        Example:
            fake_data.inject_stale_balance(stale_seconds=35.0)
            # → stale > 30s (HALT 트리거)
        """
        self._balance_ts = self._timestamp - stale_seconds

    # ========== Helper Methods for Tests ==========

    def get_price_drop_1m(self) -> float:
        """
        Calculate price_drop_1m for verification.

        Returns:
            float: (current - 1m_ago) / 1m_ago (e.g., -0.12 = -12%)
        """
        if self._price_1m_ago == 0:
            return 0.0
        return (self._mark_price - self._price_1m_ago) / self._price_1m_ago

    def get_price_drop_5m(self) -> float:
        """
        Calculate price_drop_5m for verification.

        Returns:
            float: (current - 5m_ago) / 5m_ago (e.g., -0.22 = -22%)
        """
        if self._price_5m_ago == 0:
            return 0.0
        return (self._mark_price - self._price_5m_ago) / self._price_5m_ago

    def get_balance_staleness(self) -> float:
        """
        Calculate balance staleness (seconds).

        Returns:
            float: timestamp - balance_ts (e.g., 35.0)
        """
        return self._timestamp - self._balance_ts

    # ========== Phase 6: Orchestrator Test Support ==========

    def set_signal(self, side: str, qty: int):
        """
        Entry signal 주입 (orchestrator test용).

        Args:
            side: "Buy" or "Sell"
            qty: 수량 (contracts)
        """
        self._signal = {"side": side, "qty": qty}

    def inject_fill_event(
        self,
        order_id: str,
        filled_qty: int,
        order_link_id: Optional[str] = None,
        side: Optional[str] = None,
        price: Optional[float] = None,
    ):
        """
        FILL event 주입 (orchestrator test용).

        Args:
            order_id: Order ID (Bybit 서버 생성)
            filled_qty: 체결 수량
            order_link_id: Order Link ID (클라이언트 ID, Optional)
            side: "Buy" or "Sell" (Optional)
            price: 체결 가격 (Optional)
        """
        event = {
            "type": "FILL",
            "orderId": order_id,  # Bybit API 형식 (camelCase)
            "execQty": str(filled_qty),  # Bybit API는 string
        }
        if order_link_id:
            event["orderLinkId"] = order_link_id
        if side:
            event["side"] = side
        if price:
            event["execPrice"] = str(price)

        self._events.append(event)

    def inject_exit_event(
        self,
        order_id: str,
        filled_qty: int,
        order_link_id: Optional[str] = None,
        side: Optional[str] = None,
        price: Optional[float] = None,
    ):
        """
        EXIT event 주입 (orchestrator test용).

        Args:
            order_id: Order ID (Bybit 서버 생성)
            filled_qty: 청산 수량
            order_link_id: Order Link ID (클라이언트 ID, Optional)
            side: "Buy" or "Sell" (Optional)
            price: 체결 가격 (Optional)
        """
        event = {
            "type": "EXIT",
            "orderId": order_id,
            "execQty": str(filled_qty),
        }
        if order_link_id:
            event["orderLinkId"] = order_link_id
        if side:
            event["side"] = side
        if price:
            event["execPrice"] = str(price)

        self._events.append(event)

    def get_fill_events(self) -> List[Dict[str, Any]]:
        """
        FILL event 목록 반환 (orchestrator test용).

        Returns:
            List[Dict]: FILL event 목록 (소비 후 clear)
        """
        events = self._events.copy()
        self._events.clear()  # 소비 후 clear (중복 처리 방지)
        return events

    def set_ws_degraded(self, degraded: bool, entered_at_offset: float = 0.0):
        """
        WS degraded mode 설정 (orchestrator test용).

        Args:
            degraded: True이면 degraded mode
            entered_at_offset: degraded 진입 시각 offset (초, 음수면 과거)
        """
        self._ws_degraded = degraded
        if degraded:
            self._degraded_entered_at = time.time() + entered_at_offset

    def is_ws_degraded(self) -> bool:
        """
        WS degraded mode 여부 반환.

        Returns:
            bool: degraded mode이면 True
        """
        return self._ws_degraded

    def is_degraded_timeout(self) -> bool:
        """
        Degraded timeout (60초 경과) 여부 반환.

        Returns:
            bool: degraded 60초 경과 시 True
        """
        if not self._ws_degraded or self._degraded_entered_at is None:
            return False

        elapsed = time.time() - self._degraded_entered_at
        return elapsed >= 60.0

    # ========== Phase 9: Session Risk Protocol Methods ==========

    def get_btc_mark_price_usd(self) -> float:
        """BTC Mark Price (USD 기준)."""
        return self._mark_price

    def get_daily_realized_pnl_usd(self) -> Optional[float]:
        """당일 realized PnL (USD 단위)."""
        return self._daily_realized_pnl_usd

    def get_weekly_realized_pnl_usd(self) -> Optional[float]:
        """주간 realized PnL (USD 단위)."""
        return self._weekly_realized_pnl_usd

    def get_loss_streak_count(self) -> Optional[int]:
        """연속 손실 카운트."""
        return self._loss_streak_count

    def get_fee_ratio_history(self) -> Optional[List[float]]:
        """Fee ratio 히스토리 (최근 순서)."""
        return self._fee_ratio_history

    def get_slippage_history(self) -> Optional[List[Dict[str, Any]]]:
        """Slippage 히스토리 (시간 윈도우 내)."""
        return self._slippage_history

    # ========== Phase 11b: Entry Flow Methods ==========

    def get_current_price(self) -> float:
        """현재 BTC 가격 (USD 기준)."""
        return self._mark_price  # Alias for get_mark_price()

    def get_atr(self) -> Optional[float]:
        """ATR (Average True Range) 값."""
        return self._atr

    def get_last_fill_price(self) -> Optional[float]:
        """마지막 체결 가격 (Grid 기준점)."""
        return self._last_fill_price

    def get_trades_today(self) -> int:
        """오늘 거래 횟수."""
        return self._trades_today

    def get_atr_pct_24h(self) -> float:
        """24시간 ATR (pct)."""
        return self._atr_pct_24h

    def get_winrate(self) -> float:
        """현재 winrate (0.0~1.0)."""
        return self._winrate

    def get_position_mode(self) -> str:
        """Position mode ('MergedSingle' = one-way, 'BothSide' = hedge)."""
        return self._position_mode

    # ========== Phase 11b: Test Injection Methods ==========

    def inject_atr(self, atr: float):
        """
        ATR 주입 (Signal generation test용).

        Args:
            atr: ATR 값 (e.g., 100.0)
        """
        self._atr = atr

    def inject_last_fill_price(self, price: float):
        """
        마지막 체결 가격 주입 (Grid signal test용).

        Args:
            price: 마지막 체결 가격 (e.g., 49800.0)
        """
        self._last_fill_price = price

    def inject_trades_today(self, count: int):
        """
        오늘 거래 횟수 주입 (Entry gate test용).

        Args:
            count: 거래 횟수 (e.g., 5)
        """
        self._trades_today = count

    def inject_atr_pct_24h(self, atr_pct: float):
        """
        24시간 ATR (pct) 주입 (Entry gate test용).

        Args:
            atr_pct: ATR pct (e.g., 0.03 = 3%)
        """
        self._atr_pct_24h = atr_pct

    def inject_winrate(self, winrate: float):
        """
        Winrate 주입 (Entry gate test용).

        Args:
            winrate: Winrate (0.0~1.0, e.g., 0.6 = 60%)
        """
        self._winrate = winrate

    def inject_position_mode(self, mode: str):
        """
        Position mode 주입 (Entry gate test용).

        Args:
            mode: Position mode ("MergedSingle" or "BothSide")
        """
        self._position_mode = mode

    # ========== Phase 11b: Trade Log Integration Methods ==========

    def get_funding_rate(self) -> float:
        """Funding rate (기본값: 0.0001 = 0.01%)."""
        return 0.0001

    def get_index_price(self) -> float:
        """Index price (Mark price와 동일하게 설정)."""
        return self._mark_price

    def get_ma_slope_pct(self) -> float:
        """MA slope (%) - market_regime 계산용 (기본값: 0.05 = 5%)."""
        return 0.05

    def get_atr_percentile(self) -> float:
        """ATR percentile (0-100) - market_regime 계산용 (기본값: 40.0)."""
        return 40.0

    def get_exchange_server_time_offset_ms(self) -> float:
        """거래소 서버 시간 오프셋 (ms) - 기본값: 10.0ms."""
        return 10.0
