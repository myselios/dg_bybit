"""
tests/unit/test_trade_logger_v1.py

Phase 10: Trade Log Schema v1.0 테스트

DoD 1/5: order_id, fills, slippage, latency breakdown, funding/mark/index, integrity fields
DoD 3/5: market_regime 필수 (deterministic: MA slope + ATR percentile)
DoD 5/5: schema_version, config_hash, git_commit, exchange_server_time_offset 필수

Failure-mode tests:
- schema_version/config_hash/git_commit 필드 누락 시 validation FAIL
- market_regime deterministic 계산 검증
"""

import pytest
from dataclasses import asdict


# Test 1: DoD 1/5 - 모든 실행 품질 필드 포함
def test_trade_log_v1_contains_all_execution_quality_fields():
    """
    DoD 1/5: Trade Log v1.0에 order_id, fills, slippage, latency breakdown,
    funding/mark/index 필드가 모두 포함되어야 한다.
    """
    from src.infrastructure.logging.trade_logger_v1 import TradeLogV1

    log = TradeLogV1(
        order_id="test_order_123",
        fills=[{"price": 50000.0, "qty": 100, "fee": 0.05}],
        slippage_usd=0.5,
        latency_rest_ms=150.0,
        latency_ws_ms=50.0,
        latency_total_ms=200.0,
        funding_rate=0.0001,
        mark_price=50000.0,
        index_price=50001.0,
        orderbook_snapshot={"bid": 49999.0, "ask": 50001.0},
        market_regime="ranging",
        schema_version="1.0",
        config_hash="abc123",
        git_commit="5d928f5",
        exchange_server_time_offset_ms=10.0,
    )

    # 모든 필드가 존재해야 함
    log_dict = asdict(log)
    assert "order_id" in log_dict
    assert "fills" in log_dict
    assert "slippage_usd" in log_dict
    assert "latency_rest_ms" in log_dict
    assert "latency_ws_ms" in log_dict
    assert "latency_total_ms" in log_dict
    assert "funding_rate" in log_dict
    assert "mark_price" in log_dict
    assert "index_price" in log_dict
    assert "orderbook_snapshot" in log_dict
    assert log_dict["order_id"] == "test_order_123"
    assert len(log_dict["fills"]) == 1


# Test 2: DoD 3/5 - market_regime 필드 필수
def test_trade_log_v1_market_regime_required():
    """
    DoD 3/5: market_regime 필드가 필수이며, 4개 enum 중 하나여야 한다.
    (trending_up, trending_down, ranging, high_vol)
    """
    from src.infrastructure.logging.trade_logger_v1 import TradeLogV1, validate_trade_log_v1

    log = TradeLogV1(
        order_id="test_order_123",
        fills=[],
        slippage_usd=0.0,
        latency_rest_ms=0.0,
        latency_ws_ms=0.0,
        latency_total_ms=0.0,
        funding_rate=0.0,
        mark_price=50000.0,
        index_price=50000.0,
        orderbook_snapshot={},
        market_regime="ranging",  # 필수
        schema_version="1.0",
        config_hash="abc123",
        git_commit="5d928f5",
        exchange_server_time_offset_ms=0.0,
    )

    # Validation 통과해야 함
    validate_trade_log_v1(log)

    # market_regime이 enum 값이어야 함
    assert log.market_regime in ["trending_up", "trending_down", "ranging", "high_vol"]


# Test 3: DoD 5/5 - schema_version 필드 필수
def test_trade_log_v1_schema_version_required():
    """
    DoD 5/5: schema_version 필드가 누락되면 validation FAIL
    """
    from src.infrastructure.logging.trade_logger_v1 import TradeLogV1, validate_trade_log_v1, ValidationError

    log = TradeLogV1(
        order_id="test_order_123",
        fills=[],
        slippage_usd=0.0,
        latency_rest_ms=0.0,
        latency_ws_ms=0.0,
        latency_total_ms=0.0,
        funding_rate=0.0,
        mark_price=50000.0,
        index_price=50000.0,
        orderbook_snapshot={},
        market_regime="ranging",
        schema_version="",  # 빈 문자열 → FAIL
        config_hash="abc123",
        git_commit="5d928f5",
        exchange_server_time_offset_ms=0.0,
    )

    with pytest.raises(ValidationError, match="schema_version"):
        validate_trade_log_v1(log)


# Test 4: DoD 5/5 - config_hash 필드 필수
def test_trade_log_v1_config_hash_required():
    """
    DoD 5/5: config_hash 필드가 누락되면 validation FAIL
    """
    from src.infrastructure.logging.trade_logger_v1 import TradeLogV1, validate_trade_log_v1, ValidationError

    log = TradeLogV1(
        order_id="test_order_123",
        fills=[],
        slippage_usd=0.0,
        latency_rest_ms=0.0,
        latency_ws_ms=0.0,
        latency_total_ms=0.0,
        funding_rate=0.0,
        mark_price=50000.0,
        index_price=50000.0,
        orderbook_snapshot={},
        market_regime="ranging",
        schema_version="1.0",
        config_hash="",  # 빈 문자열 → FAIL
        git_commit="5d928f5",
        exchange_server_time_offset_ms=0.0,
    )

    with pytest.raises(ValidationError, match="config_hash"):
        validate_trade_log_v1(log)


