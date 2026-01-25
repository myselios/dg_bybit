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

from typing import Protocol, Optional, List, Dict, Any


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

    Phase 9 Session Risk 확장 (Optional 메서드):
      - get_btc_mark_price_usd() → float (BTC mark price USD)
      - get_daily_realized_pnl_usd() → Optional[float] (당일 realized PnL)
      - get_weekly_realized_pnl_usd() → Optional[float] (주간 realized PnL)
      - get_loss_streak_count() → Optional[int] (연속 손실 카운트)
      - get_fee_ratio_history() → Optional[List[float]] (Fee ratio 히스토리)
      - get_slippage_history() → Optional[List[Dict[str, Any]]] (Slippage 히스토리)
      - is_degraded_timeout() → bool (DEGRADED 60초 timeout 여부)
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
        계정 Equity (BTC 단위) — DEPRECATED, Linear USDT 전환 후 제거 예정.

        Returns:
            float: Account equity in BTC (e.g., 0.0025)

        Used by:
            - balance anomaly 검증 (emergency.py)
            - equity <= 0 → HALT

        Note: Linear USDT 전환 후 get_equity_usdt() 사용 권장
        """
        ...

    def get_equity_usdt(self) -> float:
        """
        계정 Equity (USDT 단위) — Linear USDT-Margined.

        Returns:
            float: Account equity in USDT (e.g., 1000.0)

        Used by:
            - Sizing calculation (entry_coordinator.py)
            - Balance anomaly 검증 (emergency.py)
            - equity <= 0 → HALT

        SSOT: ADR-0002 (Inverse to Linear USDT Migration)
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

    # ========================================================================
    # Phase 9 Session Risk Policy (Optional 메서드)
    # ========================================================================

    def get_btc_mark_price_usd(self) -> float:
        """
        BTC Mark Price (USD 기준).

        Returns:
            float: BTC mark price in USD (e.g., 100000.0)

        Used by:
            - Session Risk Policy (equity_usd 계산)
        """
        ...

    def get_daily_realized_pnl_usd(self) -> Optional[float]:
        """
        당일 realized PnL (USD 단위).

        Returns:
            Optional[float]: 당일 realized PnL (e.g., -5.0), None이면 Session Risk 미지원

        Used by:
            - Daily Loss Cap (session_risk.py)
        """
        ...

    def get_weekly_realized_pnl_usd(self) -> Optional[float]:
        """
        주간 realized PnL (USD 단위).

        Returns:
            Optional[float]: 주간 realized PnL (e.g., -12.5), None이면 Session Risk 미지원

        Used by:
            - Weekly Loss Cap (session_risk.py)
        """
        ...

    def get_loss_streak_count(self) -> Optional[int]:
        """
        연속 손실 카운트.

        Returns:
            Optional[int]: 연속 손실 카운트 (e.g., 0, 3, 5), None이면 Session Risk 미지원

        Used by:
            - Loss Streak Kill (session_risk.py)
        """
        ...

    def get_fee_ratio_history(self) -> Optional[List[float]]:
        """
        Fee ratio 히스토리 (최근 순서).

        Returns:
            Optional[List[float]]: Fee ratio 히스토리 (e.g., [1.6, 1.7]), None이면 Session Risk 미지원

        Used by:
            - Fee Anomaly Detection (session_risk.py)
        """
        ...

    def get_slippage_history(self) -> Optional[List[Dict[str, Any]]]:
        """
        Slippage 히스토리 (시간 윈도우 내).

        Returns:
            Optional[List[Dict[str, Any]]]: Slippage 히스토리
                [{"slippage_usd": -2.5, "timestamp": 1737600000.0}, ...]
                None이면 Session Risk 미지원

        Used by:
            - Slippage Anomaly Detection (session_risk.py)
        """
        ...

    def is_degraded_timeout(self) -> bool:
        """
        DEGRADED 모드 60초 timeout 여부.

        Returns:
            bool: DEGRADED 60초 경과 시 True

        Used by:
            - Emergency Check (orchestrator.py)
        """
        ...

    def is_ws_degraded(self) -> bool:
        """
        WebSocket DEGRADED 모드 여부.

        Returns:
            bool: WS DEGRADED 모드이면 True

        Used by:
            - Entry decision (orchestrator.py)
        """
        ...

    # ========================================================================
    # Phase 11b Entry Flow (Signal Generation + Entry Gates)
    # ========================================================================

    def get_current_price(self) -> float:
        """
        현재 BTC 가격 (USD 기준).

        Returns:
            float: 현재 BTC 가격 (e.g., 50000.0)

        Used by:
            - Signal generation (signal_generator.py)
            - Stop hit check (exit_manager.py)
        """
        ...

    def get_atr(self) -> Optional[float]:
        """
        ATR (Average True Range) 값.

        Returns:
            Optional[float]: ATR 값 (e.g., 100.0), None이면 Entry 불가

        Used by:
            - Grid spacing 계산 (signal_generator.calculate_grid_spacing)
        """
        ...

    def get_last_fill_price(self) -> Optional[float]:
        """
        마지막 체결 가격 (Grid 기준점).

        Returns:
            Optional[float]: 마지막 체결 가격 (e.g., 49800.0), None이면 Entry 불가

        Used by:
            - Signal generation (signal_generator.generate_signal)
        """
        ...

    def get_trades_today(self) -> int:
        """
        오늘 거래 횟수.

        Returns:
            int: 오늘 거래 횟수 (e.g., 5)

        Used by:
            - Entry gate (max_trades_per_day)
        """
        ...

    def get_atr_pct_24h(self) -> float:
        """
        24시간 ATR (pct).

        Returns:
            float: 24시간 ATR (pct, e.g., 0.03 = 3%)

        Used by:
            - Entry gate (ATR gate)
        """
        ...

    def get_winrate(self) -> float:
        """
        현재 winrate (0.0~1.0).

        Returns:
            float: Winrate (e.g., 0.6 = 60%)

        Used by:
            - Entry gate (winrate gate)
        """
        ...

    def get_position_mode(self) -> str:
        """
        Position mode ("MergedSingle" = one-way, "BothSide" = hedge).

        Returns:
            str: Position mode (e.g., "MergedSingle")

        Used by:
            - Entry gate (one-way mode 검증)
        """
        ...

    def get_position(self) -> Dict[str, Any]:
        """
        현재 Position 정보 (Bybit API 구조).

        Returns:
            Dict[str, Any]: Position data
                - size: Position size (BTC 단위, "0"이면 포지션 없음)
                - side: "Buy", "Sell", "None"
                - avgPrice: Average entry price

        Used by:
            - Orchestrator startup (position recovery)
        """
        ...
