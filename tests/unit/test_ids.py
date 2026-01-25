"""
tests/unit/test_ids.py
Unit tests for ID generation and validation (FLOW Section 8, orderLinkId 규격)

Purpose:
- signal_id 생성 (deterministic, SHA1 축약, 36자 제한)
- orderLinkId 검증 (길이 ≤ 36, 영숫자+'-_')
- 충돌 방지 (동일 입력 → 동일 ID, 다른 입력 → 다른 ID)

SSOT:
- FLOW.md Section 8: Idempotency Key 생성 규칙
- Policy.md: (해당 없음, 구조적 규칙)

Test Coverage:
1. signal_id 결정론적 생성
2. signal_id 길이 제한 (≤ 36)
3. orderLinkId 검증 (유효한 케이스)
4. orderLinkId 검증 (길이 초과)
5. orderLinkId 검증 (잘못된 문자)
6. SHA1 해시 충돌 방지 (다른 입력 → 다른 ID)
"""

import re
from domain.ids import generate_signal_id, validate_order_link_id


def test_generate_signal_id_deterministic():
    """
    동일한 입력은 동일한 signal_id를 생성한다.

    FLOW Section 8: signal_id = {strategy}_{hash_suffix}_{side}
    - hash_suffix: SHA1 해시 앞 10자
    - 동일 입력 → 동일 해시 → 동일 ID (idempotency 보장)
    """
    strategy = "grid"
    bar_close_ts = 1705593600
    side = "long"

    # 동일 입력으로 2번 생성
    id1 = generate_signal_id(strategy, bar_close_ts, side)
    id2 = generate_signal_id(strategy, bar_close_ts, side)

    assert id1 == id2, "동일 입력은 동일 signal_id를 생성해야 함"

    # 형식 검증: {strategy_prefix}_{hash_10char}_{side_1char}
    # 예: "grid_a3f8d2e1c4_l"
    pattern = r'^[a-zA-Z0-9_-]{3,16}_[a-f0-9]{10}_[ls]$'
    assert re.match(pattern, id1), f"signal_id 형식 불일치: {id1}"


def test_generate_signal_id_length_under_36():
    """
    생성된 signal_id는 36자 이하여야 한다.

    FLOW Section 8: orderLinkId 최대 36자 제약
    - signal_id는 orderLinkId의 기반이므로 여유 확보
    - 예상 길이: 4(strategy) + 1(_) + 10(hash) + 1(_) + 1(side) = 17자
    """
    # 긴 strategy 이름
    strategy = "grid_detailed_strategy_with_long_name"
    bar_close_ts = 1705593600
    side = "long"

    signal_id = generate_signal_id(strategy, bar_close_ts, side)

    assert len(signal_id) <= 36, f"signal_id 길이 초과: {len(signal_id)} > 36"

    # orderLinkId = signal_id + "_" + direction (예: "_Buy")
    # 최대 길이 = len(signal_id) + 1 + 4 = len(signal_id) + 5
    # signal_id ≤ 31이면 안전
    assert len(signal_id) <= 31, f"signal_id + direction 조합 시 36자 초과 가능: {len(signal_id)}"


def test_validate_order_link_id_valid():
    """
    유효한 orderLinkId는 검증을 통과한다.

    FLOW Section 8: 영숫자 + '-_', 길이 ≤ 36
    """
    # 유효한 케이스들
    valid_ids = [
        "grid_a3f8d2e1c4_l_Buy",
        "signal-123_Sell",
        "test_order_id",
        "a" * 36,  # 최대 길이
        "a",  # 최소 길이
    ]

    for order_link_id in valid_ids:
        result = validate_order_link_id(order_link_id)
        assert result is True, f"유효한 ID가 검증 실패: {order_link_id}"


def test_validate_order_link_id_too_long():
    """
    길이가 36자를 초과하면 검증 실패한다.

    FLOW Section 8: Bybit orderLinkId 최대 36자 제약
    """
    # 37자
    too_long = "a" * 37

    result = validate_order_link_id(too_long)

    assert result is False, "36자 초과 ID가 검증을 통과함"


def test_validate_order_link_id_invalid_chars():
    """
    잘못된 문자가 포함되면 검증 실패한다.

    FLOW Section 8: [a-zA-Z0-9_-]만 허용
    - 공백, 유니코드, 특수문자 금지
    """
    # 잘못된 케이스들
    invalid_ids = [
        "signal 123",  # 공백
        "signal@buy",  # @
        "signal#123",  # #
        "신호_123",     # 유니코드
        "signal.buy",  # .
        "signal/buy",  # /
    ]

    for order_link_id in invalid_ids:
        result = validate_order_link_id(order_link_id)
        assert result is False, f"잘못된 ID가 검증을 통과함: {order_link_id}"


def test_sha1_hash_collision_resistance():
    """
    다른 입력은 다른 signal_id를 생성한다.

    FLOW Section 8: SHA1 해시로 충돌 방지
    - 동일 strategy/side, 다른 bar_close_ts → 다른 ID
    - 동일 strategy/bar_close_ts, 다른 side → 다른 ID
    """
    strategy = "grid"
    bar_close_ts_1 = 1705593600
    bar_close_ts_2 = 1705593601  # 1초 차이
    side_long = "long"
    side_short = "short"

    # Case 1: 다른 bar_close_ts
    id1 = generate_signal_id(strategy, bar_close_ts_1, side_long)
    id2 = generate_signal_id(strategy, bar_close_ts_2, side_long)

    assert id1 != id2, "다른 bar_close_ts는 다른 signal_id를 생성해야 함"

    # Case 2: 다른 side
    id3 = generate_signal_id(strategy, bar_close_ts_1, side_long)
    id4 = generate_signal_id(strategy, bar_close_ts_1, side_short)

    assert id3 != id4, "다른 side는 다른 signal_id를 생성해야 함"

    # Case 3: 모두 다름
    assert len({id1, id2, id3, id4}) == 3, "중복 ID 발생 (id3 == id1)"
    # id1 == id3 (동일 입력), 총 3개 고유 ID 예상
