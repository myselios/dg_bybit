"""
tests/unit/test_old_schema_compat.py

구 스키마(2026-02-12) 호환성 테스트

Feb 12 트레이드 레코드는 다음 필드가 없다:
  - side, direction, qty_btc, entry_price, exit_price
  - realized_pnl_usd, fee_usd, hold_seconds, signal_reason
  - entry_time, exit_time

load_all_trades() 와 get_summary_stats() 가 이 레코드를 크래시 없이 처리해야 한다.
"""

import json
import tempfile
from pathlib import Path

import pytest


# ========== Fixtures ==========

OLD_SCHEMA_TRADE = {
    "order_id": "6b7ac284-368b-49d8-baca-f83b2a651089",
    "fills": [{"price": 67890.8, "qty": 1, "fee": 0.0, "timestamp": 1770900037.506}],
    "slippage_usd": 0.0,
    "latency_rest_ms": 0.0,
    "latency_ws_ms": 0.0,
    "latency_total_ms": 0.0,
    "funding_rate": 0.0001,
    "mark_price": 67888.72,
    "index_price": 67916.88,
    "orderbook_snapshot": {},
    "market_regime": "trending_up",
    "schema_version": "1.0",
    "config_hash": "test_config_hash",
    "git_commit": "test_git_commit",
    "exchange_server_time_offset_ms": 0.0,
    # NOTE: side, direction, qty_btc, entry_price, exit_price,
    #       realized_pnl_usd, fee_usd, hold_seconds, signal_reason 없음
}

NEW_SCHEMA_TRADE = {
    "order_id": "new-trade-001",
    "fills": [{"price": 68000.0, "qty": 1, "fee": 0.18, "timestamp": 1773071005.9}],
    "slippage_usd": 0.05,
    "latency_rest_ms": 0.0,
    "latency_ws_ms": 1000.0,
    "latency_total_ms": 1000.0,
    "funding_rate": -0.00003,
    "mark_price": 68005.0,
    "index_price": 68010.0,
    "orderbook_snapshot": {},
    "market_regime": "high_vol",
    "schema_version": "1.0",
    "config_hash": "abc123",
    "git_commit": "def456",
    "exchange_server_time_offset_ms": 0.0,
    "side": "Sell",
    "direction": "LONG",
    "qty_btc": 0.005,
    "entry_price": 68500.0,
    "exit_price": 68000.0,
    "realized_pnl_usd": -2.5,
    "fee_usd": 0.18,
    "entry_time": 1773070000.0,
    "exit_time": 1773071005.9,
    "hold_seconds": 1005.9,
    "signal_reason": "trend_up_entry",
}


def write_jsonl(path: Path, records: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


# ========== Tests: load_all_trades() ==========

class TestLoadAllTradesOldSchema:
    """load_all_trades()가 구 스키마 트레이드를 크래시 없이 처리한다."""

    def test_load_old_schema_does_not_crash(self, tmp_path):
        """구 스키마 단독 파일 로드 시 예외 없이 DataFrame 반환."""
        from src.dashboard.data_pipeline import load_all_trades

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [OLD_SCHEMA_TRADE])

        df = load_all_trades(str(tmp_path))

        assert len(df) == 1

    def test_load_old_schema_market_regime_present(self, tmp_path):
        """구 스키마에 market_regime 값이 보존된다."""
        from src.dashboard.data_pipeline import load_all_trades

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [OLD_SCHEMA_TRADE])

        df = load_all_trades(str(tmp_path))

        assert "market_regime" in df.columns
        assert df.iloc[0]["market_regime"] == "trending_up"

    def test_load_old_schema_missing_market_regime_gets_default(self, tmp_path):
        """market_regime 누락 시 'unknown' 기본값이 들어간다."""
        from src.dashboard.data_pipeline import load_all_trades

        trade = {**OLD_SCHEMA_TRADE}
        del trade["market_regime"]

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [trade])

        df = load_all_trades(str(tmp_path))

        assert df.iloc[0]["market_regime"] == "unknown"

    def test_load_old_schema_fee_usd_defaults_to_zero(self, tmp_path):
        """fee_usd 누락 시 0.0 기본값이 들어간다."""
        from src.dashboard.data_pipeline import load_all_trades

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [OLD_SCHEMA_TRADE])

        df = load_all_trades(str(tmp_path))

        assert "fee_usd" in df.columns
        assert float(df.iloc[0]["fee_usd"]) == 0.0

    def test_load_old_schema_side_defaults_to_buy(self, tmp_path):
        """side 누락 시 'Buy' 기본값이 들어간다."""
        from src.dashboard.data_pipeline import load_all_trades

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [OLD_SCHEMA_TRADE])

        df = load_all_trades(str(tmp_path))

        assert "side" in df.columns
        assert df.iloc[0]["side"] == "Buy"

    def test_load_old_schema_signal_reason_defaults_to_empty(self, tmp_path):
        """signal_reason 누락 시 빈 문자열 기본값이 들어간다."""
        from src.dashboard.data_pipeline import load_all_trades

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [OLD_SCHEMA_TRADE])

        df = load_all_trades(str(tmp_path))

        assert "signal_reason" in df.columns
        assert df.iloc[0]["signal_reason"] == ""

    def test_load_old_schema_hold_seconds_is_nan(self, tmp_path):
        """hold_seconds 누락 시 NaN으로 처리된다."""
        import math
        from src.dashboard.data_pipeline import load_all_trades

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [OLD_SCHEMA_TRADE])

        df = load_all_trades(str(tmp_path))

        assert "hold_seconds" in df.columns
        assert math.isnan(df.iloc[0]["hold_seconds"])

    def test_load_old_schema_realized_pnl_usd_defaults_to_zero(self, tmp_path):
        """realized_pnl_usd 누락 시 0.0으로 채워진다."""
        from src.dashboard.data_pipeline import load_all_trades

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [OLD_SCHEMA_TRADE])

        df = load_all_trades(str(tmp_path))

        assert "realized_pnl_usd" in df.columns
        assert float(df.iloc[0]["realized_pnl_usd"]) == 0.0

    def test_load_mixed_old_and_new_schema(self, tmp_path):
        """구 스키마와 신 스키마가 혼재할 때 모두 로드된다."""
        from src.dashboard.data_pipeline import load_all_trades

        old_file = tmp_path / "trades_2026-02-12.jsonl"
        new_file = tmp_path / "trades_2026-03-18.jsonl"
        write_jsonl(old_file, [OLD_SCHEMA_TRADE] * 6)
        write_jsonl(new_file, [NEW_SCHEMA_TRADE])

        df = load_all_trades(str(tmp_path))

        assert len(df) == 7

    def test_load_old_schema_multiple_records(self, tmp_path):
        """구 스키마 레코드 6건을 모두 로드한다."""
        from src.dashboard.data_pipeline import load_all_trades

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        records = [
            {**OLD_SCHEMA_TRADE, "order_id": f"order-{i}"}
            for i in range(6)
        ]
        write_jsonl(trade_file, records)

        df = load_all_trades(str(tmp_path))

        assert len(df) == 6


