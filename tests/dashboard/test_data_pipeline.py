"""
tests/dashboard/test_data_pipeline.py

Phase 14a (Dashboard): Data Pipeline 테스트

TDD RED Phase: 테스트 먼저 작성 (구현은 아직 없음)
"""

import pytest
from pathlib import Path
from typing import List
import pandas as pd
import json
import tempfile


# Test 1: JSONL 파일 로드
def test_load_jsonl_files():
    """
    logs/ 디렉토리에서 *.log 파일 목록 로드

    Given: logs/ 디렉토리에 .log 파일들이 존재
    When: load_log_files() 호출
    Then: .log 파일 경로 리스트 반환
    """
    from src.dashboard.data_pipeline import load_log_files

    # Arrange: 테스트 디렉토리 생성
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        (log_dir / "trades_2026-02-12.jsonl").touch()
        (log_dir / "trades_2026-02-13.jsonl").touch()
        (log_dir / "mainnet.log").touch()  # 일반 텍스트 로그 (제외 대상)
        (log_dir / "not_a_log.txt").touch()

        # Act
        log_files = load_log_files(log_dir)

        # Assert: trades_*.jsonl만 로드, 일반 .log와 .txt 제외
        assert len(log_files) == 2
        assert all(f.suffix == ".jsonl" for f in log_files)
        assert all(f.name.startswith("trades_") for f in log_files)


# Test 2: TradeLogV1 파싱
def test_parse_trade_log():
    """
    JSONL 파일을 TradeLogV1 객체 리스트로 파싱

    Given: 유효한 JSONL 파일 (TradeLogV1 스키마)
    When: parse_jsonl() 호출
    Then: TradeLogV1 객체 리스트 반환
    """
    from src.dashboard.data_pipeline import parse_jsonl
    from src.infrastructure.logging.trade_logger_v1 import TradeLogV1

    # Arrange: 테스트 JSONL 파일 생성
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        # 간소화된 TradeLogV1 데이터 (필수 필드만)
        log_data = {
            "order_id": "test_order_1",
            "fills": [{"price": 50000.0, "qty": 100, "fee": 0.1, "timestamp": "2026-02-01T12:00:00"}],
            "slippage_usd": 0.5,
            "latency_rest_ms": 10.0,
            "latency_ws_ms": 5.0,
            "latency_total_ms": 15.0,
            "funding_rate": 0.0001,
            "mark_price": 50000.0,
            "index_price": 50000.0,
            "orderbook_snapshot": {"bid": 49999.0, "ask": 50001.0, "spread": 2.0},
            "market_regime": "ranging",
            "side": "Sell", "direction": "LONG", "qty_btc": 0.001, "entry_price": 49500.0, "exit_price": 50000.0, "realized_pnl_usd": 0.5, "fee_usd": 0.03,
            "schema_version": "1.0",
            "config_hash": "abc123",
            "git_commit": "def456",
            "exchange_server_time_offset_ms": 100,
        }
        f.write(json.dumps(log_data) + "\n")
        log_file = Path(f.name)

    try:
        # Act
        logs = parse_jsonl(log_file)

        # Assert
        assert len(logs) == 1
        assert isinstance(logs[0], TradeLogV1)
        assert logs[0].order_id == "test_order_1"
        assert logs[0].slippage_usd == 0.5
        assert logs[0].market_regime == "ranging"
    finally:
        log_file.unlink()


# Test 3: DataFrame 변환
def test_to_dataframe():
    """
    TradeLogV1 리스트를 DataFrame으로 변환

    Given: TradeLogV1 객체 리스트
    When: to_dataframe() 호출
    Then: 필수 컬럼을 가진 DataFrame 반환
    """
    from src.dashboard.data_pipeline import to_dataframe
    from src.infrastructure.logging.trade_logger_v1 import TradeLogV1

    # Arrange
    logs = [
        TradeLogV1(
            order_id="order_1",
            fills=[{"price": 50000.0, "qty": 100, "fee": 0.1, "timestamp": "2026-02-01T12:00:00"}],
            slippage_usd=0.5,
            latency_rest_ms=10.0,
            latency_ws_ms=5.0,
            latency_total_ms=15.0,
            funding_rate=0.0001,
            mark_price=50000.0,
            index_price=50000.0,
            orderbook_snapshot={"bid": 49999.0, "ask": 50001.0, "spread": 2.0},
            market_regime="ranging",
            side="Sell", direction="LONG", qty_btc=0.001, entry_price=49500.0, exit_price=50000.0, realized_pnl_usd=0.5, fee_usd=0.03,
            schema_version="1.0",
            config_hash="abc123",
            git_commit="def456",
            exchange_server_time_offset_ms=100,
        ),
        TradeLogV1(
            order_id="order_2",
            fills=[{"price": 50100.0, "qty": 100, "fee": 0.1, "timestamp": "2026-02-01T12:05:00"}],
            slippage_usd=0.3,
            latency_rest_ms=8.0,
            latency_ws_ms=4.0,
            latency_total_ms=12.0,
            funding_rate=0.0002,
            mark_price=50100.0,
            index_price=50100.0,
            orderbook_snapshot={"bid": 50099.0, "ask": 50101.0, "spread": 2.0},
            market_regime="trending_up",
            side="Buy", direction="SHORT", qty_btc=0.001, entry_price=50200.0, exit_price=50100.0, realized_pnl_usd=0.1, fee_usd=0.03,
            schema_version="1.0",
            config_hash="abc123",
            git_commit="def456",
            exchange_server_time_offset_ms=100,
        ),
    ]

    # Act
    df = to_dataframe(logs)

    # Assert
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    # 필수 컬럼 검증
    required_columns = ["order_id", "slippage_usd", "latency_total_ms", "market_regime"]
    for col in required_columns:
        assert col in df.columns
    assert df.iloc[0]["order_id"] == "order_1"
    assert df.iloc[1]["order_id"] == "order_2"


