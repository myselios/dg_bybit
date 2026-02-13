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
