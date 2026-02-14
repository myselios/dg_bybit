"""
src/application/stop_manager.py
Stop Manager — Stop Loss 갱신 정책 (FLOW Section 2.5 + Oracle PF-2~PF-6)

SSOT:
- FLOW.md Section 2.5: Stop Update Policy
- Oracle Backlog PF-2~PF-6: Stop Update 시나리오

원칙:
1. Amend 우선 (공백 방지)
2. Debounce: 20% threshold + 2초 간격
3. stop_status 복구 (MISSING → PLACE intent)
4. entry_working=True → stop 갱신 금지

Exports:
- should_update_stop(): delta threshold + debounce 체크
- determine_stop_action(): stop_status + amend_fail_count 기반 action 결정
- recover_missing_stop(): stop_status=MISSING 복구
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple
from domain.state import StopStatus, Direction

logger = logging.getLogger(__name__)


def should_update_stop(
    position_qty: int,
    stop_qty: int,
    last_stop_update_at: float,
    current_time: float,
    threshold_pct: float = 0.20,
    debounce_seconds: float = 2.0,
    entry_working: bool = False,
) -> bool:
    """
    Stop 갱신 필요 여부 판단 (FLOW Section 2.5 + Oracle PF-2/PF-3)

    Args:
        position_qty: 현재 포지션 수량
        stop_qty: 현재 stop 수량
        last_stop_update_at: 마지막 stop 갱신 시각 (timestamp)
        current_time: 현재 시각 (timestamp)
        threshold_pct: Delta threshold (기본 20%)
        debounce_seconds: Debounce 간격 (기본 2초)
        entry_working: Entry order 활성 여부 (True면 stop 갱신 금지)

    Returns:
        True: stop 갱신 필요
        False: stop 갱신 불필요

    FLOW Section 2.5:
        - Delta >= 20% → stop 갱신 필요
        - Delta < 20% → stop 유지
        - Debounce: 최소 2초 간격
        - entry_working=True → stop 갱신 금지
    """
    # (1) entry_working=True → 갱신 차단
    if entry_working:
        return False

    # (2) Delta 계산
    if stop_qty == 0:
        # stop_qty=0이면 갱신 필요 (초기 상태)
        return True

    delta = abs(position_qty - stop_qty)
    delta_pct = delta / stop_qty if stop_qty > 0 else 0.0

    # (3) Delta threshold 체크
    if delta_pct < threshold_pct:
        # Delta < 20% → 갱신 불필요
        return False

    # (4) Debounce 체크
    time_since_last_update = current_time - last_stop_update_at
    if time_since_last_update < debounce_seconds:
        # Debounce 2초 이내 → 차단
        return False

    # (5) Delta >= 20% + Debounce 통과 → 갱신 필요
    return True


def determine_stop_action(
    stop_status: StopStatus,
    amend_fail_count: int,
) -> str:
    """
    Stop 갱신 action 결정 (FLOW Section 2.5 + Oracle PF-3/PF-5/PF-6)

    Args:
        stop_status: stop_status (ACTIVE/PENDING/MISSING/ERROR)
        amend_fail_count: Amend 실패 횟수

    Returns:
        "AMEND": Amend 우선
        "CANCEL_AND_PLACE": Amend 재시도 한계 or stop_status=MISSING
        "PLACE": stop_status=MISSING (복구)

    FLOW Section 2.5:
        - stop_status=ACTIVE, amend_fail_count=0 → AMEND 우선
        - amend_fail_count=1 → AMEND 재시도
        - amend_fail_count=2 → CANCEL_AND_PLACE (재시도 한계)
        - stop_status=MISSING → PLACE (복구)
    """
    # (1) stop_status=MISSING → PLACE (복구)
    if stop_status == StopStatus.MISSING:
        return "PLACE"

    # (2) stop_status=ERROR → CANCEL_AND_PLACE (복구 실패)
    if stop_status == StopStatus.ERROR:
        return "CANCEL_AND_PLACE"

    # (3) amend_fail_count >= 2 → CANCEL_AND_PLACE (재시도 한계)
    if amend_fail_count >= 2:
        return "CANCEL_AND_PLACE"

    # (4) stop_status=ACTIVE, amend_fail_count < 2 → AMEND 우선
    return "AMEND"


def recover_missing_stop(
    stop_status: StopStatus,
    position_qty: int,
) -> Tuple[bool, str]:
    """
    stop_status=MISSING 복구 (SSOT: Phase 0.5)

    Args:
        stop_status: stop_status
        position_qty: 포지션 수량

    Returns:
        (recovery_needed, action)
        - recovery_needed: True (복구 필요)
        - action: "PLACE" (stop 설치)

    Phase 0.5:
        - stop_status=MISSING → PlaceStop intent
    """
    if stop_status == StopStatus.MISSING and position_qty > 0:
        return True, "PLACE"

    return False, "NONE"


SL_MULTIPLIER = 0.7


@dataclass
class StopUpdateResult:
    """execute_stop_update의 결과"""

    success: bool = False
    new_stop_price: Optional[float] = None
    stop_already_breached: bool = False
    error: Optional[str] = None


def calculate_stop_price(
    entry_price: float,
    direction: Direction,
    atr: Optional[float],
) -> float:
    """ATR 기반 stop price 계산 (R:R >= 2:1)"""
    if atr and atr > 0:
        stop_distance_usd = atr * SL_MULTIPLIER
        min_stop = entry_price * 0.005
        max_stop = entry_price * 0.02
        stop_distance_usd = max(min_stop, min(stop_distance_usd, max_stop))
    else:
        stop_distance_usd = entry_price * 0.01  # Fallback 1%

    if direction == Direction.LONG:
        return entry_price - stop_distance_usd
    else:
        return entry_price + stop_distance_usd


def is_stop_breached(
    current_price: float,
    stop_price: float,
    direction: Direction,
) -> bool:
    """SL이 이미 관통되었는지 확인"""
    if not current_price or current_price <= 0:
        return False
    if direction == Direction.LONG and current_price <= stop_price:
        return True
    if direction == Direction.SHORT and current_price >= stop_price:
        return True
    return False


def execute_stop_update(
    rest_client,
    entry_price: float,
    direction: Direction,
    current_price: float,
    atr: Optional[float],
) -> StopUpdateResult:
    """
    Stop Loss를 계산하고 거래소에 설정한다.

    Args:
        rest_client: Bybit REST client
        entry_price: 진입 가격
        direction: 포지션 방향
        current_price: 현재 mark price
        atr: ATR 값

    Returns:
        StopUpdateResult
    """
    new_stop_price = calculate_stop_price(entry_price, direction, atr)

    # SL 이미 관통 체크
    if is_stop_breached(current_price, new_stop_price, direction):
        logger.warning(
            f"Stop already breached: SL=${new_stop_price:,.2f}, mark=${current_price:,.2f}"
        )
        return StopUpdateResult(
            success=True,
            new_stop_price=new_stop_price,
            stop_already_breached=True,
        )

    # Bybit V5 trading-stop API 호출
    result = rest_client.set_trading_stop(
        symbol="BTCUSDT",
        stop_loss=str(round(new_stop_price, 2)),
    )

    ret_code = result.get("retCode", -1)
    # 34040 = "not modified" → SL already set to same price → treat as success
    if ret_code not in (0, 34040):
        raise ValueError(
            f"set_trading_stop failed: retCode={ret_code}, msg={result.get('retMsg')}"
        )

    logger.info(f"Stop Loss set: ${new_stop_price:,.2f}")
    return StopUpdateResult(success=True, new_stop_price=new_stop_price)
