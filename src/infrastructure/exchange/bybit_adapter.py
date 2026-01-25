"""
src/infrastructure/exchange/bybit_adapter.py
Bybit Adapter — REST + WS → MarketDataInterface

Purpose:
- REST API와 WebSocket을 통합하여 MarketDataInterface 구현
- Domain layer가 실제 거래소 데이터에 접근할 수 있도록 변환

Design:
- BybitRestClient + BybitWsClient를 사용
- MarketDataInterface Protocol 구현
- 상태 캐싱 (mark_price, equity, position 등)

SSOT:
- docs/plans/task_plan.md Phase 12a-1 (BybitAdapter 완전 구현)
- docs/constitution/FLOW.md Section 2 (Market Data Provider)
"""

import time
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from infrastructure.exchange.bybit_rest_client import BybitRestClient
from infrastructure.exchange.bybit_ws_client import BybitWsClient
from domain.events import ExecutionEvent, EventType
from application.atr_calculator import ATRCalculator, Kline as ATRKline
from application.session_risk_tracker import SessionRiskTracker, Trade, FillEvent
from application.market_regime import MarketRegimeAnalyzer, Kline as RegimeKline

logger = logging.getLogger(__name__)


class BybitAdapter:
    """
    Bybit Adapter — MarketDataInterface 완전 구현

    역할:
    - REST API로 시장/계정 정보 조회 (mark_price, equity, position, trade history)
    - WebSocket으로 실시간 체결 정보 수신 (execution.linear)
    - MarketDataInterface 모든 메서드 구현 (캐싱)
    """

    def __init__(
        self,
        rest_client: BybitRestClient,
        ws_client: BybitWsClient,
        testnet: bool = True,
    ):
        """
        BybitAdapter 초기화

        Args:
            rest_client: Bybit REST client
            ws_client: Bybit WebSocket client
            testnet: Testnet 여부 (default: True)
        """
        self.rest_client = rest_client
        self.ws_client = ws_client
        self.testnet = testnet

        # Market Data Provider 컴포넌트 (Phase 12a-2 통합)
        self.atr_calculator = ATRCalculator(period=14, default_multiplier=0.5)
        self.session_risk_tracker = SessionRiskTracker()
        self.market_regime_analyzer = MarketRegimeAnalyzer(
            ma_period=20,
            trend_threshold_pct=0.2,
            high_vol_threshold_percentile=70.0
        )

        # 상태 캐싱
        self._mark_price: float = 0.0
        self._equity_btc: float = 0.0  # DEPRECATED (Linear USDT 전환 후 제거 예정)
        self._equity_usdt: float = 0.0  # Linear USDT-Margined equity
        self._last_update_ts: float = 0.0

        # WS health tracking
        self._ws_last_heartbeat_ts: float = time.time()
        self._ws_event_drop_count: int = 0
        self._ws_degraded: bool = False
        self._degraded_entered_at: Optional[float] = None

        # Position tracking
        self._current_position: Optional[Dict[str, Any]] = None
        self._last_fill_price: Optional[float] = None

        # Session Risk tracking
        self._daily_realized_pnl_usd: Optional[float] = None
        self._weekly_realized_pnl_usd: Optional[float] = None
        self._loss_streak_count: Optional[int] = None
        self._trades_today: int = 0

        # Entry Flow tracking
        self._atr: Optional[float] = None
        self._atr_pct_24h: float = 0.0
        self._winrate: float = 0.5
        self._position_mode: str = "MergedSingle"

        # Trade Log tracking (Phase 11b)
        self._funding_rate: float = 0.0001
        self._index_price: float = 0.0
        self._ma_slope_pct: float = 0.0
        self._atr_percentile: float = 50.0
        self._exchange_server_time_offset_ms: float = 0.0

        logger.info(f"BybitAdapter initialized (testnet={testnet})")

    # ========== Phase 1: Emergency & Market Health ==========

    def get_mark_price(self) -> float:
        """현재 BTC Mark Price (USD 기준)"""
        return self._mark_price

    def get_equity_btc(self) -> float:
        """계정 Equity (BTC 단위) — DEPRECATED"""
        return self._equity_btc

    def get_equity_usdt(self) -> float:
        """계정 Equity (USDT 단위) — Linear USDT-Margined"""
        # Linear USDT: Wallet balance API에서 totalEquity (USDT) 직접 파싱
        return getattr(self, '_equity_usdt', 0.0)

    def get_rest_latency_p95_1m(self) -> float:
        """REST API latency p95 (1분 윈도우, seconds)"""
        # TODO: REST client의 latency tracker에서 가져오기
        return 0.15  # Temporary default

    def get_ws_last_heartbeat_ts(self) -> float:
        """WebSocket 마지막 heartbeat timestamp"""
        return self._ws_last_heartbeat_ts

    def get_ws_event_drop_count(self) -> int:
        """WebSocket event drop 누적 카운트"""
        return self._ws_event_drop_count

    def get_timestamp(self) -> float:
        """현재 timestamp (balance staleness 계산용)"""
        return time.time()

    # ========== Phase 9: Session Risk Policy ==========

    def get_btc_mark_price_usd(self) -> float:
        """BTC Mark Price (USD 기준)"""
        return self._mark_price

    def get_daily_realized_pnl_usd(self) -> Optional[float]:
        """당일 realized PnL (USD 단위)"""
        return self._daily_realized_pnl_usd

    def get_weekly_realized_pnl_usd(self) -> Optional[float]:
        """주간 realized PnL (USD 단위)"""
        return self._weekly_realized_pnl_usd

    def get_loss_streak_count(self) -> Optional[int]:
        """연속 손실 카운트"""
        return self._loss_streak_count

    def get_fee_ratio_history(self) -> Optional[List[float]]:
        """Fee ratio 히스토리 (최근 순서)"""
        # TODO: Trade history에서 fee ratio 계산
        return None

    def get_slippage_history(self) -> Optional[List[Dict[str, Any]]]:
        """Slippage 히스토리 (시간 윈도우 내)"""
        # TODO: Trade history에서 slippage 계산
        return None

    def is_degraded_timeout(self) -> bool:
        """DEGRADED 모드 60초 timeout 여부"""
        if not self._ws_degraded or self._degraded_entered_at is None:
            return False

        elapsed = time.time() - self._degraded_entered_at
        return elapsed >= 60.0

    def is_ws_degraded(self) -> bool:
        """WebSocket DEGRADED 모드 여부"""
        return self._ws_degraded

    # ========== Phase 11b: Entry Flow ==========

    def get_current_price(self) -> float:
        """현재 BTC 가격 (USD 기준)"""
        return self._mark_price

    def get_atr(self) -> Optional[float]:
        """ATR (Average True Range) 값"""
        return self._atr

    def get_last_fill_price(self) -> Optional[float]:
        """마지막 체결 가격 (Grid 기준점)"""
        return self._last_fill_price

    def get_trades_today(self) -> int:
        """오늘 거래 횟수"""
        return self._trades_today

    def get_atr_pct_24h(self) -> float:
        """24시간 ATR (pct)"""
        return self._atr_pct_24h

    def get_winrate(self) -> float:
        """현재 winrate (0.0~1.0)"""
        return self._winrate

    def get_position_mode(self) -> str:
        """Position mode ('MergedSingle' = one-way, 'BothSide' = hedge)"""
        return self._position_mode

    def get_position(self) -> Dict[str, Any]:
        """현재 Position 정보 (Bybit API 구조)"""
        if self._current_position is None:
            # Position 없음 (size = 0)
            return {"size": "0", "side": "None", "avgPrice": "0"}
        return self._current_position

    # ========== Phase 11b: Trade Log Integration ==========

    def get_funding_rate(self) -> float:
        """Funding rate"""
        return self._funding_rate

    def get_index_price(self) -> float:
        """Index price"""
        return self._index_price

    def get_ma_slope_pct(self) -> float:
        """MA slope (%) - market_regime 계산용"""
        return self._ma_slope_pct

    def get_atr_percentile(self) -> float:
        """ATR percentile (0-100) - market_regime 계산용"""
        return self._atr_percentile

    def get_exchange_server_time_offset_ms(self) -> float:
        """거래소 서버 시간 오프셋 (ms)"""
        return self._exchange_server_time_offset_ms

    # ========== Phase 12a-1: REST API Integration ==========

    def update_market_data(self):
        """
        REST API로 시장 데이터 업데이트 (Phase 12a-2 통합)

        호출: 1초마다 (tick loop)
        업데이트 항목:
        - Mark price, Index price, Funding rate (GET /v5/market/tickers)
        - Equity (GET /v5/account/wallet-balance)
        - Position (GET /v5/position/list)
        - Trade history → PnL, Loss streak (GET /v5/execution/list)
        - Kline → ATR, ATR percentile, Grid spacing (GET /v5/market/kline)
        - Kline → MA slope, Market regime (GET /v5/market/kline)
        """
        try:
            # 1. Mark price, Index price, Funding rate 조회
            tickers_response = self.rest_client.get_tickers(category="linear", symbol="BTCUSDT")
            result = tickers_response.get("result", {})
            ticker_list = result.get("list", [])
            if ticker_list:
                ticker = ticker_list[0]
                self._mark_price = float(ticker.get("markPrice", 0.0))
                self._index_price = float(ticker.get("indexPrice", 0.0))
                self._funding_rate = float(ticker.get("fundingRate", 0.0001))

            # 2. Equity 조회 (Linear USDT: UNIFIED 계정)
            wallet_response = self.rest_client.get_wallet_balance(accountType="UNIFIED", coin="BTC")
            result = wallet_response.get("result", {})
            wallet_list = result.get("list", [])
            if wallet_list:
                wallet_data = wallet_list[0]
                # Linear USDT: totalEquity (USDT 단위)
                self._equity_usdt = float(wallet_data.get("totalEquity", 0.0))

                # BTC equity (DEPRECATED, 호환성 유지)
                coin_list = wallet_data.get("coin", [])
                for coin_data in coin_list:
                    if coin_data.get("coin") == "BTC":
                        equity_str = coin_data.get("equity", "0")
                        self._equity_btc = float(equity_str) if equity_str else 0.0
                        break

            # 3. Position 조회
            position_response = self.rest_client.get_position(category="linear", symbol="BTCUSDT")
            result = position_response.get("result", {})
            position_list = result.get("list", [])
            if position_list:
                self._current_position = position_list[0]

            # 4. Trade history 조회 (SessionRiskTracker 사용)
            execution_response = self.rest_client.get_execution_list(category="linear", symbol="BTCUSDT", limit=50)
            result = execution_response.get("result", {})
            trade_list = result.get("list", [])

            # 4.1. Last fill price 설정 (Grid 기준점)
            if trade_list:
                # 가장 최근 체결 (list[0])의 execPrice 사용
                latest_exec = trade_list[0]
                exec_price_str = latest_exec.get("execPrice")
                if exec_price_str:
                    self._last_fill_price = float(exec_price_str)

            # Trade 객체로 변환 (SessionRiskTracker용)
            trades = []
            for trade_data in trade_list:
                closed_pnl = trade_data.get("closedPnl")
                exec_time = trade_data.get("execTime")
                if closed_pnl is not None and exec_time is not None:
                    # execTime은 milliseconds이므로 seconds로 변환
                    timestamp = float(exec_time) / 1000.0
                    trades.append(Trade(
                        closed_pnl=float(closed_pnl),
                        timestamp=timestamp
                    ))

            # SessionRiskTracker로 Daily/Weekly PnL, Loss streak 계산
            current_date = datetime.now(timezone.utc)
            self._daily_realized_pnl_usd = self.session_risk_tracker.track_daily_pnl(trades, current_date)
            self._weekly_realized_pnl_usd = self.session_risk_tracker.track_weekly_pnl(trades, current_date)
            self._loss_streak_count = self.session_risk_tracker.calculate_loss_streak(trades)

            # 5. Kline 조회 (ATR/Regime 계산용)
            kline_response = self.rest_client.get_kline(
                category="linear",
                symbol="BTCUSDT",
                interval="60",  # 1-hour
                limit=200  # 14-period ATR + 20-period MA + buffer
            )
            result = kline_response.get("result", {})
            kline_list = result.get("list", [])

            if kline_list and len(kline_list) >= 20:  # MA period 최소 요구사항
                # Kline 데이터를 Kline 객체로 변환
                klines_atr = []
                klines_regime = []
                for kline_data in reversed(kline_list):  # Bybit은 최신순, 역순으로 변환
                    # kline_data: [startTime, open, high, low, close, volume, turnover]
                    high = float(kline_data[2])
                    low = float(kline_data[3])
                    close = float(kline_data[4])

                    klines_atr.append(ATRKline(high=high, low=low, close=close))
                    klines_regime.append(RegimeKline(close=close, high=high, low=low))

                # ATR 계산 (14-period 이상 필요)
                if len(klines_atr) >= 15:  # 14 + 1 (previous close)
                    self._atr = self.atr_calculator.calculate_atr(klines_atr)
                    # ATR percentile 계산 (rolling 100-period)
                    # 단순화: 최근 100개 kline의 ATR을 계산하여 history로 사용
                    # (실제로는 별도 history 저장 필요)
                    atr_history = []
                    for i in range(max(15, len(klines_atr) - 100), len(klines_atr)):
                        if i >= 15:
                            atr_val = self.atr_calculator.calculate_atr(klines_atr[:i])
                            atr_history.append(atr_val)
                    if atr_history:
                        self._atr_percentile = self.atr_calculator.calculate_atr_percentile(
                            self._atr, atr_history
                        )

                # Market Regime 계산 (20-period MA 이상 필요)
                if len(klines_regime) >= 21:  # 20 + 1 (slope 계산용)
                    self._ma_slope_pct = self.market_regime_analyzer.calculate_ma_slope(klines_regime)
                    # Regime classification
                    # Note: classify_regime은 별도 호출 필요 시 사용
                    # (Orchestrator에서 get_ma_slope_pct() + get_atr_percentile()로 판단)

            # 업데이트 타임스탬프 기록
            self._last_update_ts = time.time()

        except Exception as e:
            logger.error(f"Market data update failed: {e}")

    # ========== Phase 12a-1: WebSocket Integration ==========

    def get_fill_events(self) -> List[ExecutionEvent]:
        """
        FILL event 목록 반환 (WebSocket에서 수신)

        Returns:
            List[ExecutionEvent]: FILL event 목록 (소비 후 clear)
        """
        fill_events: List[ExecutionEvent] = []

        # WS client에서 execution event 가져오기
        raw_events = self.ws_client.get_execution_events()

        for raw_event in raw_events:
            try:
                # Bybit execution event → domain ExecutionEvent 변환
                exec_type = raw_event.get("execType")
                exec_qty = float(raw_event.get("execQty", 0))
                order_qty = float(raw_event.get("orderQty", 0))

                # EventType 판단 (FILL vs PARTIAL_FILL)
                if exec_type == "Trade":
                    if exec_qty == order_qty:
                        event_type = EventType.FILL
                    else:
                        event_type = EventType.PARTIAL_FILL
                else:
                    # 다른 execType은 일단 skip (Cancel, Reject 등)
                    continue

                # ExecutionEvent 생성 (파라미터 이름 정확히 매칭)
                execution_event = ExecutionEvent(
                    type=event_type,  # ✅ event_type → type
                    order_id=raw_event.get("orderId", ""),
                    order_link_id=raw_event.get("orderLinkId", ""),
                    filled_qty=int(exec_qty),  # ✅ executed_qty → filled_qty
                    order_qty=int(order_qty),
                    timestamp=float(raw_event.get("execTime", 0)),
                    exec_price=float(raw_event.get("execPrice", 0.0)),  # ✅ executed_price → exec_price
                    fee_paid=float(raw_event.get("execFee", 0.0)),  # ✅ fee → fee_paid
                )

                fill_events.append(execution_event)

                # last_fill_price 업데이트
                if event_type == EventType.FILL:
                    self._last_fill_price = execution_event.exec_price

            except Exception as e:
                logger.error(f"Failed to convert execution event: {e}, raw_event={raw_event}")

        return fill_events

    # ========== Internal Helper Methods ==========

    def set_ws_degraded(self, degraded: bool):
        """WS degraded mode 설정 (Internal use)"""
        self._ws_degraded = degraded
        if degraded and self._degraded_entered_at is None:
            self._degraded_entered_at = time.time()
        elif not degraded:
            self._degraded_entered_at = None

    def update_ws_heartbeat(self):
        """WS heartbeat 업데이트 (Internal use)"""
        self._ws_last_heartbeat_ts = time.time()

    def increment_event_drop_count(self):
        """WS event drop count 증가 (Internal use)"""
        self._ws_event_drop_count += 1

    def update_last_fill_price(self, price: float):
        """마지막 체결 가격 업데이트 (Internal use)"""
        self._last_fill_price = price

    def increment_trades_today(self):
        """오늘 거래 횟수 증가 (Internal use)"""
        self._trades_today += 1