# Test 4: 빈 파일 처리
def test_empty_log_handling():
    """
    빈 JSONL 파일 처리

    Given: 빈 .log 파일
    When: parse_jsonl() 호출
    Then: 빈 리스트 반환 (예외 발생 안 함)
    """
    from src.dashboard.data_pipeline import parse_jsonl

    # Arrange: 빈 파일 생성
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        log_file = Path(f.name)

    try:
        # Act
        logs = parse_jsonl(log_file)

        # Assert
        assert logs == []
    finally:
        log_file.unlink()


# Test 5: 잘못된 JSON 라인 스킵
def test_invalid_json_handling():
    """
    잘못된 JSON 라인을 스킵하고 유효한 라인만 파싱

    Given: 유효한 JSON + 잘못된 JSON이 섞인 파일
    When: parse_jsonl() 호출
    Then: 유효한 라인만 파싱, 에러 발생 안 함
    """
    from src.dashboard.data_pipeline import parse_jsonl
    from src.infrastructure.logging.trade_logger_v1 import TradeLogV1

    # Arrange: 혼합 파일 생성
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        # 유효한 JSON
        valid_log = {
            "order_id": "order_valid",
            "fills": [{"price": 50000.0, "qty": 100, "fee": 0.1, "timestamp": "2026-02-01T12:00:00"}],
            "slippage_usd": 0.5,
            "latency_rest_ms": 10.0,
            "latency_ws_ms": 5.0,
            "latency_total_ms": 15.0,
            "funding_rate": 0.0001,
            "mark_price": 50000.0,
            "index_price": 50000.0,
            "orderbook_snapshot": {"bid": 49999.0, "ask": 50001.0, "spread": 2.0},
            "market_regime": "ranging",
            "side": "Sell", "direction": "LONG", "qty_btc": 0.001, "entry_price": 49500.0, "exit_price": 50000.0, "realized_pnl_usd": 0.5, "fee_usd": 0.03,
            "schema_version": "1.0",
            "config_hash": "abc123",
            "git_commit": "def456",
            "exchange_server_time_offset_ms": 100,
        }
        f.write(json.dumps(valid_log) + "\n")
        # 잘못된 JSON
        f.write("{ invalid json line \n")
        # 또 다른 유효한 JSON
        valid_log2 = valid_log.copy()
        valid_log2["order_id"] = "order_valid_2"
        f.write(json.dumps(valid_log2) + "\n")
        log_file = Path(f.name)

    try:
        # Act
        logs = parse_jsonl(log_file)

        # Assert
        assert len(logs) == 2  # 유효한 2개만 파싱됨
        assert logs[0].order_id == "order_valid"
        assert logs[1].order_id == "order_valid_2"
    finally:
        log_file.unlink()


# ============================================================================
# Stream C: load_all_trades / get_summary_stats 테스트
# ============================================================================

