"""
tests/unit/test_wave5_streamb.py

Wave 5 Stream B: R:R 개선 테스트
- 수수료 Maker 보장 (Post-Only)
- Trailing stop 활성화 임계값 (ATR*0.8 이상에서만 trailing 시작)
- Grid spacing 확대 (ATR*0.3)

TDD: RED → GREEN 순서로 작성
"""

import pytest
from application.orchestrator import _compute_adaptive_trail_distance
from domain.state import Direction


# ============================================================
# 1. Trailing stop 활성화 임계값 테스트
# ============================================================


def test_trail_not_active_below_08_atr_long():
    """수익 < ATR*0.8 이면 trail_distance가 매우 커서 trailing 비활성화 (LONG)."""
    trail_atr = 500.0  # ATR = $500
    entry_price = 80000.0
    # 수익 = $300 (< ATR*0.8 = $400)
    trail_price = 80300.0

    trail_distance = _compute_adaptive_trail_distance(
        trail_atr=trail_atr,
        entry_price=entry_price,
        trail_price=trail_price,
        direction=Direction.LONG,
    )

    # 수익(300) < 활성화 임계값(400): trail_distance는 trail_price보다 커야 함
    # 실질적으로 trailing이 발동하지 않는 큰 값이어야 함
    assert trail_distance > trail_price, (
        f"수익 $300 < ATR*0.8=$400: trail_distance({trail_distance:.2f}) > trail_price({trail_price:.2f}) 이어야 함"
    )


def test_trail_not_active_below_08_atr_short():
    """수익 < ATR*0.8 이면 trail_distance가 매우 커서 trailing 비활성화 (SHORT)."""
    trail_atr = 500.0
    entry_price = 80000.0
    # SHORT 수익 = $300 (< ATR*0.8 = $400)
    trail_price = 79700.0  # 가격이 내려와야 SHORT 수익

    trail_distance = _compute_adaptive_trail_distance(
        trail_atr=trail_atr,
        entry_price=entry_price,
        trail_price=trail_price,
        direction=Direction.SHORT,
    )

    # 수익(300) < 활성화 임계값(400): trail_distance가 trail_price보다 커야 trailing 미발동
    assert trail_distance > trail_price, (
        f"수익 $300 < ATR*0.8=$400: trail_distance({trail_distance:.2f}) > trail_price({trail_price:.2f}) 이어야 함"
    )


def test_trail_activates_at_08_atr_long():
    """수익 >= ATR*0.8 이면 trailing 활성화 (LONG) — trail_distance가 합리적인 값."""
    trail_atr = 500.0
    entry_price = 80000.0
    # 수익 = $400 (= ATR*0.8)
    trail_price = 80400.0

    trail_distance = _compute_adaptive_trail_distance(
        trail_atr=trail_atr,
        entry_price=entry_price,
        trail_price=trail_price,
        direction=Direction.LONG,
    )

    # 활성화됨: trail_distance는 ATR*0.5 이하여야 함
    assert trail_distance <= trail_atr * 0.5, (
        f"수익 $400 = ATR*0.8=$400: trail_distance({trail_distance:.2f}) <= ATR*0.5={trail_atr*0.5:.2f} 이어야 함"
    )


def test_trail_activates_above_08_atr_long():
    """수익 > ATR*0.8 이면 trailing 활성화 (LONG) — 수익 수준별 trail 거리 확인."""
    trail_atr = 500.0
    entry_price = 80000.0
    # 수익 = $600 (= ATR*1.2 > ATR*0.8)
    trail_price = 80600.0

    trail_distance = _compute_adaptive_trail_distance(
        trail_atr=trail_atr,
        entry_price=entry_price,
        trail_price=trail_price,
        direction=Direction.LONG,
    )

    # 수익 >= ATR*0.8: trailing 활성화, trail_distance는 trail_price보다 훨씬 작아야 함
    assert trail_distance < trail_price / 2, (
        f"수익 $600: trail_distance({trail_distance:.2f})는 합리적 범위여야 함"
    )


def test_trail_distance_tier_at_1x_atr():
    """수익 >= ATR*1.0 → trail_distance = ATR*0.3."""
    trail_atr = 500.0
    entry_price = 80000.0
    trail_price = 80500.0  # 수익 = $500 = ATR*1.0

    trail_distance = _compute_adaptive_trail_distance(
        trail_atr=trail_atr,
        entry_price=entry_price,
        trail_price=trail_price,
        direction=Direction.LONG,
    )

    assert trail_distance == pytest.approx(trail_atr * 0.3)


