"""
src/infrastructure/logging/metrics_logger.py
Metrics Logger — Winrate/Streak/Multiplier 변화 추적 (시간에 따른 성과)

SSOT:
- FLOW.md Section 9: Metrics Update는 Closed Trades만
- account_builder_policy.md Section 11: Performance Gates (Winrate + Streak)
- task_plan.md Phase 5: Observability (metrics 변화 로그)

원칙:
1. CLOSED 거래만 집계 (FLOW Section 9)
2. Winrate/Streak/Multiplier 변화 추적
3. Schema validation: 필수 필드 누락 시 MetricsLogValidationError

Exports:
- log_metrics_update(): Metrics 변화 로그 생성
- validate_metrics_schema(): Schema validation (필수 필드 검증)
- MetricsLogValidationError: 필수 필드 누락 예외
"""

from typing import Dict, Any


class MetricsLogValidationError(Exception):
    """Metrics log schema validation 실패"""

    pass


def log_metrics_update(
    timestamp: float,
    winrate: float,
    win_streak: int,
    loss_streak: int,
    size_multiplier: float,
    num_closed_trades: int,
) -> Dict[str, Any]:
    """
    Metrics 변화 로그 생성

    Args:
        timestamp: 업데이트 시각 (UNIX timestamp)
        winrate: Winrate (0.0 ~ 1.0, 최근 50 closed trades 기준)
        win_streak: 연승 수
        loss_streak: 연패 수
        size_multiplier: Size multiplier (0.25 ~ 1.0)
        num_closed_trades: CLOSED 거래 수 (N)

    Returns:
        log_entry: Metrics log (dict)

    task_plan.md Phase 5:
        - metrics_logger: winrate/streak/multiplier 변화

    FLOW Section 9:
        - Winrate/Streak는 CLOSED 거래만 집계

    account_builder_policy Section 11:
        - N < 10 / 10-30 / 30+ 구간별 gate
        - 3 consecutive losses → size_mult = max(size_mult * 0.5, 0.25)
        - 3 consecutive wins → size_mult = min(size_mult * 1.5, 1.0)
    """
    log_entry = {
        "timestamp": timestamp,
        "winrate": winrate,
        "win_streak": win_streak,
        "loss_streak": loss_streak,
        "size_multiplier": size_multiplier,
        "num_closed_trades": num_closed_trades,
    }

    # Schema validation
    validate_metrics_schema(log_entry)

    return log_entry


def validate_metrics_schema(log_entry: Dict[str, Any]) -> None:
    """
    Metrics log schema validation

    Args:
        log_entry: Metrics log entry (dict)

    Raises:
        MetricsLogValidationError: 필수 필드 누락

    task_plan.md Phase 5:
        - schema 테스트(필수 필드 누락 시 실패)

    Required fields:
        - timestamp (float)
        - winrate (float)
        - win_streak (int)
        - loss_streak (int)
        - size_multiplier (float)
        - num_closed_trades (int)
    """
    required_fields = [
        "timestamp",
        "winrate",
        "win_streak",
        "loss_streak",
        "size_multiplier",
        "num_closed_trades",
    ]

    for field in required_fields:
        if field not in log_entry:
            raise MetricsLogValidationError(f"Missing required field: {field}")
