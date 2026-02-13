"""
tests/dashboard/test_export.py

Phase 14a (Dashboard) Phase 5: Export 기능 테스트

TDD RED Phase: Export 테스트 먼저 작성
"""

import pytest
import pandas as pd
from pathlib import Path
import tempfile
from datetime import date
from src.dashboard.export import (
    apply_date_filter,
    export_to_csv,
)


# Test 1: 날짜 필터 적용
def test_apply_date_filter():
    """
    날짜 범위 필터링

    Given: 거래 DataFrame (fills.timestamp 포함)
    When: apply_date_filter(start_date, end_date) 호출
    Then: 날짜 범위 내 거래만 반환
    """
    # Arrange: 테스트 데이터 (3개 거래, 다른 날짜)
    df = pd.DataFrame([
        {
            "order_id": "o1",
            "pnl": 10.0,
            "fills": [{"timestamp": "2026-02-01T10:00:00"}]
        },
        {
            "order_id": "o2",
            "pnl": -5.0,
            "fills": [{"timestamp": "2026-02-05T11:00:00"}]
        },
        {
            "order_id": "o3",
            "pnl": 15.0,
            "fills": [{"timestamp": "2026-02-10T12:00:00"}]
        },
    ])

    # Act: 2/3 ~ 2/9 필터
    filtered = apply_date_filter(
        df,
        start_date=date(2026, 2, 3),
        end_date=date(2026, 2, 9)
    )

    # Assert: o2만 남음
    assert len(filtered) == 1
    assert filtered.iloc[0]["order_id"] == "o2"


# Test 2: 날짜 필터 (전체 범위)
def test_apply_date_filter_all():
    """
    전체 범위 선택 시 모든 데이터 반환

    Given: 거래 DataFrame
    When: 전체 날짜 범위 선택
    Then: 모든 거래 반환
    """
    df = pd.DataFrame([
        {
            "order_id": "o1",
            "pnl": 10.0,
            "fills": [{"timestamp": "2026-02-01T10:00:00"}]
        },
        {
            "order_id": "o2",
            "pnl": -5.0,
            "fills": [{"timestamp": "2026-02-10T11:00:00"}]
        },
    ])

    # Act: 전체 범위
    filtered = apply_date_filter(
        df,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 10)
    )

    # Assert: 모든 거래 반환
    assert len(filtered) == 2


# Test 3: CSV Export
def test_export_to_csv():
    """
    CSV 파일 생성

    Given: 거래 DataFrame
    When: export_to_csv() 호출
    Then: CSV 파일 생성 (읽기 가능)
    """
    # Arrange: 테스트 데이터
    df = pd.DataFrame([
        {
            "order_id": "o1",
            "pnl": 10.0,
            "market_regime": "ranging",
        },
        {
            "order_id": "o2",
            "pnl": -5.0,
            "market_regime": "trending_up",
        },
    ])

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "export.csv"

        # Act: CSV 생성
        export_to_csv(df, str(output_path))

        # Assert: 파일 존재 확인
        assert output_path.exists()

        # Assert: CSV 읽기 가능
        loaded_df = pd.read_csv(output_path)
        assert len(loaded_df) == 2
        assert "order_id" in loaded_df.columns
        assert "pnl" in loaded_df.columns


# Test 4: 빈 DataFrame Export
def test_export_to_csv_empty():
    """
    빈 DataFrame 처리

    Given: 빈 DataFrame
    When: export_to_csv() 호출
    Then: 빈 CSV 파일 생성 (헤더만)
    """
    df = pd.DataFrame()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "empty.csv"

        # Act: CSV 생성
        export_to_csv(df, str(output_path))

        # Assert: 파일 존재 (빈 파일)
        assert output_path.exists()
