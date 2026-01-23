"""
src/infrastructure/logging/trade_logger_v1.py

Phase 10: Trade Log Schema v1.0

DoD 1/5: order_id, fills, slippage, latency breakdown, funding/mark/index, integrity fields
DoD 3/5: market_regime (deterministic: MA slope + ATR percentile)
DoD 5/5: schema_version, config_hash, git_commit, exchange_server_time_offset 필수
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


class ValidationError(Exception):
    """Validation 실패 시 발생하는 예외"""

    pass


@dataclass
class TradeLogV1:
    """
    Trade Log Schema v1.0

    실행 품질 필드:
    - order_id: 거래소 주문 ID
    - fills: 체결 내역 (price, qty, fee, timestamp)
    - slippage_usd: 슬리피지 (USD)
    - latency_rest_ms: REST API 레이턴시 (ms)
    - latency_ws_ms: WebSocket 레이턴시 (ms)
    - latency_total_ms: 총 레이턴시 (ms)

    Market data:
    - funding_rate: 펀딩 비율
    - mark_price: Mark Price
    - index_price: Index Price
    - orderbook_snapshot: 오더북 스냅샷 (bid, ask, spread 등)
    - market_regime: 시장 상태 (trending_up, trending_down, ranging, high_vol)

    무결성 필드:
    - schema_version: 스키마 버전 (예: "1.0")
    - config_hash: 설정 해시 (재현성)
    - git_commit: Git 커밋 해시 (코드 버전)
    - exchange_server_time_offset_ms: 거래소 서버 시간 오프셋 (ms)
    """

    # 실행 품질 필드
    order_id: str
    fills: List[Dict[str, Any]]
    slippage_usd: float
    latency_rest_ms: float
    latency_ws_ms: float
    latency_total_ms: float

    # Market data
    funding_rate: float
    mark_price: float
    index_price: float
    orderbook_snapshot: Dict[str, Any]
    market_regime: str

    # 무결성 필드
    schema_version: str
    config_hash: str
    git_commit: str
    exchange_server_time_offset_ms: Optional[float]


def calculate_market_regime(ma_slope_pct: float, atr_percentile: float) -> str:
    """
    Market regime을 deterministic하게 계산한다.

    규칙:
    - MA slope > 0.1% and ATR percentile < 50 → trending_up
    - MA slope < -0.1% and ATR percentile < 50 → trending_down
    - ATR percentile >= 80 → high_vol
    - 그 외 → ranging

    Args:
        ma_slope_pct: Moving Average slope (%)
        atr_percentile: ATR percentile (0-100)

    Returns:
        str: market_regime ("trending_up", "trending_down", "ranging", "high_vol")
    """
    # High volatility 우선 판단
    if atr_percentile >= 80:
        return "high_vol"

    # Trending 판단 (ATR percentile < 50)
    if atr_percentile < 50:
        if ma_slope_pct > 0.1:
            return "trending_up"
        elif ma_slope_pct < -0.1:
            return "trending_down"

    # 그 외는 ranging
    return "ranging"


def validate_trade_log_v1(log: TradeLogV1) -> None:
    """
    Trade Log v1.0 validation

    필수 검증:
    - market_regime: 4개 enum 중 하나
    - schema_version: 빈 문자열 금지
    - config_hash: 빈 문자열 금지
    - git_commit: 빈 문자열 금지
    - exchange_server_time_offset_ms: None 금지

    Raises:
        ValidationError: validation 실패 시
    """
    # market_regime validation
    valid_regimes = ["trending_up", "trending_down", "ranging", "high_vol"]
    if log.market_regime not in valid_regimes:
        raise ValidationError(
            f"Invalid market_regime: {log.market_regime}. Must be one of {valid_regimes}"
        )

    # schema_version validation
    if not log.schema_version or log.schema_version.strip() == "":
        raise ValidationError("schema_version is required and cannot be empty")

    # config_hash validation
    if not log.config_hash or log.config_hash.strip() == "":
        raise ValidationError("config_hash is required and cannot be empty")

    # git_commit validation
    if not log.git_commit or log.git_commit.strip() == "":
        raise ValidationError("git_commit is required and cannot be empty")

    # exchange_server_time_offset_ms validation
    if log.exchange_server_time_offset_ms is None:
        raise ValidationError("exchange_server_time_offset_ms is required and cannot be None")
