"""
src/dashboard/export.py

Phase 14a (Dashboard) Phase 5: 데이터 Export 및 필터링 유틸리티

DoD:
- 날짜 범위 필터링
- CSV Export
"""

from datetime import date
from typing import Union
import pandas as pd
from datetime import datetime


def _parse_timestamp(ts: Union[str, float, int]) -> datetime:
    """
    Timestamp 파싱 (ISO 8601 문자열 또는 Unix timestamp)

    Args:
        ts: Timestamp (ISO 8601 문자열 또는 Unix timestamp)

    Returns:
        datetime: 파싱된 datetime 객체
    """
    if isinstance(ts, (float, int)):
        return datetime.fromtimestamp(ts)
    else:
        return datetime.fromisoformat(str(ts))


def apply_date_filter(
    df: pd.DataFrame,
    start_date: date,
    end_date: date
) -> pd.DataFrame:
    """
    날짜 범위 필터링

    Args:
        df: 거래 DataFrame (fills 컬럼 필수)
        start_date: 시작 날짜 (포함)
        end_date: 종료 날짜 (포함)

    Returns:
        pd.DataFrame: 필터링된 DataFrame
    """
    if df.empty:
        return df

    # fills에서 timestamp 추출
    df = df.copy()
    df["_date"] = df["fills"].apply(
        lambda fills: _parse_timestamp(fills[0]["timestamp"]).date()
        if fills else None
    )

    # 날짜 범위 필터
    mask = (df["_date"] >= start_date) & (df["_date"] <= end_date)
    filtered = df[mask].drop(columns=["_date"])

    return filtered


def export_to_csv(df: pd.DataFrame, filename: str) -> None:
    """
    DataFrame을 CSV 파일로 Export

    Args:
        df: 거래 DataFrame
        filename: 출력 파일 경로
    """
    df.to_csv(filename, index=False, encoding="utf-8")
