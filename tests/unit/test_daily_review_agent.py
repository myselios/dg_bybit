"""
tests/unit/test_daily_review_agent.py

S9: DailyReviewAgent TDD RED 테스트
모든 테스트는 아직 구현체가 없으므로 ImportError로 실패해야 한다.
"""

import pytest
from application.agents.daily_review_agent import DailyReport, DailyReviewAgent


# ── 헬퍼 ──────────────────────────────────────────────

def _make_trade(pnl_usd: float, direction: str = "LONG") -> dict:
    """테스트용 trade_log_entry 픽스처"""
    return {
        "entry_price": 70000.0,
        "exit_price": 70000.0 + pnl_usd / 0.001,
        "pnl_usd": pnl_usd,
        "direction": direction,
        "ma_slope_pct": 0.05,
        "hold_seconds": 300.0,
    }


# ── 1) 기본 반환 타입 ────────────────────────────────

def test_run_with_trades_returns_daily_report():
    # Arrange
    agent = DailyReviewAgent()
    trades = [_make_trade(5.0), _make_trade(-2.0)]

    # Act
    result = agent.run(trades, report_date="2026-03-18")

    # Assert
    assert isinstance(result, DailyReport)
    assert result.report_date == "2026-03-18"
    assert result.trade_count == 2


# ── 2) win_rate 계산 ─────────────────────────────────

def test_run_calculates_win_rate():
    # Arrange — 2승 1패
    agent = DailyReviewAgent()
    trades = [_make_trade(5.0), _make_trade(3.0), _make_trade(-1.0)]

    # Act
    result = agent.run(trades, report_date="2026-03-18")

    # Assert — 2/3 ≈ 0.667
    assert result.win_rate == pytest.approx(2 / 3, abs=0.01)


# ── 3) total_pnl 합계 ───────────────────────────────

def test_run_calculates_total_pnl():
    # Arrange
    agent = DailyReviewAgent()
    trades = [_make_trade(5.0), _make_trade(-2.0), _make_trade(1.5)]

    # Act
    result = agent.run(trades, report_date="2026-03-18")

    # Assert
    assert result.total_pnl_usd == pytest.approx(4.5, abs=0.01)


# ── 4) 빈 trades → 빈 리포트 ────────────────────────

def test_run_with_no_trades_returns_empty_report():
    # Arrange
    agent = DailyReviewAgent()

    # Act
    result = agent.run(trades=[], report_date="2026-03-18")

    # Assert
    assert result.trade_count == 0
    assert result.total_pnl_usd == 0.0
    assert result.win_rate == 0.0
    assert any("거래 없음" in s for s in result.suggestions)


# ── 5) suggestions 리스트 비어있지 않음 ──────────────

def test_run_generates_suggestions_list():
    # Arrange
    agent = DailyReviewAgent()
    trades = [_make_trade(5.0), _make_trade(-2.0)]

    # Act
    result = agent.run(trades, report_date="2026-03-18")

    # Assert
    assert isinstance(result.suggestions, list)
    assert len(result.suggestions) >= 1


# ── 6) DailyReport frozen (불변) ─────────────────────

def test_daily_report_immutable():
    # Arrange
    report = DailyReport(
        report_date="2026-03-18",
        trade_count=3,
        win_rate=0.667,
        total_pnl_usd=4.5,
        suggestions=["개선1"],
    )

    # Act & Assert — frozen dataclass 변경 시도 시 에러
    with pytest.raises(AttributeError):
        report.trade_count = 99

    assert report.trade_count == 3
