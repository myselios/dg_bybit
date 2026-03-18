"""
src/application/agents/daily_review_agent.py
자동 일일 트레이드 분석 리포트 생성 에이전트
"""
from dataclasses import dataclass
from typing import List, Optional
from datetime import date


@dataclass(frozen=True)
class DailyReport:
    report_date: str        # "YYYY-MM-DD"
    trade_count: int
    win_rate: float         # 0.0~1.0
    total_pnl_usd: float
    suggestions: List[str]  # 개선 제안 (1개 이상)


class DailyReviewAgent:
    def run(self, trades: List[dict], report_date: Optional[str] = None) -> DailyReport:
        """
        trades: List of trade_log_entry dicts with pnl_usd field
        report_date: "YYYY-MM-DD" (None → today)
        """
        if report_date is None:
            report_date = date.today().isoformat()

        if not trades:
            return DailyReport(
                report_date=report_date,
                trade_count=0,
                win_rate=0.0,
                total_pnl_usd=0.0,
                suggestions=["거래 없음 — 파라미터 임계값이 너무 높을 수 있습니다."]
            )

        wins = [t for t in trades if t.get("pnl_usd", 0) > 0]
        total_pnl = sum(t.get("pnl_usd", 0) for t in trades)
        win_rate = len(wins) / len(trades)

        suggestions = _generate_suggestions(trades, win_rate, total_pnl)

        return DailyReport(
            report_date=report_date,
            trade_count=len(trades),
            win_rate=round(win_rate, 3),
            total_pnl_usd=round(total_pnl, 2),
            suggestions=suggestions
        )


def _generate_suggestions(trades: list, win_rate: float, total_pnl: float) -> List[str]:
    suggestions = []
    if win_rate < 0.4:
        suggestions.append("승률이 40% 미만입니다. T_TREND 임계값 상향을 고려하세요.")
    if win_rate >= 0.6:
        suggestions.append("승률 양호. 현재 파라미터 유지를 권장합니다.")
    if total_pnl < 0:
        suggestions.append("당일 누적 손실. 포지션 사이즈 축소를 고려하세요.")
    if not suggestions:
        suggestions.append("성과 정상 범위. 데이터 축적 후 재평가하세요.")
    return suggestions
