"""
src/domain/ids.py
ID 생성 및 검증 (FLOW Section 8: Idempotency Key)

Purpose:
- signal_id 생성 (deterministic, SHA1 축약, 36자 제한 준수)
- orderLinkId 검증 (Bybit 제약 준수: 길이 ≤ 36, 영숫자+'-_')

SSOT:
- FLOW.md Section 8: Idempotency Key 생성 규칙
  - signal_id = {strategy[:4]}_{hash[:10]}_{side[:1]}
  - orderLinkId 검증: [a-zA-Z0-9_-], ≤ 36자

Design Decisions:
- SHA1 해시 사용 (충돌 방지, 결정론적)
- 길이 제한: signal_id ≤ 16자 (orderLinkId 여유 확보)
- entry_price 제외 (라운딩 변화로 인한 중복 주문 방지)
"""

import hashlib
import re


def generate_signal_id(strategy: str, bar_close_ts: int, side: str) -> str:
    """
    Signal ID 생성 (결정론적, 36자 제한 준수)

    Args:
        strategy: 전략명 (예: "grid", "grid_detailed_strategy")
        bar_close_ts: 바 종가 타임스탬프 (Unix timestamp)
        side: 방향 ("long" or "short")

    Returns:
        signal_id: {strategy_prefix}_{hash_suffix}_{side_prefix}
        - strategy_prefix: 전략명 앞 4자
        - hash_suffix: SHA1 해시 앞 10자 (충돌 방지)
        - side_prefix: side 앞 1자 (l/s)

    Example:
        >>> generate_signal_id("grid", 1705593600, "long")
        "grid_a3f8d2e1c4_l"  # 16자

    FLOW Section 8:
        - 동일 입력 → 동일 ID (idempotency 보장)
        - 다른 입력 → 다른 ID (충돌 방지)
        - signal_id + "_" + direction ≤ 36자 보장
    """
    # 원본 (충돌 방지를 위한 전체 데이터)
    raw = f"{strategy}_{bar_close_ts}_{side}"

    # SHA1 해시 축약 (앞 10자)
    hash_suffix = hashlib.sha1(raw.encode()).hexdigest()[:10]

    # 축약 ID 생성
    strategy_prefix = strategy[:4]
    side_prefix = side[:1]

    signal_id = f"{strategy_prefix}_{hash_suffix}_{side_prefix}"

    return signal_id


def validate_order_link_id(order_link_id: str) -> bool:
    """
    orderLinkId 검증 (Bybit 제약 준수)

    Args:
        order_link_id: 검증할 orderLinkId

    Returns:
        True: 유효한 ID
        False: 제약 위반

    Constraints (FLOW Section 8):
        - 길이 ≤ 36자
        - 영숫자 + '-_'만 허용 (정규식: [a-zA-Z0-9_-])
        - 공백, 유니코드, 특수문자 금지

    Example:
        >>> validate_order_link_id("grid_a3f8d2e1c4_l_Buy")
        True
        >>> validate_order_link_id("a" * 37)  # 37자
        False
        >>> validate_order_link_id("signal@buy")  # @ 포함
        False
    """
    # 길이 검증
    if len(order_link_id) > 36:
        return False

    # 문자 검증 (영숫자 + '-_')
    pattern = r'^[a-zA-Z0-9_-]+$'
    if not re.match(pattern, order_link_id):
        return False

    return True
