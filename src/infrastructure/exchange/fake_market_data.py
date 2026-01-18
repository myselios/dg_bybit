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

    def __init__(self):
        """
        Initialize with safe defaults (no emergency triggers).

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
        self._mark_price = 42000.0
        self._equity_btc = 0.0025
        self._rest_latency_p95_1m = 0.15
        self._ws_last_heartbeat_ts = time.time()
        self._ws_event_drop_count = 0
        self._timestamp = time.time()

        # Price history (for drop calculation)
        self._price_1m_ago = 42000.0
        self._price_5m_ago = 42000.0

        # Balance staleness control
        self._balance_ts = time.time()

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
