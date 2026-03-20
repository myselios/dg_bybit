"""
src/dashboard/app.py

Phase 14a (Dashboard) Phase 3: Streamlit 진입점

실행 방법:
    streamlit run src/dashboard/app.py

DoD:
- Page Config (title, icon, layout="wide")
- 데이터 로드 (logs/ 디렉토리)
- 메트릭 카드 3개 (Total PnL, Win Rate, Trade Count)
- PnL 시계열 차트
- Trade Distribution 히스토그램
- Session Risk 게이지
"""

from pathlib import Path
from typing import Optional, Dict, Any
import os
import streamlit as st
import pandas as pd

# Dashboard 모듈 import
from src.dashboard.data_pipeline import load_log_files, parse_jsonl, to_dataframe
from src.dashboard.metrics_calculator import (
    calculate_summary,
    calculate_session_risk,
    calculate_regime_breakdown,
    calculate_slippage_stats,
    calculate_latency_stats,
    calculate_cumulative_pnl,
    calculate_win_rate_by_regime,
    calculate_max_drawdown,
    calculate_hold_time_stats,
    calculate_daily_pnl,
)
from src.dashboard.ui_components import (
    create_pnl_chart,
    create_trade_distribution,
    create_session_risk_gauge,
    create_journal_tab,
    get_date_range,
)
from src.dashboard.data_pipeline import load_journal_df, calculate_journal_stats, load_all_trades, get_summary_stats
from src.dashboard.file_watcher import (
    get_latest_modification_time,
    has_directory_changed,
)
from src.dashboard.export import (
    apply_date_filter,
    export_to_csv,
)


# ============================================================================
# Page Configuration
# ============================================================================

