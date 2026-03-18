"""
src/application/health_scorecard.py

S8: HealthScorecard — 봇 건강 상태 진단 모듈

등급 기준:
- A: signal_rate>=5/h AND win_rate>=0.5 AND consecutive_losses<3
- B: signal_rate>=2/h AND win_rate>=0.4 AND consecutive_losses<5
- C: signal_rate>0/h (진입은 하고 있음)
- D: signal_rate==0/h AND uptime>0 (살아있지만 진입 없음)
- F: 완전 비정상 (uptime==0)
"""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class HealthScore:
    grade: str              # "A", "B", "C", "D", "F"
    score: float            # 0.0~100.0
    signal_rate: float      # 신호/시간 비율
    win_rate: float         # 승률
    consecutive_losses: int
    alerts: List[str] = field(default_factory=list)  # CRITICAL 경고 목록


class HealthScorecard:
    """봇 건강 상태를 진단하여 HealthScore를 반환한다."""

    def score(
        self,
        signal_count_1h: int,
        win_rate: float,
        consecutive_losses: int,
        uptime_pct: float = 1.0,
    ) -> HealthScore:
        signal_rate = float(signal_count_1h)

        # F: 봇 다운
        if uptime_pct == 0.0:
            return HealthScore(
                grade="F",
                score=0.0,
                signal_rate=signal_rate,
                win_rate=win_rate,
                consecutive_losses=consecutive_losses,
                alerts=["CRITICAL: 봇 다운 (uptime=0%)"],
            )

        # D: 살아있지만 신호 없음
        if signal_count_1h == 0:
            return HealthScore(
                grade="D",
                score=10.0,
                signal_rate=0.0,
                win_rate=win_rate,
                consecutive_losses=consecutive_losses,
                alerts=["CRITICAL: 신호 발생률 0%"],
            )

        # A: 좋은 성과
        if (
            signal_count_1h >= 5
            and win_rate >= 0.5
            and consecutive_losses < 3
        ):
            computed_score = min(100.0, 80.0 + win_rate * 20.0)
            return HealthScore(
                grade="A",
                score=computed_score,
                signal_rate=signal_rate,
                win_rate=win_rate,
                consecutive_losses=consecutive_losses,
                alerts=[],
            )

        # B: 보통 성과
        if signal_count_1h >= 2 and win_rate >= 0.4 and consecutive_losses < 5:
            return HealthScore(
                grade="B",
                score=60.0,
                signal_rate=signal_rate,
                win_rate=win_rate,
                consecutive_losses=consecutive_losses,
                alerts=[],
            )

        # C: 진입은 하고 있음
        return HealthScore(
            grade="C",
            score=40.0,
            signal_rate=signal_rate,
            win_rate=win_rate,
            consecutive_losses=consecutive_losses,
            alerts=[],
        )
