"""
src/application/trade_logging.py
Trade logging — orchestrator.py에서 추출한 트레이드 로그 기록 함수

순수 함수: self.state, self.position 등 Write 없음 (읽기 전용 의존만)
"""

import logging
import time
from dataclasses import asdict
from typing import Dict, Any, Optional

from domain.state import Position, Direction
from infrastructure.exchange.market_data_interface import MarketDataInterface
from infrastructure.logging.trade_logger_v1 import (
    TradeLogV1,
    calculate_market_regime,
    validate_trade_log_v1,
)
from infrastructure.storage.log_storage import LogStorage

logger = logging.getLogger(__name__)


def log_estimated_trade(
    market_data: MarketDataInterface,
    log_storage: LogStorage,
    config_hash: str,
    git_commit: str,
    position: Position,
    reason: str,
) -> None:
    """
    Fill 데이터 없이 추정값으로 트레이드 로그를 기록한다.

    EXIT_PENDING -> FLAT 전환 시 execution list를 못 가져온 경우 사용.
    mark_price를 exit_price로 추정하고, config_hash에 "estimated_" prefix를 붙여 구분.

    Args:
        market_data: 시장 데이터 인터페이스
        log_storage: 로그 저장소
        config_hash: 설정 해시
        git_commit: Git 커밋 해시
        position: 청산된 포지션
        reason: 추정 로그를 쓰는 이유 (예: "no_executions", "order_id_none")
    """
    mark_price = market_data.get_mark_price()
    entry_price = position.entry_price
    direction = position.direction.value
    exit_side = "Sell" if position.direction == Direction.LONG else "Buy"
    qty_btc = position.qty * 0.001

    if position.direction == Direction.LONG:
        realized_pnl_usd = (mark_price - entry_price) * qty_btc
    else:
        realized_pnl_usd = (entry_price - mark_price) * qty_btc

    trade_log = TradeLogV1(
        order_id=f"estimated_{reason}",
        fills=[{
            "price": mark_price,
            "qty": position.qty,
            "fee": 0.0,
            "timestamp": market_data.get_timestamp(),
        }],
        slippage_usd=0.0,
        latency_rest_ms=0.0,
        latency_ws_ms=0.0,
        latency_total_ms=0.0,
        funding_rate=market_data.get_funding_rate(),
        mark_price=mark_price,
        index_price=market_data.get_index_price(),
        orderbook_snapshot={},
        market_regime=calculate_market_regime(
            ma_slope_pct=market_data.get_ma_slope_pct(),
            atr_percentile=market_data.get_atr_percentile(),
        ),
        side=exit_side,
        direction=direction,
        qty_btc=qty_btc,
        entry_price=entry_price,
        exit_price=mark_price,
        realized_pnl_usd=realized_pnl_usd,
        fee_usd=0.0,
        schema_version="1.0",
        config_hash=f"estimated_{config_hash}",
        git_commit=git_commit,
        exchange_server_time_offset_ms=market_data.get_exchange_server_time_offset_ms(),
    )

    validate_trade_log_v1(trade_log)
    log_dict = asdict(trade_log)
    log_storage.append_trade_log_v1(log_entry=log_dict, is_critical=False)
    logger.warning(
        f"Estimated trade logged ({reason}): {direction} {exit_side} {qty_btc:.4f} BTC, "
        f"entry=${entry_price:,.2f} -> exit~=${mark_price:,.2f}, PnL~=${realized_pnl_usd:,.4f}"
    )


