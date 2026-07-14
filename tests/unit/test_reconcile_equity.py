"""
test_reconcile_equity.py

scripts/reconcile_equity.py 순수 로직 단위 테스트.

스크립트 모듈은 src 패키지가 아니므로 importlib로 파일 경로에서 로드한다
(sys.path.insert 금지 규칙 준수).
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "reconcile_equity.py"
_spec = importlib.util.spec_from_file_location("reconcile_equity", _SCRIPT_PATH)
reconcile_equity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reconcile_equity)

is_valid_record = reconcile_equity.is_valid_record
reconcile = reconcile_equity.reconcile


# ============================================================================
# is_valid_record
# ============================================================================

def test_is_valid_record_accepts_normal():
    assert is_valid_record({"config_hash": "9fb499eab289", "realized_pnl_usd": 0.5}) is True


def test_is_valid_record_rejects_test_config_hash():
    assert is_valid_record({"config_hash": "test_config_hash", "realized_pnl_usd": 0.5}) is False


def test_is_valid_record_rejects_missing_pnl():
    assert is_valid_record({"config_hash": "9fb499eab289"}) is False


# ============================================================================
# reconcile
# ============================================================================

def test_reconcile_basic_equity_is_gross_minus_fees():
    """equity = starting + gross - fees (realized_pnl_usd는 gross)."""
    records = [
        ("2026-03-01", {"config_hash": "h", "realized_pnl_usd": 1.0, "fee_usd": 0.1}),
        ("2026-03-02", {"config_hash": "h", "realized_pnl_usd": -0.5, "fee_usd": 0.2}),
    ]
    result = reconcile(records, starting_capital=100.0)
    assert result.valid_trades == 2
    assert result.gross_pnl == pytest.approx(0.5)
    assert result.total_fees == pytest.approx(0.3)
    assert result.net_pnl == pytest.approx(0.2)
    assert result.equity == pytest.approx(100.2)


def test_reconcile_win_loss_by_gross_pnl():
    """승/패는 gross realized_pnl_usd > 0 기준."""
    records = [
        ("2026-03-01", {"config_hash": "h", "realized_pnl_usd": 1.0, "fee_usd": 0.0}),
        ("2026-03-02", {"config_hash": "h", "realized_pnl_usd": -1.0, "fee_usd": 0.0}),
        ("2026-03-03", {"config_hash": "h", "realized_pnl_usd": 0.0, "fee_usd": 0.0}),
    ]
    result = reconcile(records)
    assert result.win_count == 1
    assert result.loss_count == 2  # 0.0은 승리 아님


def test_reconcile_excludes_test_and_missing_records():
    records = [
        ("2026-03-01", {"config_hash": "h", "realized_pnl_usd": 2.0, "fee_usd": 0.0}),
        ("2026-03-01", {"config_hash": "test_config_hash", "realized_pnl_usd": 999.0}),
        ("2026-03-01", {"config_hash": "h"}),  # pnl 없음
    ]
    result = reconcile(records)
    assert result.total_records == 3
    assert result.valid_trades == 1
    assert result.gross_pnl == pytest.approx(2.0)


def test_reconcile_handles_none_fee():
    records = [
        ("2026-03-01", {"config_hash": "h", "realized_pnl_usd": 1.0, "fee_usd": None}),
    ]
    result = reconcile(records)
    assert result.total_fees == pytest.approx(0.0)
    assert result.equity == pytest.approx(101.0)


def test_reconcile_monthly_breakdown():
    records = [
        ("2026-03-01", {"config_hash": "h", "realized_pnl_usd": 1.0, "fee_usd": 0.1}),
        ("2026-03-15", {"config_hash": "h", "realized_pnl_usd": -0.5, "fee_usd": 0.1}),
        ("2026-04-02", {"config_hash": "h", "realized_pnl_usd": 2.0, "fee_usd": 0.2}),
    ]
    result = reconcile(records)
    assert set(result.monthly.keys()) == {"2026-03", "2026-04"}
    march = result.monthly["2026-03"]
    assert march.trades == 2
    assert march.wins == 1
    assert march.losses == 1
    assert march.gross_pnl == pytest.approx(0.5)
    assert march.net_pnl == pytest.approx(0.3)
    april = result.monthly["2026-04"]
    assert april.trades == 1
    assert april.gross_pnl == pytest.approx(2.0)


def test_reconcile_empty():
    result = reconcile([], starting_capital=100.0)
    assert result.valid_trades == 0
    assert result.equity == pytest.approx(100.0)
    assert result.monthly == {}