# Test 5: DoD 5/5 - git_commit 필드 필수
def test_trade_log_v1_git_commit_required():
    """
    DoD 5/5: git_commit 필드가 누락되면 validation FAIL
    """
    from src.infrastructure.logging.trade_logger_v1 import TradeLogV1, validate_trade_log_v1, ValidationError

    log = TradeLogV1(
        order_id="test_order_123",
        fills=[],
        slippage_usd=0.0,
        latency_rest_ms=0.0,
        latency_ws_ms=0.0,
        latency_total_ms=0.0,
        funding_rate=0.0,
        mark_price=50000.0,
        index_price=50000.0,
        orderbook_snapshot={},
        market_regime="ranging",
        schema_version="1.0",
        config_hash="abc123",
        git_commit="",  # 빈 문자열 → FAIL
        exchange_server_time_offset_ms=0.0,
    )

    with pytest.raises(ValidationError, match="git_commit"):
        validate_trade_log_v1(log)


# Test 6: DoD 3/5 - market_regime deterministic 계산 (MA slope + ATR percentile)
def test_market_regime_deterministic_calculation():
    """
    DoD 3/5: market_regime은 MA slope + ATR percentile로 deterministic하게 계산되어야 한다.

    규칙 (예시):
    - MA slope > 0.1% and ATR percentile < 50 → trending_up
    - MA slope < -0.1% and ATR percentile < 50 → trending_down
    - ATR percentile >= 80 → high_vol
    - 그 외 → ranging
    """
    from src.infrastructure.logging.trade_logger_v1 import calculate_market_regime

    # Case 1: trending_up (MA slope > 0.1%, ATR percentile < 50)
    regime = calculate_market_regime(ma_slope_pct=0.15, atr_percentile=30.0)
    assert regime == "trending_up"

    # Case 2: trending_down (MA slope < -0.1%, ATR percentile < 50)
    regime = calculate_market_regime(ma_slope_pct=-0.15, atr_percentile=30.0)
    assert regime == "trending_down"

    # Case 3: high_vol (ATR percentile >= 80)
    regime = calculate_market_regime(ma_slope_pct=0.05, atr_percentile=85.0)
    assert regime == "high_vol"

    # Case 4: ranging (그 외)
    regime = calculate_market_regime(ma_slope_pct=0.05, atr_percentile=40.0)
    assert regime == "ranging"


# Test 7: Invalid market_regime enum
def test_trade_log_v1_invalid_market_regime_fails():
    """
    DoD 3/5: market_regime이 4개 enum 외의 값이면 validation FAIL
    """
    from src.infrastructure.logging.trade_logger_v1 import TradeLogV1, validate_trade_log_v1, ValidationError

    log = TradeLogV1(
        order_id="test_order_123",
        fills=[],
        slippage_usd=0.0,
        latency_rest_ms=0.0,
        latency_ws_ms=0.0,
        latency_total_ms=0.0,
        funding_rate=0.0,
        mark_price=50000.0,
        index_price=50000.0,
        orderbook_snapshot={},
        market_regime="invalid_regime",  # 잘못된 값
        schema_version="1.0",
        config_hash="abc123",
        git_commit="5d928f5",
        exchange_server_time_offset_ms=0.0,
    )

    with pytest.raises(ValidationError, match="market_regime"):
        validate_trade_log_v1(log)


# Test 8: exchange_server_time_offset 필수
def test_trade_log_v1_exchange_server_time_offset_required():
    """
    DoD 5/5: exchange_server_time_offset_ms 필드가 필수이며, None이면 validation FAIL
    """
    from src.infrastructure.logging.trade_logger_v1 import TradeLogV1, validate_trade_log_v1, ValidationError

    log = TradeLogV1(
        order_id="test_order_123",
        fills=[],
        slippage_usd=0.0,
        latency_rest_ms=0.0,
        latency_ws_ms=0.0,
        latency_total_ms=0.0,
        funding_rate=0.0,
        mark_price=50000.0,
        index_price=50000.0,
        orderbook_snapshot={},
        market_regime="ranging",
        schema_version="1.0",
        config_hash="abc123",
        git_commit="5d928f5",
        exchange_server_time_offset_ms=None,  # None → FAIL
    )

    with pytest.raises(ValidationError, match="exchange_server_time_offset"):
        validate_trade_log_v1(log)


# Test 9: 전체 필드 validation 통과
def test_trade_log_v1_full_validation_pass():
    """
    모든 필드가 올바르게 설정되면 validation 통과
    """
    from src.infrastructure.logging.trade_logger_v1 import TradeLogV1, validate_trade_log_v1

    log = TradeLogV1(
        order_id="order_abc123",
        fills=[
            {"price": 50000.0, "qty": 50, "fee": 0.025, "timestamp": 1706000000},
            {"price": 50001.0, "qty": 50, "fee": 0.025, "timestamp": 1706000001},
        ],
        slippage_usd=1.5,
        latency_rest_ms=120.0,
        latency_ws_ms=30.0,
        latency_total_ms=150.0,
        funding_rate=0.0001,
        mark_price=50000.5,
        index_price=50001.2,
        orderbook_snapshot={"bid": 49999.5, "ask": 50000.5, "spread": 1.0},
        market_regime="trending_up",
        schema_version="1.0",
        config_hash="abc123def456",
        git_commit="5d928f5a1b2c3d4e",
        exchange_server_time_offset_ms=12.5,
    )

    # Validation 통과 (예외 없음)
    validate_trade_log_v1(log)

    # 모든 필드 검증
    assert log.order_id == "order_abc123"
    assert len(log.fills) == 2
    assert log.slippage_usd == 1.5
    assert log.market_regime == "trending_up"
    assert log.schema_version == "1.0"
    assert log.config_hash == "abc123def456"
    assert log.git_commit == "5d928f5a1b2c3d4e"
    assert log.exchange_server_time_offset_ms == 12.5