def _make_trade_jsonl_line(**overrides) -> dict:
    """테스트용 JSONL 레코드 생성"""
    base = {
        "order_id": "test_order",
        "fills": [{"price": 50000.0, "qty": 0.001, "fee": 0.01,
                   "timestamp": "2026-03-01T10:00:00"}],
        "slippage_usd": 0.1,
        "latency_rest_ms": 10.0,
        "latency_ws_ms": 5.0,
        "latency_total_ms": 15.0,
        "funding_rate": 0.0001,
        "mark_price": 50000.0,
        "index_price": 50000.0,
        "orderbook_snapshot": {},
        "market_regime": "ranging",
        "side": "Sell",
        "direction": "LONG",
        "qty_btc": 0.001,
        "entry_price": 49000.0,
        "exit_price": 50000.0,
        "realized_pnl_usd": 1.0,
        "fee_usd": 0.02,
        "schema_version": "1.0",
        "config_hash": "abc",
        "git_commit": "def",
        "exchange_server_time_offset_ms": 0,
        "entry_time": None,
        "exit_time": 1_740_826_800.0,
        "hold_seconds": None,
    }
    base.update(overrides)
    return base


def test_load_all_trades_basic():
    """
    load_all_trades: 여러 trades_*.jsonl 파일 로드 → 통합 DataFrame 반환

    Given: 2개 trades_*.jsonl 파일 (각 2행)
    When: load_all_trades() 호출
    Then: 4행 DataFrame 반환, exit_time 컬럼 존재
    """
    from src.dashboard.data_pipeline import load_all_trades

    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        r1 = _make_trade_jsonl_line(order_id="o1", exit_time=1_740_826_800.0)
        r2 = _make_trade_jsonl_line(order_id="o2", exit_time=1_740_826_900.0)
        r3 = _make_trade_jsonl_line(order_id="o3", exit_time=1_740_913_200.0)
        r4 = _make_trade_jsonl_line(order_id="o4", exit_time=1_740_913_300.0)

        with open(log_dir / "trades_2026-03-01.jsonl", "w") as f:
            f.write(json.dumps(r1) + "\n")
            f.write(json.dumps(r2) + "\n")
        with open(log_dir / "trades_2026-03-02.jsonl", "w") as f:
            f.write(json.dumps(r3) + "\n")
            f.write(json.dumps(r4) + "\n")

        df = load_all_trades(str(log_dir))

        assert len(df) == 4
        assert "exit_time" in df.columns
        assert "entry_time" in df.columns
        assert "hold_seconds" in df.columns


def test_load_all_trades_null_entry_time():
    """
    entry_time null → NaN (crash 없음)
    """
    from src.dashboard.data_pipeline import load_all_trades

    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        r1 = _make_trade_jsonl_line(order_id="o1", entry_time=None)
        with open(log_dir / "trades_2026-03-01.jsonl", "w") as f:
            f.write(json.dumps(r1) + "\n")

        df = load_all_trades(str(log_dir))

        assert len(df) == 1
        import math
        assert math.isnan(df.iloc[0]["entry_time"])


def test_load_all_trades_empty_dir():
    """
    trades_*.jsonl 파일 없는 디렉토리 → 빈 DataFrame, crash 없음
    """
    from src.dashboard.data_pipeline import load_all_trades

    with tempfile.TemporaryDirectory() as tmpdir:
        df = load_all_trades(tmpdir)

        assert df.empty


def test_load_all_trades_nonexistent_dir():
    """
    존재하지 않는 디렉토리 → 빈 DataFrame 반환 (예외 아님)
    """
    from src.dashboard.data_pipeline import load_all_trades

    df = load_all_trades("/nonexistent/path/that/does/not/exist")

    assert df.empty


def test_get_summary_stats_basic():
    """
    get_summary_stats: 기본 통계 계산

    Given: realized_pnl_usd 컬럼이 있는 DataFrame
    When: get_summary_stats() 호출
    Then: total_trades, win_rate, total_pnl, avg_win, avg_loss, rr_ratio, max_drawdown 반환
    """
    from src.dashboard.data_pipeline import get_summary_stats

    df = pd.DataFrame([
        {"realized_pnl_usd": 10.0},
        {"realized_pnl_usd": -5.0},
        {"realized_pnl_usd": 8.0},
        {"realized_pnl_usd": -3.0},
    ])
    result = get_summary_stats(df)

    assert result["total_trades"] == 4
    assert result["win_rate"] == pytest.approx(0.5, rel=1e-6)
    assert result["total_pnl"] == pytest.approx(10.0, rel=1e-6)
    assert result["avg_win"] == pytest.approx(9.0, rel=1e-6)   # (10+8)/2
    assert result["avg_loss"] == pytest.approx(-4.0, rel=1e-6)  # (-5-3)/2
    assert result["rr_ratio"] == pytest.approx(9.0 / 4.0, rel=1e-6)


def test_get_summary_stats_empty():
    """빈 DataFrame → 모두 0 반환, crash 없음"""
    from src.dashboard.data_pipeline import get_summary_stats

    result = get_summary_stats(pd.DataFrame())

    assert result["total_trades"] == 0
    assert result["win_rate"] == 0.0
    assert result["total_pnl"] == 0.0
