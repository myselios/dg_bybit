"""
src/dashboard/ui_components.py

Phase 14a (Dashboard) Phase 3: Streamlit UI Components

DoD:
- Metric Card 생성 (PnL, Win Rate, Trade Count)
- PnL 시계열 차트 (Plotly)
- Trade Distribution 히스토그램
- Session Risk 게이지 차트
- Date Range 추출
"""

from typing import Dict, Any, Optional, Tuple, Union
from datetime import datetime, date
import pandas as pd
import plotly.graph_objects as go  # type: ignore[import-untyped]


def _parse_timestamp(ts: Union[str, float, int]) -> datetime:
    """
    Timestamp 파싱 (ISO 8601 문자열 또는 Unix timestamp)

    Args:
        ts: Timestamp (ISO 8601 문자열 또는 Unix timestamp)

    Returns:
        datetime: 파싱된 datetime 객체
    """
    if isinstance(ts, (float, int)):
        # Unix timestamp (초 단위)
        return datetime.fromtimestamp(ts)
    else:
        # ISO 8601 문자열
        return datetime.fromisoformat(str(ts))


def create_metric_card(
    label: str,
    value: float,
    delta: float,
    delta_color: str = "normal"
) -> Dict[str, Any]:
    """
    메트릭 카드 데이터 생성 (Streamlit st.metric 호환)

    Args:
        label: 메트릭 레이블
        value: 메트릭 값
        delta: 변화량
        delta_color: Delta 색상 ("normal" or "inverse")

    Returns:
        Dict[str, Any]: 메트릭 카드 데이터
    """
    return {
        "label": label,
        "value": value,
        "delta": delta,
        "delta_color": delta_color,
    }


def create_pnl_chart(df: pd.DataFrame) -> go.Figure:
    """
    PnL 시계열 차트 생성 (Cumulative PnL)

    Args:
        df: 거래 DataFrame (pnl, fills 컬럼 필수)

    Returns:
        go.Figure: Plotly Figure 객체
    """
    if df.empty:
        # 빈 DataFrame → 빈 차트 반환
        fig = go.Figure()
        fig.update_layout(
            title="Cumulative PnL Over Time",
            xaxis_title="Time",
            yaxis_title="Cumulative PnL (USDT)",
            template="plotly_white",
        )
        return fig

    # Timestamp 추출 (fills[0].timestamp)
    df = df.copy()
    df["timestamp"] = df["fills"].apply(
        lambda fills: _parse_timestamp(fills[0]["timestamp"])
        if fills else None
    )

    # Cumulative PnL 계산
    df = df.sort_values("timestamp")
    df["cumulative_pnl"] = df["pnl"].cumsum()

    # Plotly Line Chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["cumulative_pnl"],
        mode="lines+markers",
        name="누적 손익",
        line=dict(color="blue", width=2),
        marker=dict(size=6),
    ))

    # 0 라인 추가 (Break-even)
    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="red",
        annotation_text="손익분기점",
    )

    fig.update_layout(
        title="누적 손익 추이",
        xaxis_title="시간",
        yaxis_title="누적 손익 (USDT)",
        template="plotly_white",
        hovermode="x unified",
    )

    return fig


def create_trade_distribution(df: pd.DataFrame) -> go.Figure:
    """
    PnL 분포 히스토그램 생성

    Args:
        df: 거래 DataFrame (pnl 컬럼 필수)

    Returns:
        go.Figure: Plotly Figure 객체
    """
    if df.empty:
        # 빈 DataFrame → 빈 차트 반환
        fig = go.Figure()
        fig.update_layout(
            title="PnL Distribution",
            xaxis_title="PnL (USDT)",
            yaxis_title="Frequency",
            template="plotly_white",
        )
        return fig

    # Histogram
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=df["pnl"],
        nbinsx=20,
        name="손익 분포",
        marker=dict(
            color=df["pnl"],
            colorscale="RdYlGn",
            line=dict(color="black", width=1),
        ),
    ))

    # 0 라인 추가
    fig.add_vline(
        x=0,
        line_dash="dash",
        line_color="black",
        annotation_text="손익분기점",
    )

    fig.update_layout(
        title="손익 분포",
        xaxis_title="손익 (USDT)",
        yaxis_title="빈도",
        template="plotly_white",
        showlegend=False,
    )

    return fig


def create_session_risk_gauge(
    daily_max_loss: float,
    threshold: float = -100.0
) -> go.Figure:
    """
    Session Risk 게이지 차트 생성 (Daily Max Loss)

    Args:
        daily_max_loss: 일별 최대 손실 (음수)
        threshold: 위험 임계값 (음수, 기본 -100.0)

    Returns:
        go.Figure: Plotly Figure 객체
    """
    # Gauge 차트 (손실을 양수로 변환해서 표시)
    loss_abs = abs(daily_max_loss)
    threshold_abs = abs(threshold)

    # Gauge 범위: 0 ~ threshold * 2
    gauge_max = threshold_abs * 2

    # 위험 수준 계산 (0% ~ 100%)
    risk_pct = min((loss_abs / threshold_abs) * 100, 100) if threshold_abs > 0 else 0

    # Gauge 색상 (녹색 → 노란색 → 빨간색)
    if risk_pct < 50:
        gauge_color = "green"
    elif risk_pct < 80:
        gauge_color = "yellow"
    else:
        gauge_color = "red"

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=loss_abs,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': "일일 최대 손실"},
        delta={'reference': threshold_abs, 'increasing': {'color': "red"}},
        gauge={
            'axis': {'range': [None, gauge_max]},
            'bar': {'color': gauge_color},
            'steps': [
                {'range': [0, threshold_abs * 0.5], 'color': "lightgreen"},
                {'range': [threshold_abs * 0.5, threshold_abs], 'color': "lightyellow"},
                {'range': [threshold_abs, gauge_max], 'color': "lightcoral"},
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': threshold_abs
            }
        }
    ))

    return fig


def get_date_range(df: pd.DataFrame) -> Tuple[Optional[date], Optional[date]]:
    """
    DataFrame에서 날짜 범위 추출 (fills.timestamp 기준)

    Args:
        df: 거래 DataFrame (fills 컬럼 필수)

    Returns:
        Tuple[Optional[date], Optional[date]]: (min_date, max_date)
    """
    if df.empty:
        return None, None

    # Timestamp 추출
    df = df.copy()
    df["timestamp"] = df["fills"].apply(
        lambda fills: _parse_timestamp(fills[0]["timestamp"])
        if fills else None
    )

    # 날짜 범위 추출
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return None, None

    min_date = df["timestamp"].min().date()
    max_date = df["timestamp"].max().date()

    return min_date, max_date