# ========== Tests: get_summary_stats() ==========

class TestGetSummaryStatsOldSchema:
    """get_summary_stats()가 구 스키마에서 오는 NaN/0 값을 안전하게 처리한다."""

    def test_summary_stats_old_schema_does_not_crash(self, tmp_path):
        """구 스키마 트레이드로 get_summary_stats() 호출 시 예외 없이 반환."""
        from src.dashboard.data_pipeline import load_all_trades, get_summary_stats

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [OLD_SCHEMA_TRADE] * 6)

        df = load_all_trades(str(tmp_path))
        stats = get_summary_stats(df)

        assert isinstance(stats, dict)

    def test_summary_stats_old_schema_total_trades(self, tmp_path):
        """구 스키마 6건 로드 시 total_trades == 6."""
        from src.dashboard.data_pipeline import load_all_trades, get_summary_stats

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [OLD_SCHEMA_TRADE] * 6)

        df = load_all_trades(str(tmp_path))
        stats = get_summary_stats(df)

        assert stats["total_trades"] == 6

    def test_summary_stats_old_schema_zero_pnl(self, tmp_path):
        """realized_pnl_usd 없는 구 스키마 트레이드의 total_pnl == 0.0."""
        from src.dashboard.data_pipeline import load_all_trades, get_summary_stats

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [OLD_SCHEMA_TRADE] * 6)

        df = load_all_trades(str(tmp_path))
        stats = get_summary_stats(df)

        assert stats["total_pnl"] == 0.0

    def test_summary_stats_mixed_schema_uses_new_pnl(self, tmp_path):
        """신 스키마 트레이드의 realized_pnl_usd가 총 PnL에 반영된다."""
        from src.dashboard.data_pipeline import load_all_trades, get_summary_stats

        old_file = tmp_path / "trades_2026-02-12.jsonl"
        new_file = tmp_path / "trades_2026-03-18.jsonl"
        write_jsonl(old_file, [OLD_SCHEMA_TRADE] * 6)
        write_jsonl(new_file, [NEW_SCHEMA_TRADE])

        df = load_all_trades(str(tmp_path))
        stats = get_summary_stats(df)

        # NEW_SCHEMA_TRADE.realized_pnl_usd == -2.5
        assert stats["total_pnl"] == pytest.approx(-2.5, abs=1e-6)

    def test_summary_stats_win_rate_all_zero_pnl(self, tmp_path):
        """모든 트레이드 PnL == 0 이면 win_rate == 0.0."""
        from src.dashboard.data_pipeline import load_all_trades, get_summary_stats

        trade_file = tmp_path / "trades_2026-02-12.jsonl"
        write_jsonl(trade_file, [OLD_SCHEMA_TRADE] * 6)

        df = load_all_trades(str(tmp_path))
        stats = get_summary_stats(df)

        assert stats["win_rate"] == 0.0
