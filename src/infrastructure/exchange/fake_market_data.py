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


class FakeMarketData:
    """
    Deterministic Market Data Provider for Testing.

    Implements MarketDataInterface with injectable state.
    """

    def __init__(self, current_price: float = 42000.0, equity_btc: float = 0.0025):
        """
        Initialize with safe defaults (no emergency triggers).

        Args:
            current_price: Mark price (USD, default 42000.0)
            equity_btc: Equity (BTC, default 0.0025)

        Defaults:
          - mark_price: 42000.0 (USD)
          - equity_btc: 0.0025 (safe, > 0)
          - rest_latency_p95_1m: 0.15 (safe, < 5.0s)
          - ws_last_heartbeat_ts: current time (fresh)
          - ws_event_drop_count: 0 (no drops)
          - timestamp: current time
          - price_1m_ago: 42000.0 (no drop)
          - price_5m_ago: 42000.0 (no drop)
        """
        self._mark_price = current_price
        self._equity_btc = equity_btc
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

    # ========== MarketDataInterface Implementation ==========

    def get_mark_price(self) -> float:
        """현재 BTC Mark Price (USD)."""
        return self._mark_price

    def get_equity_btc(self) -> float:
        """계정 Equity (BTC)."""
        return self._equity_btc

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

    def inject_fill_event(self, order_id: str, filled_qty: int):
        """
        FILL event 주입 (orchestrator test용).

        Args:
            order_id: Order ID
            filled_qty: 체결 수량
        """
        self._events.append({"type": "FILL", "order_id": order_id, "filled_qty": filled_qty})

    def inject_exit_event(self, order_id: str, filled_qty: int):
        """
        EXIT event 주입 (orchestrator test용).

        Args:
            order_id: Order ID
            filled_qty: 청산 수량
        """
        self._events.append({"type": "EXIT", "order_id": order_id, "filled_qty": filled_qty})

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
