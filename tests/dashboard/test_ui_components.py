"""
tests/dashboard/test_ui_components.py

Phase 14a (Dashboard) Phase 3: UI Components 테스트

TDD RED Phase: 테스트 먼저 작성 (구현은 아직 없음)
"""

import pytest
import pandas as pd
from datetime import date
from typing import Dict, Any


# Test 1: Metric Card 렌더링
def test_render_metric_card():
    """
    메트릭 카드 생성: 레이블, 값, Delta

    Given: 메트릭 값 (label, value, delta)
    When: create_metric_card() 호출
    Then: 메트릭 카드 데이터 반환 (Dict)
    """
    from src.dashboard.ui_components import create_metric_card

    # Act
    card = create_metric_card(
        label="Total PnL",
        value=125.50,
        delta=10.5,
        delta_color="normal"  # "normal" (green if positive) or "inverse"
    )

    # Assert
    assert isinstance(card, dict)
    assert card["label"] == "Total PnL"
    assert card["value"] == 125.50
    assert card["delta"] == 10.5
    assert card["delta_color"] == "normal"


# Test 2: PnL Chart 생성
def test_render_pnl_chart():
    """
    PnL 시계열 차트 생성

    Given: 거래 DataFrame (fills.timestamp, pnl 포함)
    When: create_pnl_chart() 호출
    Then: plotly Figure 객체 반환
    """
    from src.dashboard.ui_components import create_pnl_chart
    import plotly.graph_objects as go

    # Arrange: 테스트 데이터
    df = pd.DataFrame([
        {
            "order_id": "o1",
            "pnl": 10.0,
            "fills": [{"timestamp": "2026-02-01T10:00:00"}]
        },
        {
            "order_id": "o2",
            "pnl": -5.0,
            "fills": [{"timestamp": "2026-02-01T11:00:00"}]
        },
        {
            "order_id": "o3",
            "pnl": 15.0,
            "fills": [{"timestamp": "2026-02-01T12:00:00"}]
        },
    ])

    # Act
    fig = create_pnl_chart(df)

    # Assert
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0  # 최소 1개 trace 존재
    assert fig.layout.title.text == "누적 손익 추이"


# Test 3: Trade Distribution 히스토그램
def test_render_trade_distribution():
    """
    Entry/Exit 분포 히스토그램 생성

    Given: 거래 DataFrame (pnl 포함)
    When: create_trade_distribution() 호출
    Then: plotly Figure 객체 반환
    """
    from src.dashboard.ui_components import create_trade_distribution
    import plotly.graph_objects as go

    # Arrange: 테스트 데이터
    df = pd.DataFrame([
        {"order_id": "o1", "pnl": 10.0},
        {"order_id": "o2", "pnl": -5.0},
        {"order_id": "o3", "pnl": 15.0},
        {"order_id": "o4", "pnl": -3.0},
        {"order_id": "o5", "pnl": 20.0},
    ])

    # Act
    fig = create_trade_distribution(df)

    # Assert
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0
    assert fig.layout.title.text == "손익 분포"


# Test 4: Session Risk Gauge 차트
def test_render_session_risk_gauge():
    """
    Session Risk 게이지 차트 생성

    Given: Session Risk Metrics (daily_max_loss, 임계값)
    When: create_session_risk_gauge() 호출
    Then: plotly Figure 객체 반환
    """
    from src.dashboard.ui_components import create_session_risk_gauge
    import plotly.graph_objects as go

    # Arrange: 테스트 데이터
    risk_metrics = {
        "daily_max_loss": -50.0,
        "weekly_max_loss": -150.0,
        "max_loss_streak": 3,
    }

    # Act
    fig = create_session_risk_gauge(
        daily_max_loss=risk_metrics["daily_max_loss"],
        threshold=-100.0  # 임계값 (위험 기준선)
    )

    # Assert
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0
    # Indicator 차트의 title은 data[0].title에 있음
    assert fig.data[0].title.text == "일일 최대 손실"


# Test 5: Sidebar Filters 데이터 생성
def test_sidebar_filters():
    """
    사이드바 날짜 필터 데이터 생성

    Given: DataFrame (fills.timestamp 포함)
    When: get_date_range() 호출
    Then: (min_date, max_date) 튜플 반환
    """
    from src.dashboard.ui_components import get_date_range

    # Arrange: 테스트 데이터
    df = pd.DataFrame([
        {"order_id": "o1", "fills": [{"timestamp": "2026-02-01T10:00:00"}]},
        {"order_id": "o2", "fills": [{"timestamp": "2026-02-05T11:00:00"}]},
        {"order_id": "o3", "fills": [{"timestamp": "2026-02-10T12:00:00"}]},
    ])

    # Act
    min_date, max_date = get_date_range(df)

    # Assert
    assert isinstance(min_date, date)
    assert isinstance(max_date, date)
    assert min_date == date(2026, 2, 1)
    assert max_date == date(2026, 2, 10)


# Test 6: Empty DataFrame 처리
def test_empty_dataframe_handling():
    """
    빈 DataFrame 처리

    Given: 빈 DataFrame
    When: UI 컴포넌트 함수 호출
    Then: 에러 없이 처리, 기본값 반환
    """
    from src.dashboard.ui_components import create_pnl_chart, get_date_range

    # Arrange: 빈 DataFrame
    df_empty = pd.DataFrame()

    # Act & Assert: PnL Chart
    fig = create_pnl_chart(df_empty)
    assert fig is not None

    # Act & Assert: Date Range (빈 DataFrame → None, None)
    min_date, max_date = get_date_range(df_empty)
    assert min_date is None
    assert max_date is None