st.set_page_config(
    page_title="CBGB Trade Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================================
# Data Loading
# ============================================================================

@st.cache_data(ttl=60)  # 60초 캐시 (실시간 업데이트 대비)
def load_trade_data(log_dir: str) -> pd.DataFrame:
    """
    Trade log 데이터 로드

    Args:
        log_dir: 로그 디렉토리 경로

    Returns:
        pd.DataFrame: 거래 DataFrame
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        st.error(f"❌ Log directory not found: {log_dir}")
        return pd.DataFrame()

    # 로그 파일 로드
    log_files = load_log_files(log_path)
    if not log_files:
        st.warning(f"⚠️ No .log files found in: {log_dir}")
        return pd.DataFrame()

    # JSONL 파싱 (모든 파일 병합)
    all_logs = []
    for file in log_files:
        logs = parse_jsonl(file)
        all_logs.extend(logs)

    if not all_logs:
        st.warning("⚠️ No valid trade logs found")
        return pd.DataFrame()

    # DataFrame 변환
    df = to_dataframe(all_logs)
    return df


@st.cache_resource
def _get_bybit_client():
    """공유 BybitRestClient 인스턴스 (Mainnet)"""
    from src.infrastructure.exchange.bybit_rest_client import BybitRestClient

    api_key = os.getenv("BYBIT_MAINNET_API_KEY")
    api_secret = os.getenv("BYBIT_MAINNET_API_SECRET")

    if not api_key or not api_secret:
        return None

    return BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api.bybit.com"
    )


@st.cache_data(ttl=10)
def fetch_position_data() -> Optional[Dict[str, Any]]:
    """Bybit API로 실시간 포지션 조회"""
    try:
        client = _get_bybit_client()
        if client is None:
            return None

        response = client.get_position(category="linear", symbol="BTCUSDT")

        if response.get("retCode") == 0:
            positions = response.get("result", {}).get("list", [])
            if positions:
                pos = positions[0]
                size = float(pos.get("size", "0"))
                if size > 0:
                    return {
                        "size": pos.get("size", "0"),
                        "side": pos.get("side", "None"),
                        "avgPrice": pos.get("avgPrice", "0"),
                        "unrealisedPnl": pos.get("unrealisedPnl", "0"),
                        "stopLoss": pos.get("stopLoss", "0"),
                    }
            return {"size": "0", "side": "None", "avgPrice": "0", "unrealisedPnl": "0", "stopLoss": "0"}
        return None

    except Exception as e:
        import traceback
        print(f"❌ Position API Error: {e}")
        print(traceback.format_exc())
        return None


@st.cache_data(ttl=10)
def fetch_equity_data() -> Optional[float]:
    """Bybit API로 현재 자산(Equity) 조회"""
    try:
        client = _get_bybit_client()
        if client is None:
            return None

        response = client.get_wallet_balance(accountType="UNIFIED")

        if response.get("retCode") == 0:
            wallet_list = response.get("result", {}).get("list", [])
            if wallet_list:
                return float(wallet_list[0].get("totalEquity", 0.0))
        return None

    except Exception as e:
        import traceback
        print(f"❌ Equity API Error: {e}")
        print(traceback.format_exc())
        return None


# ============================================================================
# Main App
# ============================================================================

def main():
    """Streamlit 앱 메인 함수"""

    # Custom CSS for card-style UI
    st.markdown("""
    <style>
    /* 전체 폭/여백 */
    .block-container { padding-top: 1.4rem; padding-bottom: 2.2rem; }

    /* 섹션 타이틀 간격 줄이기 */
    h1, h2, h3 { letter-spacing: -0.3px; }
    h2 { margin-top: 0.8rem; margin-bottom: 0.6rem; }

    /* Metric을 카드처럼 보이게 */
    [data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 14px;
        padding: 14px 14px;
        box-shadow: 0 1px 0 rgba(0,0,0,0.02);
    }
    [data-testid="stMetricLabel"] { color: #6B7280; font-size: 0.875rem; }
    [data-testid="stMetricValue"] { font-weight: 750; font-size: 1.5rem; }
    [data-testid="stMetricDelta"] { font-weight: 650; }

    /* 사이드바 덜 답답하게 */
    section[data-testid="stSidebar"] {
        background: #F6F7FB;
        border-right: 1px solid #E5E7EB;
    }

    /* Header bar */
    .header-bar {
        background: linear-gradient(90deg, #4F46E5 0%, #7C3AED 100%);
        color: white;
        padding: 1.2rem 1.5rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 6px rgba(79, 70, 229, 0.15);
    }
    .header-title { font-size: 1.75rem; font-weight: 700; margin: 0; }
    .header-subtitle { font-size: 0.875rem; opacity: 0.9; margin-top: 0.25rem; }
    .status-pill {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        background: rgba(255,255,255,0.2);
        margin-left: 0.5rem;
    }
    </style>
    """, unsafe_allow_html=True)

    # Temporary: Header Bar (Status pill will be updated after data load)
    header_placeholder = st.empty()

    # 사이드바: 로그 디렉토리 선택
    st.sidebar.header("⚙️ 설정")
    log_dir = st.sidebar.text_input(
        "로그 디렉토리",
        value="logs/mainnet",
        help="Trade log 디렉토리 경로"
    )

    # Auto-refresh 설정
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔄 자동 새로고침")

    # 파일 변경 감지
    log_path = Path(log_dir)
    if "last_check_time" not in st.session_state:
        st.session_state.last_check_time = get_latest_modification_time(log_path) if log_path.exists() else None

    # 변경 감지 여부 표시
    if log_path.exists():
        is_changed = has_directory_changed(log_path, st.session_state.last_check_time)
        if is_changed:
            st.sidebar.info("📝 새 데이터 감지됨")

    # 새로고침 버튼
    if st.sidebar.button("🔄 새로고침", help="로그 파일 변경사항 확인 및 데이터 재로드"):
        # 캐시 무효화
        load_trade_data.clear()
        # 마지막 확인 시간 업데이트
        st.session_state.last_check_time = get_latest_modification_time(log_path) if log_path.exists() else None
        st.rerun()

    # 데이터 로드
    with st.spinner("📂 Loading trade data..."):
        df = load_trade_data(log_dir)

    # 데이터 없음 처리
    if df.empty:
        st.info("ℹ️ No trade data available. Please check the log directory.")
        st.stop()

    # 날짜 범위 추출
    min_date, max_date = get_date_range(df)

    # 날짜 필터 (사이드바)
    st.sidebar.markdown("---")
    st.sidebar.subheader("📅 날짜 필터")

    if min_date and max_date:
        col_start, col_end = st.sidebar.columns(2)
        with col_start:
            start_date = st.date_input(
                "시작일",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
                help="분석 시작 날짜"
            )
        with col_end:
            end_date = st.date_input(
                "종료일",
                value=max_date,
                min_value=min_date,
                max_value=max_date,
                help="분석 종료 날짜"
            )

        # 날짜 필터 적용
        df = apply_date_filter(df, start_date, end_date)

        if df.empty:
            st.warning("⚠️ 선택한 날짜 범위에 데이터가 없습니다.")
            st.stop()
    else:
        st.sidebar.info("날짜 정보 없음")

    # CSV Export 버튼
    st.sidebar.markdown("---")
    st.sidebar.subheader("💾 데이터 Export")

    # CSV 다운로드 버튼
    import io
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, encoding="utf-8")
    csv_data = csv_buffer.getvalue()

    st.sidebar.download_button(
        label="📥 CSV 다운로드",
        data=csv_data,
        file_name=f"trades_{start_date}_{end_date}.csv" if min_date else "trades.csv",
        mime="text/csv",
        help="현재 필터링된 데이터를 CSV로 다운로드"
    )

    # Calculate metrics first for status determination
    summary = calculate_summary(df)
    risk_metrics = calculate_session_risk(df)

    # Determine status based on data
    status = "OK"
    status_color = "rgba(16, 185, 129, 0.3)"  # Green
    if risk_metrics['daily_max_loss'] < -50:  # Example threshold
        status = "HALT"
        status_color = "rgba(239, 68, 68, 0.3)"  # Red
    elif len(df) > 0:
        status = "LIVE"
        status_color = "rgba(59, 130, 246, 0.3)"  # Blue

    # Render Header Bar with dynamic status
    header_placeholder.markdown(f"""
    <div class="header-bar">
        <div class="header-title">📊 CBGB Trade Dashboard <span class="status-pill" style="background: {status_color};">{status}</span></div>
        <div class="header-subtitle">BTC/USDT Linear Futures · Mainnet Dry-Run · {len(df)} trades</div>
    </div>
    """, unsafe_allow_html=True)

    # --- KPI Strip (핵심 지표 7개) ---
    st.markdown("### 핵심 지표")

    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5, kpi_col6, kpi_col7 = st.columns(7)

    with kpi_col1:
        # Determine current position status from Bybit API (real-time)
        position_data = fetch_position_data()

        if position_data is None:
            # API error or credentials missing
            position_status = "UNKNOWN"
            position_color = "⚠️"
            position_delta = "API 오류"
        elif float(position_data.get("size", "0") or "0") > 0:
            # Position exists
            side = position_data.get("side", "None")
            position_status = "IN POSITION"
            position_color = "🟢"
            position_delta = side.upper() if side != "None" else "LONG"
        else:
            # FLAT (no position)
            position_status = "FLAT"
            position_color = "⚪"
            position_delta = "대기 중"

        st.metric(
            label="현재 상태",
            value=f"{position_color} {position_status}",
            delta=position_delta,
            help="현재 포지션 상태 (FLAT: 포지션 없음, IN POSITION: 포지션 있음)"
        )

    with kpi_col2:
        # Calculate delta as percentage of initial equity (example: $100)
        initial_equity = 100  # Assume starting equity
        pnl_pct = (summary['total_pnl'] / initial_equity) * 100 if initial_equity > 0 else 0
        st.metric(
            label="총 손익",
            value=f"${summary['total_pnl']:.2f}",
            delta=f"{pnl_pct:+.1f}%",
            help="누적 손익 (USDT)"
        )

    with kpi_col3:
        st.metric(
            label="승률",
            value=f"{summary['win_rate'] * 100:.1f}%",
            delta=None,
            help="승률 (승리 / 전체)"
        )

    with kpi_col4:
        st.metric(
            label="거래 횟수",
            value=f"{summary['trade_count']}",
            delta=None,
            help="총 거래 수"
        )

    with kpi_col5:
        st.metric(
            label="Daily Max Loss",
            value=f"${risk_metrics['daily_max_loss']:.2f}",
            delta=None,
            help="일일 최대 손실"
        )

    with kpi_col6:
        st.metric(
            label="승/패",
            value=f"{summary['win_count']}/{summary['loss_count']}",
            delta=None,
            help="승리 / 패배 거래 수"
        )

    with kpi_col7:
        equity = fetch_equity_data()
        if equity is not None:
            equity_delta = f"{((equity - 100) / 100) * 100:+.1f}%"  # vs 초기 $100
            st.metric(
                label="현재 자산",
                value=f"${equity:.2f}",
                delta=equity_delta,
                help="현재 계좌 Equity (USDT, Bybit API 실시간)"
            )
        else:
            st.metric(
                label="현재 자산",
                value="N/A",
                delta="API 오류",
                help="Bybit API 연결 실패 — 환경변수 확인"
            )

    st.markdown("---")

    # --- Tabs (Overview / 성과 분석 / Risk / Diagnostics / 매매일지) ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview",
        "📈 성과 분석",
        "⚙️ Risk & Config",
        "⚡ Diagnostics",
        "📒 매매일지",
    ])

    # TAB 1: Overview
    with tab1:
        # PnL Chart
        st.header("📊 누적 손익")
        fig_pnl = create_pnl_chart(df)
        st.plotly_chart(fig_pnl, use_container_width=True)

        # Trade Distribution & Summary
        st.header("📊 상세 분석")
        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("손익 분포")
            fig_dist = create_trade_distribution(df)
            st.plotly_chart(fig_dist, use_container_width=True)

        with col_right:
            st.subheader("요약 메트릭")
            st.metric("총 손익 (USDT)", f"${summary['total_pnl']:.2f}")
            st.metric("승률", f"{summary['win_rate'] * 100:.1f}%")
            st.metric("거래 횟수", f"{summary['trade_count']}")

    # TAB 2: 성과 분석
    with tab2:
        st.header("📈 성과 분석")

        # load_all_trades로 enriched DataFrame 사용 (entry_time/exit_time 포함)
        all_trades_df = load_all_trades(log_dir)

        if all_trades_df.empty:
            st.info("ℹ️ 트레이드 데이터가 없습니다.")
        else:
            import plotly.graph_objects as _go
            import plotly.express as _px

            # --- 요약 통계 배너 ---
            summary_stats = get_summary_stats(all_trades_df)
            s_col1, s_col2, s_col3, s_col4, s_col5 = st.columns(5)
            with s_col1:
                st.metric("총 트레이드", summary_stats["total_trades"])
            with s_col2:
                st.metric("승률", f"{summary_stats['win_rate'] * 100:.1f}%")
            with s_col3:
                st.metric("총 손익", f"${summary_stats['total_pnl']:.2f}")
            with s_col4:
                rr = summary_stats["rr_ratio"]
                st.metric("R:R 비율", f"{rr:.2f}" if rr > 0 else "N/A")
            with s_col5:
                md = summary_stats["max_drawdown"]
                st.metric("최대 드로다운", f"${md:.2f}", delta=None)

            st.markdown("---")

            # --- PnL 누적 곡선 ---
            st.subheader("누적 PnL 곡선")
            cum_pnl = calculate_cumulative_pnl(all_trades_df)
            if not cum_pnl.empty:
                cum_df = cum_pnl.reset_index()
                cum_df.columns = ["exit_time", "cumulative_pnl"]
                cum_df = cum_df.dropna(subset=["exit_time"])

                fig_cum = _go.Figure()
                fig_cum.add_trace(_go.Scatter(
                    x=cum_df["exit_time"],
                    y=cum_df["cumulative_pnl"],
                    mode="lines+markers",
                    name="누적 PnL",
                    line=dict(color="#4F46E5", width=2),
                    marker=dict(size=5),
                ))
                fig_cum.add_hline(y=0, line_dash="dash", line_color="gray",
                                  annotation_text="손익분기")
                fig_cum.update_layout(
                    xaxis_title="청산 시각",
                    yaxis_title="누적 손익 (USDT)",
                    template="plotly_white",
                    height=320,
                    margin=dict(l=40, r=40, t=30, b=40),
                    hovermode="x unified",
                )
                st.plotly_chart(fig_cum, use_container_width=True)
            else:
                st.info("exit_time 데이터가 없어 누적 PnL 곡선을 표시할 수 없습니다.")

            st.markdown("---")

            # --- 일별 PnL bar chart + Regime 승률 ---
            perf_left, perf_right = st.columns(2)

            with perf_left:
                st.subheader("일별 PnL")
                daily = calculate_daily_pnl(all_trades_df)
                if not daily.empty:
                    colors = ["#10B981" if v >= 0 else "#EF4444" for v in daily.values]
                    fig_daily = _go.Figure(_go.Bar(
                        x=daily.index,
                        y=daily.values,
                        marker_color=colors,
                        name="일별 PnL",
                    ))
                    fig_daily.add_hline(y=0, line_dash="dash", line_color="gray")
                    fig_daily.update_layout(
                        xaxis_title="날짜",
                        yaxis_title="PnL (USDT)",
                        template="plotly_white",
                        height=300,
                        margin=dict(l=30, r=30, t=30, b=30),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_daily, use_container_width=True)
                else:
                    st.info("exit_time 정보가 없어 일별 PnL을 표시할 수 없습니다.")

            with perf_right:
                st.subheader("Regime별 승률")
                regime_wr = calculate_win_rate_by_regime(all_trades_df)
                if regime_wr:
                    fig_regime = _go.Figure(_go.Bar(
                        x=list(regime_wr.keys()),
                        y=[v * 100 for v in regime_wr.values()],
                        marker_color="#7C3AED",
                        name="승률(%)",
                    ))
                    fig_regime.add_hline(y=50, line_dash="dash", line_color="gray",
                                         annotation_text="50%")
                    fig_regime.update_layout(
                        xaxis_title="Market Regime",
                        yaxis_title="승률 (%)",
                        template="plotly_white",
                        height=300,
                        margin=dict(l=30, r=30, t=30, b=30),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_regime, use_container_width=True)
                else:
                    st.info("market_regime 데이터가 없습니다.")

            st.markdown("---")

            # --- 최대 드로다운 ---
            st.subheader("드로다운 분석")
            dd_stats = calculate_max_drawdown(all_trades_df)
            dd_col1, dd_col2 = st.columns(2)
            with dd_col1:
                st.metric("최대 드로다운 (USD)", f"${dd_stats['max_drawdown_usd']:.2f}")
            with dd_col2:
                dd_pct = dd_stats["max_drawdown_pct"] * 100
                st.metric("최대 드로다운 (%)", f"{dd_pct:.1f}%")

            dd_series = dd_stats["drawdown_series"]
            if not dd_series.empty:
                dd_df = dd_series.reset_index()
                dd_df.columns = ["exit_time", "drawdown"]
                dd_df = dd_df.dropna(subset=["exit_time"])
                fig_dd = _go.Figure(_go.Scatter(
                    x=dd_df["exit_time"],
                    y=dd_df["drawdown"],
                    fill="tozeroy",
                    mode="lines",
                    line=dict(color="#EF4444", width=1.5),
                    fillcolor="rgba(239,68,68,0.15)",
                    name="드로다운",
                ))
                fig_dd.update_layout(
                    xaxis_title="시각",
                    yaxis_title="드로다운 (USDT)",
                    template="plotly_white",
                    height=250,
                    margin=dict(l=30, r=30, t=20, b=30),
                )
                st.plotly_chart(fig_dd, use_container_width=True)

    # TAB 3: Risk & Config
    with tab3:
        # Current Position Details (real-time from Bybit API)
        st.header("📍 현재 포지션")

        # Fetch position data (uses 10s cache from earlier call)
        position_data = fetch_position_data()

        if position_data is None:
            # API error or credentials missing
            st.warning("⚠️ 실시간 포지션 조회 실패 (API credentials 확인 필요)")
            st.info("환경변수 BYBIT_MAINNET_API_KEY, BYBIT_MAINNET_API_SECRET 설정 필요")

        elif float(position_data.get("size", "0") or "0") > 0:
            # Position exists
            side = position_data.get("side", "None")
            st.success(f"🟢 포지션 있음 ({side.upper()})")

            col_pos1, col_pos2, col_pos3, col_pos4 = st.columns(4)

            # Real-time values from Bybit API
            with col_pos1:
                entry_price = float(position_data.get("avgPrice", "0") or "0")
                st.metric(
                    "진입 가격",
                    f"${entry_price:,.2f}" if entry_price > 0 else "N/A",
                    help="평균 진입 가격 (Bybit API)"
                )

            with col_pos2:
                size = position_data.get("size", "0")
                st.metric(
                    "포지션 크기",
                    f"{float(size):.4f} BTC",
                    help="현재 포지션 크기 (Bybit API)"
                )

            with col_pos3:
                upnl = float(position_data.get("unrealisedPnl", "0") or "0")
                upnl_delta = "📈" if upnl > 0 else "📉" if upnl < 0 else ""
                st.metric(
                    "미실현 손익",
                    f"${upnl:.2f}",
                    delta=f"{upnl:.2f} USDT {upnl_delta}",
                    help="미실현 손익 (Bybit API)"
                )

            with col_pos4:
                stop_price = float(position_data.get("stopLoss", "0") or "0")
                st.metric(
                    "손절 가격",
                    f"${stop_price:,.2f}" if stop_price > 0 else "미설정",
                    help="손절 가격 (Bybit API)"
                )

            st.success("✅ 실시간 포지션 데이터 (Bybit API, 10초 캐시)")

        else:
            # FLAT (no position)
            st.info("⚪ FLAT (포지션 없음, 대기 중)")

        st.markdown("---")

        # System Configuration (Expander로 접기)
        with st.expander("⚙️ 시스템 설정", expanded=False):
            st.markdown("현재 거래 시스템 설정 및 리스크 파라미터")

            # Configuration cards (3 rows)
            # Row 1: Position Mode, Direction, Leverage
            col_cfg1, col_cfg2, col_cfg3 = st.columns(3)

            with col_cfg1:
                st.metric(
                    label="포지션 모드",
                    value="One-way Isolate",
                    help="격리 마진 모드, 단방향 거래"
                )

            with col_cfg2:
                st.metric(
                    label="거래 방향",
                    value="LONG",
                    help="매수 전용 (하락장 거래 금지)"
                )

            with col_cfg3:
                st.metric(
                    label="레버리지",
                    value="3x",
                    help="Stage 1/2: 3x, Stage 3: 2x (Equity 기준)"
                )

            # Row 2: Grid Strategy Parameters
            st.markdown("#### 그리드 전략 파라미터")
            col_grid1, col_grid2, col_grid3 = st.columns(3)

            with col_grid1:
                st.metric(
                    label="Stop Distance",
                    value="3%",
                    help="손절 거리 (Entry 대비)"
                )

            with col_grid2:
                st.metric(
                    label="Fee Rate",
                    value="0.01%",
                    help="Maker-only 전략 (Post-only)"
                )

            with col_grid3:
                st.metric(
                    label="EV Gate",
                    value="2.0x Fee",
                    help="예상 수익 >= 수수료 × 2.0 (Stage 1)"
                )

            # Row 3: Risk Limits
            st.markdown("#### 리스크 제한")
            col_risk1, col_risk2, col_risk3 = st.columns(3)

            with col_risk1:
                st.metric(
                    label="Per-Trade Loss Cap",
                    value="$10 (10%)",
                    help="Stage 1: $10 또는 Equity 10% 중 작은 값 (ADR-0014)"
                )

            with col_risk2:
                st.metric(
                    label="Daily Loss Cap",
                    value="5% Equity",
                    help="일일 손실 상한 (HALT 조건)"
                )

            with col_risk3:
                st.metric(
                    label="Weekly Loss Cap",
                    value="12.5% Equity",
                    help="주간 손실 상한 (7일 COOLDOWN)"
                )

            # Row 4: Entry Gates
            st.markdown("#### 진입 게이트")
            col_gate1, col_gate2, col_gate3 = st.columns(3)

            with col_gate1:
                st.metric(
                    label="ATR 최소",
                    value="> 2%",
                    help="Stage 1: ATR > 2% (변동성 필터)"
                )

            with col_gate2:
                st.metric(
                    label="Max Trades/Day",
                    value="10",
                    help="Stage 1 일일 최대 거래 횟수"
                )

            with col_gate3:
                st.metric(
                    label="Loss Streak Limit",
                    value="3연패 HALT",
                    help="3연패 시 당일 HALT, 5연패 시 72h COOLDOWN"
                )

        # Session Risk
        st.markdown("---")
        st.header("📉 세션 리스크")

        col_risk_left, col_risk_right = st.columns(2)

        with col_risk_left:
            fig_gauge = create_session_risk_gauge(
                daily_max_loss=risk_metrics["daily_max_loss"],
                threshold=-100.0  # 임계값 (조정 가능)
            )
            st.plotly_chart(fig_gauge, use_container_width=True)

        with col_risk_right:
            st.metric("Daily Max Loss", f"${risk_metrics['daily_max_loss']:.2f}")
            st.metric("Weekly Max Loss", f"${risk_metrics.get('weekly_max_loss', 0):.2f}")
            st.metric("Consecutive Losses", f"{risk_metrics.get('max_consecutive_losses', 0)}")

        # Regime Breakdown
        st.markdown("---")
        st.header("🌐 시장 상황별 분석")

        regime_df = calculate_regime_breakdown(df)
        regime_df_kr = regime_df.copy()
        regime_df_kr.columns = ["시장상황", "거래수", "승률", "총손익"]

        st.dataframe(
            regime_df_kr,
            use_container_width=True,
            hide_index=True,
        )

        # 시스템 상태 (거래 지표 기반)
        st.markdown("---")
        st.header("🖥️ 시스템 상태")

        _sys_risk = calculate_session_risk(df)
        _sys_summary = calculate_summary(df)

        sys_col1, sys_col2, sys_col3, sys_col4 = st.columns(4)

        with sys_col1:
            # 봇 상태: 연속손실 기반
            _streak = int(_sys_risk.get("max_loss_streak", 0))
            if _streak >= 5:
                _bot_status = "HALT (5연패)"
                _bot_delta = "72h cooldown"
            elif _streak >= 3:
                _bot_status = "WARN (3연패)"
                _bot_delta = "당일 주의"
            else:
                _bot_status = "정상"
                _bot_delta = f"연속손실 {_streak}회"
            st.metric("봇 헬스", _bot_status, delta=_bot_delta)

        with sys_col2:
            # 오늘 거래 수 / 한도
            _today_count = 0
            if "exit_time" in df.columns:
                _today_df = df.copy()
                _today_df["_exit_date"] = pd.to_datetime(
                    _today_df["exit_time"], unit="s", utc=True, errors="coerce"
                ).dt.date
                from datetime import date as _date_cls
                _today_count = int((_today_df["_exit_date"] == _date_cls.today()).sum())
            st.metric("오늘 거래 수", f"{_today_count} / 10", delta="일일 한도 10회")

        with sys_col3:
            st.metric("연속 손실", f"{_streak}회",
                      delta="HALT 기준 3연패" if _streak < 3 else "HALT 도달!")

        with sys_col4:
            _daily_loss = _sys_risk.get("daily_max_loss", 0.0)
            st.metric("일일 최대 손실", f"${_daily_loss:.2f}",
                      delta="한도: -5% Equity")

    # TAB 4: Diagnostics
    with tab4:
        st.header("⚡ 체결 품질")

        col_slippage, col_latency = st.columns(2)

        with col_slippage:
            st.subheader("슬리피지 통계")
            slippage = calculate_slippage_stats(df)
            st.json(slippage)

        with col_latency:
            st.subheader("레이턴시 통계")
            latency = calculate_latency_stats(df)
            st.json(latency)

        # 보유 시간 통계
        st.markdown("---")
        st.subheader("포지션 보유 시간")
        hold_stats_diag = calculate_hold_time_stats(df)
        if hold_stats_diag["valid_count"] > 0:
            h_col1, h_col2, h_col3 = st.columns(3)
            with h_col1:
                st.metric("평균 보유 시간",
                          f"{hold_stats_diag['mean_seconds'] / 60:.1f}분")
            with h_col2:
                st.metric("중앙값 보유 시간",
                          f"{hold_stats_diag['median_seconds'] / 60:.1f}분")
            with h_col3:
                st.metric("유효 레코드", hold_stats_diag["valid_count"])
        else:
            st.info("hold_seconds 데이터가 없습니다.")

    # TAB 5: 매매일지
    with tab5:
        st.header("📒 매매일지")
        log_path_journal = Path(log_dir)
        journal_df = load_journal_df(log_path_journal) if log_path_journal.exists() else pd.DataFrame()
        journal_stats = calculate_journal_stats(journal_df)

        # 요약 통계
        col_j1, col_j2, col_j3, col_j4 = st.columns(4)
        with col_j1:
            st.metric("총 거래", journal_stats["total_trades"])
        with col_j2:
            st.metric("승률", f"{journal_stats['win_rate'] * 100:.1f}%")
        with col_j3:
            st.metric("평균 PnL", f"${journal_stats['avg_pnl']:.2f}")
        with col_j4:
            st.metric("최대 손실", f"${journal_stats['max_loss']:.2f}")

        st.markdown("---")

        journal_data = create_journal_tab(journal_df)
        if journal_data["empty"]:
            st.info("거래 기록이 없습니다.")
        else:
            # 누적 PnL 차트
            if journal_data["cumulative_pnl"]:
                import plotly.graph_objects as _go
                fig_j = _go.Figure(
                    _go.Scatter(
                        y=journal_data["cumulative_pnl"],
                        mode="lines+markers",
                        name="누적 PnL",
                        line=dict(color="#00cec9", width=2),
                    )
                )
                fig_j.update_layout(
                    title="누적 PnL",
                    yaxis_title="PnL (USDT)",
                    template="plotly_white",
                    height=300,
                    margin=dict(l=40, r=40, t=40, b=40),
                )
                st.plotly_chart(fig_j, use_container_width=True)

            # 거래 테이블 (entry_time, exit_time, hold_seconds 컬럼 포함)
            _jdf_raw = load_all_trades(log_dir)
            if not _jdf_raw.empty:
                _cols_show = [c for c in [
                    "direction", "entry_price", "exit_price",
                    "qty_btc", "realized_pnl_usd", "fee_usd",
                    "entry_time", "exit_time", "hold_seconds", "market_regime",
                ] if c in _jdf_raw.columns]
                _jdf_display = _jdf_raw[_cols_show].copy()

                # entry_time, exit_time → 사람이 읽기 쉬운 형식
                for _ts_col in ("entry_time", "exit_time"):
                    if _ts_col in _jdf_display.columns:
                        _jdf_display[_ts_col] = pd.to_datetime(
                            _jdf_display[_ts_col], unit="s", utc=True, errors="coerce"
                        ).dt.strftime("%m/%d %H:%M")

                # hold_seconds null → "-"
                if "hold_seconds" in _jdf_display.columns:
                    _jdf_display["hold_seconds"] = _jdf_display["hold_seconds"].apply(
                        lambda x: f"{x:.0f}s" if pd.notna(x) else "-"
                    )

                # realized_pnl_usd 컬럼 색상 (st.dataframe에서 직접 지원 안 됨, 수치만 표시)
                _col_rename = {
                    "direction": "방향",
                    "entry_price": "진입가",
                    "exit_price": "청산가",
                    "qty_btc": "수량(BTC)",
                    "realized_pnl_usd": "PnL($)",
                    "fee_usd": "수수료",
                    "entry_time": "진입시각",
                    "exit_time": "청산시각",
                    "hold_seconds": "보유시간",
                    "market_regime": "시장",
                }
                _jdf_display = _jdf_display.rename(columns=_col_rename)
                st.dataframe(_jdf_display, use_container_width=True, hide_index=True)
            else:
                # fallback: 기존 journal_data 테이블
                table_df = pd.DataFrame(journal_data["table_data"])
                st.dataframe(table_df, use_container_width=True, hide_index=True)

    # --- Footer ---
    st.sidebar.markdown("---")

    from datetime import datetime
    last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    st.sidebar.info(
        f"📁 **{len(df)} trades** loaded\n\n"
        f"📅 **Date Range**\n"
        f"{get_date_range(df)[0]} ~ {get_date_range(df)[1]}\n\n"
        f"🕐 **Last Updated**\n"
        f"{last_updated}"
    )


if __name__ == "__main__":
    main()