def test_trail_distance_tier_at_2x_atr():
    """수익 >= ATR*2.0 → trail_distance = ATR*0.2."""
    trail_atr = 500.0
    entry_price = 80000.0
    trail_price = 81000.0  # 수익 = $1000 = ATR*2.0

    trail_distance = _compute_adaptive_trail_distance(
        trail_atr=trail_atr,
        entry_price=entry_price,
        trail_price=trail_price,
        direction=Direction.LONG,
    )

    assert trail_distance == pytest.approx(trail_atr * 0.2)


def test_trail_distance_base_tier_between_08_and_1x():
    """수익 >= ATR*0.8 but < ATR*1.0 → trail_distance = ATR*0.5."""
    trail_atr = 500.0
    entry_price = 80000.0
    trail_price = 80420.0  # 수익 = $420 (ATR*0.84, >= 0.8x but < 1x)

    trail_distance = _compute_adaptive_trail_distance(
        trail_atr=trail_atr,
        entry_price=entry_price,
        trail_price=trail_price,
        direction=Direction.LONG,
    )

    assert trail_distance == pytest.approx(trail_atr * 0.5)


# ============================================================
# 2. Grid spacing 확대 (ATR*0.3) 테스트
# ============================================================


def test_grid_spacing_multiplier_03():
    """calculate_grid_spacing(atr=500, multiplier=0.3) == 150."""
    from application.signal_generator import calculate_grid_spacing

    result = calculate_grid_spacing(atr=500.0, multiplier=0.3)
    assert result == pytest.approx(150.0)


def test_orchestrator_uses_03_multiplier():
    """Orchestrator가 grid_spacing 계산 시 0.3 multiplier를 사용한다."""
    # orchestrator.py에서 calculate_grid_spacing(atr=atr, multiplier=0.3) 호출 확인
    import inspect
    from application import orchestrator

    source = inspect.getsource(orchestrator)
    assert "multiplier=0.3" in source, (
        "orchestrator.py는 grid_spacing multiplier=0.3을 사용해야 함 (0.2 아님)"
    )


# ============================================================
# 3. Post-Only (수수료 Maker 보장) 테스트
# ============================================================


def test_rest_client_place_order_supports_post_only():
    """bybit_rest_client.place_order가 isPostOnly 파라미터를 지원한다."""
    import inspect
    from infrastructure.exchange.bybit_rest_client import BybitRestClient

    sig = inspect.signature(BybitRestClient.place_order)
    assert "is_post_only" in sig.parameters, (
        "place_order는 is_post_only 파라미터를 지원해야 함"
    )


def test_rest_client_post_only_adds_param():
    """is_post_only=True 시 payload에 isPostOnly=True 추가."""
    from unittest.mock import MagicMock, patch
    from infrastructure.exchange.bybit_rest_client import BybitRestClient

    client = BybitRestClient.__new__(BybitRestClient)
    client.max_retries = 1
    client._last_rate_limit_info = None

    captured_params = {}

    def mock_make_request(method, endpoint, params):
        captured_params.update(params)
        return {"retCode": 0, "result": {"orderId": "test123"}}

    client._make_request = mock_make_request

    client.place_order(
        symbol="BTCUSDT",
        side="Buy",
        qty="0.003",
        order_link_id="test_link_001",
        order_type="Limit",
        time_in_force="GoodTillCancel",
        price="80000.0",
        is_post_only=True,
    )

    assert captured_params.get("isPostOnly") is True, (
        f"is_post_only=True 시 payload에 isPostOnly=True가 있어야 함, got: {captured_params}"
    )


def test_rest_client_post_only_false_no_param():
    """is_post_only=False (기본값) 시 payload에 isPostOnly 없음."""
    from unittest.mock import MagicMock
    from infrastructure.exchange.bybit_rest_client import BybitRestClient

    client = BybitRestClient.__new__(BybitRestClient)
    client.max_retries = 1
    client._last_rate_limit_info = None

    captured_params = {}

    def mock_make_request(method, endpoint, params):
        captured_params.update(params)
        return {"retCode": 0, "result": {"orderId": "test123"}}

    client._make_request = mock_make_request

    client.place_order(
        symbol="BTCUSDT",
        side="Buy",
        qty="0.003",
        order_link_id="test_link_002",
        order_type="Limit",
        time_in_force="GoodTillCancel",
        price="80000.0",
        is_post_only=False,
    )

    assert "isPostOnly" not in captured_params, (
        f"is_post_only=False 시 payload에 isPostOnly가 없어야 함, got: {captured_params}"
    )


def test_orchestrator_entry_uses_post_only():
    """Orchestrator entry 주문 시 is_post_only=True 사용 확인."""
    import inspect
    from application import orchestrator

    source = inspect.getsource(orchestrator)
    assert "is_post_only=True" in source, (
        "orchestrator.py entry 주문은 is_post_only=True를 사용해야 함 (Maker 보장)"
    )
