"""
Market Data Interface (Phase 1: Emergency & WS Health)

FLOW_REF: docs/constitution/FLOW.md#1.5 (Emergency Check 데이터 제공)
Policy_REF: docs/specs/account_builder_policy.md Section 7 (Emergency 측정 정의)

Purpose:
  Emergency Check와 WS Health 판단에 필요한 시장/계정/헬스 데이터 제공.

Interface Contract:
  - Pure data provider (no business logic)
  - Implementations: FakeMarketData (test), BybitAdapter (production)
  - All methods must be callable without arguments
  - Return types must match exactly (float/int)

Measurement Definitions (Policy Section 7.1):
  - exchange_latency_rest_s: REST RTT p95 over 1 minute window
  - balance anomaly: API returns equity <= 0 OR schema invalid OR stale > 30s
  - price_drop_1m: (current_price - price_1m_ago) / price_1m_ago
  - price_drop_5m: (current_price - price_5m_ago) / price_5m_ago
"""

from typing import Protocol


class MarketDataInterface(Protocol):
    """
    Market Data Provider Interface (Protocol)

    Phase 1 최소 요구사항:
      - get_mark_price() → float (USD 기준 BTC 가격)
      - get_equity_btc() → float (계정 equity BTC)
      - get_rest_latency_p95_1m() → float (REST latency p95, seconds)
      - get_ws_last_heartbeat_ts() → float (WS 마지막 heartbeat timestamp)
      - get_ws_event_drop_count() → int (WS event drop 누적 카운트)
      - get_timestamp() → float (현재 timestamp, balance staleness 계산용)
    """

    def get_mark_price(self) -> float:
        """
        현재 BTC Mark Price (USD 기준).

        Returns:
            float: BTC mark price in USD (e.g., 42000.0)

        Used by:
            - price_drop_1m/5m 계산 (emergency.py)
        """
        ...

    def get_equity_btc(self) -> float:
        """
        계정 Equity (BTC 단위).

        Returns:
            float: Account equity in BTC (e.g., 0.0025)

        Used by:
            - balance anomaly 검증 (emergency.py)
            - equity <= 0 → HALT
        """
        ...

    def get_rest_latency_p95_1m(self) -> float:
        """
        REST API latency p95 (1분 윈도우, seconds).

        Returns:
            float: p95 latency in seconds (e.g., 0.15)

        Used by:
            - latency >= 5.0s → emergency_block=True (emergency.py)
        """
        ...

    def get_ws_last_heartbeat_ts(self) -> float:
        """
        WebSocket 마지막 heartbeat timestamp.

        Returns:
            float: Unix timestamp (e.g., 1705612800.123)

        Used by:
            - timeout > 10s → degraded_mode=True (ws_health.py)
        """
        ...

    def get_ws_event_drop_count(self) -> int:
        """
        WebSocket event drop 누적 카운트.

        Returns:
            int: Drop count (e.g., 0, 3, 10)

        Used by:
            - drop_count >= 3 → degraded_mode=True (ws_health.py)
        """
        ...

    def get_timestamp(self) -> float:
        """
        현재 timestamp (balance staleness 계산용).

        Returns:
            float: Unix timestamp (e.g., 1705612800.456)

        Used by:
            - stale_timestamp > 30s → balance anomaly → HALT (emergency.py)
        """
        ...
