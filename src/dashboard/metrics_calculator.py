"""
src/dashboard/metrics_calculator.py

Phase 14a (Dashboard) Phase 2: DataFrame → Metrics 변환

DoD:
- Summary Metrics (Total PnL, Win Rate, Trade Count)
- Session Risk (Daily/Weekly Loss, Loss Streak)
- Regime Breakdown (Regime별 성과)
- Slippage Stats (평균, 최대, p95)
- Latency Stats (평균, p95, p99)
"""

from typing import Dict, Any, Union
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


def calculate_summary(df: pd.DataFrame) -> Dict[str, float]:
    """
    Summary Metrics 계산: Total PnL, Win Rate, Trade Count

    Args:
        df: 거래 DataFrame (pnl 컬럼 필수)

    Returns:
        Dict[str, float]: Summary Metrics
            - total_pnl: 총 PnL (USDT)
            - win_rate: 승률 (0.0 ~ 1.0)
            - trade_count: 거래 수
            - win_count: 승리 거래 수
            - loss_count: 손실 거래 수
    """
    if df.empty:
        return {
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
        }

    total_pnl = df["pnl"].sum()
    trade_count = len(df)
    win_count = (df["pnl"] > 0).sum()
    loss_count = trade_count - win_count
    win_rate = win_count / trade_count if trade_count > 0 else 0.0

    return {
        "total_pnl": float(total_pnl),
        "win_rate": float(win_rate),
        "trade_count": int(trade_count),
        "win_count": int(win_count),
        "loss_count": int(loss_count),
    }


def calculate_session_risk(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Session Risk 계산: Daily/Weekly Loss, Loss Streak

    Args:
        df: 거래 DataFrame (pnl, fills 컬럼 필수)

    Returns:
        Dict[str, Any]: Session Risk Metrics
            - daily_max_loss: 일별 손실 중 최대값 (음수)
            - weekly_max_loss: 주간 손실 합계 (음수)
            - max_loss_streak: 연속 손실 횟수
    """
    if df.empty:
        return {
            "daily_max_loss": 0.0,
            "weekly_max_loss": 0.0,
            "max_loss_streak": 0,
        }

    # fills에서 timestamp 추출 (첫 번째 fill 기준)
    df = df.copy()
    df["date"] = df["fills"].apply(
        lambda fills: _parse_timestamp(fills[0]["timestamp"]).date()
        if fills else None
    )

    # 일별 PnL 집계
    daily_pnl = df.groupby("date")["pnl"].sum()

    # 일별 최대 손실 (음수 중 가장 작은 값)
    daily_losses = daily_pnl[daily_pnl < 0]
    daily_max_loss = daily_losses.min() if not daily_losses.empty else 0.0

    # 주간 손실 (전체 손실 합계)
    total_pnl = df["pnl"].sum()
    weekly_max_loss = total_pnl if total_pnl < 0 else 0.0

    # 연속 손실 스트릭 계산
    max_loss_streak = _calculate_max_loss_streak(df["pnl"].tolist())

    return {
        "daily_max_loss": float(daily_max_loss),
        "weekly_max_loss": float(weekly_max_loss),
        "max_loss_streak": int(max_loss_streak),
    }


def _calculate_max_loss_streak(pnls: list) -> int:
    """
    연속 손실 스트릭 계산

    Args:
        pnls: PnL 목록

    Returns:
        int: 최대 연속 손실 횟수
    """
    if not pnls:
        return 0

    max_streak = 0
    current_streak = 0

    for pnl in pnls:
        if pnl < 0:  # 손실
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:  # 승리
            current_streak = 0

    return max_streak


def calculate_regime_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """
    Market Regime별 성과 분석

    Args:
        df: 거래 DataFrame (market_regime, pnl 컬럼 필수)

    Returns:
        pd.DataFrame: Regime별 성과
            - regime: Market Regime 이름
            - trade_count: 거래 수
            - win_rate: 승률
            - total_pnl: 총 PnL
    """
    if df.empty:
        return pd.DataFrame(columns=["regime", "trade_count", "win_rate", "total_pnl"])

    # Regime별 그룹화
    grouped = df.groupby("market_regime")

    # Regime별 집계 (win_count 포함)
    breakdown = grouped.agg(
        trade_count=("pnl", "count"),
        total_pnl=("pnl", "sum"),
        win_count=("pnl", lambda x: (x > 0).sum()),  # 승리 거래 수
    ).reset_index()

    # Win Rate 계산 (승리 거래 비율)
    breakdown["win_rate"] = breakdown["win_count"] / breakdown["trade_count"]
    breakdown.drop(columns=["win_count"], inplace=True)  # win_count는 제거

    # 컬럼 순서 정렬
    breakdown = breakdown[["market_regime", "trade_count", "win_rate", "total_pnl"]]
    breakdown.rename(columns={"market_regime": "regime"}, inplace=True)

    return breakdown


def calculate_slippage_stats(df: pd.DataFrame) -> Dict[str, float]:
    """
    Slippage 통계: 평균, 최대, p95

    Args:
        df: 거래 DataFrame (slippage_usd 컬럼 필수)

    Returns:
        Dict[str, float]: Slippage Stats
            - avg_slippage: 평균 Slippage (USD)
            - max_slippage: 최대 Slippage (USD)
            - p95_slippage: p95 Slippage (USD)
    """
    if df.empty:
        return {
            "avg_slippage": 0.0,
            "max_slippage": 0.0,
            "p95_slippage": 0.0,
        }

    avg_slippage = df["slippage_usd"].mean()
    max_slippage = df["slippage_usd"].max()
    p95_slippage = df["slippage_usd"].quantile(0.95)

    return {
        "avg_slippage": float(avg_slippage),
        "max_slippage": float(max_slippage),
        "p95_slippage": float(p95_slippage),
    }


def calculate_latency_stats(df: pd.DataFrame) -> Dict[str, float]:
    """
    Latency 통계: 평균, p95, p99

    Args:
        df: 거래 DataFrame (latency_total_ms 컬럼 필수)

    Returns:
        Dict[str, float]: Latency Stats
            - avg_latency_ms: 평균 Latency (ms)
            - p95_latency_ms: p95 Latency (ms)
            - p99_latency_ms: p99 Latency (ms)
    """
    if df.empty:
        return {
            "avg_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
        }

    avg_latency = df["latency_total_ms"].mean()
    p95_latency = df["latency_total_ms"].quantile(0.95)
    p99_latency = df["latency_total_ms"].quantile(0.99)

    return {
        "avg_latency_ms": float(avg_latency),
        "p95_latency_ms": float(p95_latency),
        "p99_latency_ms": float(p99_latency),
    }
