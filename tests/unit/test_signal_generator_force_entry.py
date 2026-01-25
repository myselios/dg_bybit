"""
tests/unit/test_signal_generator_force_entry.py

Phase 12a-4a: Force Entry 모드 테스트

Test cases:
1. force_entry=True → 즉시 Buy 신호 (Grid spacing 무시)
2. force_entry=True + last_fill_price=None → Buy 신호
3. force_entry=False → 정상 Grid 로직
"""

from application.signal_generator import generate_signal


def test_force_entry_ignores_grid_spacing():
    """
    force_entry=True일 때 Grid spacing 체크 무시, 즉시 Buy 신호 생성
    """
    current_price = 100_000.0
    last_fill_price = 99_000.0  # Grid spacing 범위 내
    grid_spacing = 2_000.0  # $2,000 spacing

    # 정상 Grid 로직: 범위 내 (99k~101k) → 신호 없음
    normal_signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        qty=10,
        force_entry=False,
    )
    assert normal_signal is None, "정상 Grid 로직: 범위 내 → 신호 없음"

    # Force Entry 모드: Grid spacing 무시 → 즉시 Buy 신호
    force_signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        qty=10,
        force_entry=True,
    )
    assert force_signal is not None, "Force Entry: 신호 생성됨"
    assert force_signal.side == "Buy", "Force Entry: Buy 신호"
    assert force_signal.price == current_price
    assert force_signal.qty == 10


def test_force_entry_works_when_flat():
    """
    force_entry=True + last_fill_price=None (FLAT 상태) → Buy 신호 생성
    """
    current_price = 100_000.0
    last_fill_price = None  # FLAT 상태
    grid_spacing = 2_000.0

    # 정상 Grid 로직: FLAT 상태 → 신호 없음
    normal_signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        qty=10,
        force_entry=False,
    )
    assert normal_signal is None, "정상 Grid 로직: FLAT → 신호 없음"

    # Force Entry 모드: FLAT 상태에서도 Buy 신호
    force_signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        qty=10,
        force_entry=True,
    )
    assert force_signal is not None, "Force Entry: FLAT에서도 신호 생성"
    assert force_signal.side == "Buy", "Force Entry: Buy 신호"
    assert force_signal.price == current_price
    assert force_signal.qty == 10


def test_force_entry_false_follows_normal_grid_logic():
    """
    force_entry=False → 정상 Grid 로직 (기존 동작 유지)
    """
    last_fill_price = 98_000.0
    grid_spacing = 2_000.0

    # Case 1: Grid 범위 내 (신호 없음)
    # Grid 범위: [96_000, 100_000]
    # current_price = 99_000 (범위 내)
    current_price_inside = 99_000.0
    signal_no_trigger = generate_signal(
        current_price=current_price_inside,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        qty=10,
        force_entry=False,
    )
    assert signal_no_trigger is None, "Grid 범위 내 → 신호 없음"

    # Case 2: Grid down 조건 충족 (Buy 신호)
    # current_price <= last_fill_price - grid_spacing
    # 96_000 <= 98_000 - 2_000 = 96_000 → Buy 신호
    current_price_low = 96_000.0
    signal_grid_down = generate_signal(
        current_price=current_price_low,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        qty=10,
        force_entry=False,
    )
    assert signal_grid_down is not None, "Grid down 조건 → Buy 신호"
    assert signal_grid_down.side == "Buy"

    # Case 3: Grid up 조건 충족 (Sell 신호)
    # current_price >= last_fill_price + grid_spacing
    # 100_000 >= 98_000 + 2_000 = 100_000 → Sell 신호
    current_price_high = 100_000.0
    signal_grid_up = generate_signal(
        current_price=current_price_high,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        qty=10,
        force_entry=False,
    )
    assert signal_grid_up is not None, "Grid up 조건 → Sell 신호"
    assert signal_grid_up.side == "Sell"