def log_completed_trade(
    market_data: MarketDataInterface,
    log_storage: LogStorage,
    config_hash: str,
    git_commit: str,
    position: Position,
    pending_order: Optional[Dict[str, Any]],
    pending_order_timestamp: Optional[float],
    event: Any,
) -> None:
    """
    완료된 거래를 Trade Log v1.0으로 기록한다.

    Args:
        market_data: 시장 데이터 인터페이스
        log_storage: 로그 저장소
        config_hash: 설정 해시
        git_commit: Git 커밋 해시
        position: 청산된 포지션 (Exit FILL 직전 상태)
        pending_order: 대기 주문 정보
        pending_order_timestamp: 대기 주문 발주 시각
        event: Exit FILL event (ExecutionEvent dataclass 또는 dict)
    """
    # Exit fill 데이터 추출
    if hasattr(event, 'order_id'):
        # ExecutionEvent dataclass
        order_id = event.order_id or "unknown"
        exec_price = float(event.exec_price)
        exec_qty_btc = float(event.filled_qty) * 0.001
        fee_usd = abs(float(event.fee_paid)) if event.fee_paid is not None else 0.0
        event_timestamp = event.timestamp  # Bybit execTime (ms)
    else:
        # dict (REST API fallback)
        order_id = event.get("orderId", "unknown")
        exec_price = float(event.get("execPrice", 0.0))
        exec_qty_btc = float(event.get("execQty", 0.0))
        fee_usd = abs(float(event.get("execFee", 0.0)))
        event_timestamp = float(event.get("execTime", 0))

    # 거래 결과 계산
    entry_price = position.entry_price
    exit_price = exec_price
    qty_btc = exec_qty_btc
    direction = position.direction.value  # "LONG" or "SHORT"
    exit_side = "Sell" if position.direction == Direction.LONG else "Buy"

    # PnL 계산 (Linear USDT)
    if position.direction == Direction.LONG:
        realized_pnl_usd = (exit_price - entry_price) * qty_btc
    else:
        realized_pnl_usd = (entry_price - exit_price) * qty_btc

    fills = [
        {
            "price": exit_price,
            "qty": int(qty_btc * 1000),
            "fee": fee_usd,
            "timestamp": market_data.get_timestamp(),
        }
    ]

    # Market data
    funding_rate = market_data.get_funding_rate()
    mark_price = market_data.get_mark_price()
    index_price = market_data.get_index_price()

    # Market regime
    ma_slope_pct = market_data.get_ma_slope_pct()
    atr_percentile = market_data.get_atr_percentile()
    market_regime = calculate_market_regime(
        ma_slope_pct=ma_slope_pct,
        atr_percentile=atr_percentile,
    )

    exchange_server_time_offset_ms = market_data.get_exchange_server_time_offset_ms()

    # Slippage 계산: 주문 가격(expected) vs 실제 체결 가격
    expected_price = pending_order.get("price", 0.0) if pending_order else 0.0
    slippage_usd = abs(exec_price - expected_price) * qty_btc if expected_price > 0 else 0.0

    # Latency 계산: 주문 발주 시각 -> Bybit 체결 시각 -> 수신 시각
    now = time.time()
    if pending_order_timestamp and event_timestamp > 0:
        exec_time_sec = event_timestamp / 1000.0 if event_timestamp > 1e12 else event_timestamp
        latency_rest_ms = max(0.0, (exec_time_sec - pending_order_timestamp) * 1000.0)
        latency_ws_ms = max(0.0, (now - exec_time_sec) * 1000.0)
        latency_total_ms = (now - pending_order_timestamp) * 1000.0
    else:
        latency_rest_ms = 0.0
        latency_ws_ms = 0.0
        latency_total_ms = 0.0

    trade_log = TradeLogV1(
        order_id=order_id,
        fills=fills,
        slippage_usd=slippage_usd,
        latency_rest_ms=latency_rest_ms,
        latency_ws_ms=latency_ws_ms,
        latency_total_ms=latency_total_ms,
        funding_rate=funding_rate,
        mark_price=mark_price,
        index_price=index_price,
        orderbook_snapshot={},
        market_regime=market_regime,
        side=exit_side,
        direction=direction,
        qty_btc=qty_btc,
        entry_price=entry_price,
        exit_price=exit_price,
        realized_pnl_usd=realized_pnl_usd,
        fee_usd=fee_usd,
        schema_version="1.0",
        config_hash=config_hash,
        git_commit=git_commit,
        exchange_server_time_offset_ms=exchange_server_time_offset_ms,
    )

    validate_trade_log_v1(trade_log)

    log_dict = asdict(trade_log)
    log_storage.append_trade_log_v1(log_entry=log_dict, is_critical=False)
    logger.info(
        f"Trade logged: {direction} {exit_side} {qty_btc:.4f} BTC, "
        f"entry=${entry_price:,.2f} -> exit=${exit_price:,.2f}, "
        f"PnL=${realized_pnl_usd:,.4f}, fee=${fee_usd:,.4f}"
    )
