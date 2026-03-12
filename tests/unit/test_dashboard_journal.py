"""
tests/unit/test_dashboard_journal.py
매매일지 탭 데이터 파이프라인 테스트 (S5)

Purpose:
- trades_*.jsonl 파일에서 DataFrame 로드
- 승률, 평균PnL, 최대손실 등 통계 계산
- hold_seconds=None 핸들링 (UI에서 '-' 표시)

TDD RED Phase: 구현 없이 실패하는 테스트만 작성
"""

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest


# ========== Fixtures ==========

SAMPLE_TRADE_1 = {
    "order_id": "abc123",
    "side": "Sell",
    "direction": "LONG",
    "qty_btc": 0.001,
    "entry_price": 70000.0,
    "exit_price": 71000.0,
    "realized_pnl_usd": 1.0,
    "fee_usd": 0.07,
    "entry_time": 1773285000.0,
    "exit_time": 1773285600.0,
    "hold_seconds": 600.0,
    "market_regime": "trending",
    "schema_version": "1.0",
}

SAMPLE_TRADE_2 = {
    "order_id": "def456",
    "side": "Buy",
    "direction": "SHORT",
    "qty_btc": 0.001,
    "entry_price": 70000.0,
    "exit_price": 69000.0,
    "realized_pnl_usd": 1.0,
    "fee_usd": 0.07,
    "entry_time": None,
    "exit_time": 1773285700.0,
    "hold_seconds": None,
    "market_regime": "ranging",
    "schema_version": "1.0",
}


@pytest.fixture
def trades_jsonl_path(tmp_path: Path) -> Path:
    """임시 trades JSONL 파일 생성"""
    jsonl_file = tmp_path / "trades_2026-03-12.jsonl"
    with open(jsonl_file, "w") as f:
        f.write(json.dumps(SAMPLE_TRADE_1) + "\n")
        f.write(json.dumps(SAMPLE_TRADE_2) + "\n")
    return jsonl_file


# ========== Tests ==========


class TestJournalDataPipeline:
    """매매일지 데이터 파이프라인 테스트"""

    def test_load_journal_returns_dataframe(self, trades_jsonl_path: Path):
        """trades_*.jsonl 파일에서 DataFrame 반환

        기대 컬럼: direction, realized_pnl_usd, hold_minutes (hold_seconds/60)
        """
        from src.application.dashboard_journal import load_journal_df

        # Act
        df = load_journal_df(trades_jsonl_path)

        # Assert: DataFrame 반환 + 필수 컬럼 존재
        assert isinstance(df, pd.DataFrame)
        assert "direction" in df.columns
        assert "realized_pnl_usd" in df.columns
        assert "hold_minutes" in df.columns  # hold_seconds / 60 변환
        assert len(df) == 2

    def test_journal_stats_calculation(self, trades_jsonl_path: Path):
        """승률, 평균PnL, 최대손실 계산

        SAMPLE_TRADE_1: PnL=$1 (WIN)
        SAMPLE_TRADE_2: PnL=$1 (WIN)
        → win_rate=1.0, avg_pnl=1.0, total_trades=2
        """
        from src.application.dashboard_journal import (
            load_journal_df,
            calculate_journal_stats,
        )

        # Arrange
        df = load_journal_df(trades_jsonl_path)

        # Act
        stats = calculate_journal_stats(df)

        # Assert: 통계 검증
        assert stats["win_rate"] == pytest.approx(1.0)
        assert stats["avg_pnl"] == pytest.approx(1.0)
        assert stats["total_trades"] == 2

    def test_null_hold_seconds_displayed_as_dash(self, trades_jsonl_path: Path):
        """hold_seconds=None이면 hold_minutes=None (UI에서 '-' 표시)

        SAMPLE_TRADE_2의 hold_seconds=None → hold_minutes도 NaN/None
        """
        from src.application.dashboard_journal import load_journal_df

        # Act
        df = load_journal_df(trades_jsonl_path)

        # Assert: hold_seconds=None인 행의 hold_minutes는 NaN
        row = df.loc[df["order_id"] == "def456"]
        assert len(row) == 1
        assert pd.isna(row["hold_minutes"].iloc[0])
