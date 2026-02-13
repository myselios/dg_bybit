"""
test_trade_analyzer.py

Phase 13a: TradeAnalyzer 단위 테스트
- Trade log 로드
- 성과 지표 계산
- JSONL 파싱
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import pytest

from src.analysis.trade_analyzer import (
    TradeAnalyzer,
    PerformanceMetrics,
    MetricsBreakdown,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_log_dir():
    """임시 로그 디렉토리 생성"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_trades():
    """샘플 거래 데이터"""
    return [
        {
            "order_id": "order_1",
            "fills": [{"price": 50000, "qty": 100, "fee": 0.5}],
            "pnl": 100.0,
            "timestamp": "2026-01-20T10:00:00Z",
            "market_regime": "RANGING",
            "holding_time_seconds": 3600,
            "slippage_usd": 2.0,
        },
        {
            "order_id": "order_2",
            "fills": [{"price": 51000, "qty": 100, "fee": 0.5}],
            "pnl": -50.0,
            "timestamp": "2026-01-20T11:00:00Z",
            "market_regime": "TRENDING_UP",
            "holding_time_seconds": 1800,
            "slippage_usd": 1.5,
        },
        {
            "order_id": "order_3",
            "fills": [{"price": 49000, "qty": 100, "fee": 0.5}],
            "pnl": 200.0,
            "timestamp": "2026-01-20T12:00:00Z",
            "market_regime": "RANGING",
            "holding_time_seconds": 7200,
            "slippage_usd": 3.0,
        },
    ]


# ============================================================================
# Test Cases
# ============================================================================

def test_init_valid_log_dir(temp_log_dir):
    """정상: 유효한 로그 디렉토리로 TradeAnalyzer 초기화"""
    analyzer = TradeAnalyzer(log_dir=str(temp_log_dir))
    assert analyzer.log_dir == temp_log_dir


def test_init_nonexistent_dir_raises_error():
    """오류: 존재하지 않는 디렉토리로 초기화 시 FileNotFoundError"""
    with pytest.raises(FileNotFoundError, match="Log directory not found"):
        TradeAnalyzer(log_dir="/nonexistent/path/to/logs")


def test_load_trades_empty_period(temp_log_dir):
    """정상: 거래가 없는 기간 로드 → 빈 리스트 반환"""
    analyzer = TradeAnalyzer(log_dir=str(temp_log_dir))
    trades = analyzer.load_trades("2026-01-01", "2026-01-05")
    assert trades == []


def test_load_trades_single_day(temp_log_dir, sample_trades):
    """정상: 단일 날짜 JSONL 파일 로드"""
    # JSONL 파일 생성
    log_file = temp_log_dir / "trades_2026-01-20.jsonl"
    with open(log_file, 'w') as f:
        for trade in sample_trades:
            f.write(json.dumps(trade) + '\n')

    analyzer = TradeAnalyzer(log_dir=str(temp_log_dir))
    trades = analyzer.load_trades("2026-01-20", "2026-01-20")

    assert len(trades) == 3
    assert trades[0]["order_id"] == "order_1"
    assert trades[1]["pnl"] == -50.0
    assert trades[2]["market_regime"] == "RANGING"


def test_load_trades_multiple_days(temp_log_dir):
    """정상: 여러 날짜 JSONL 파일 로드"""
    # 2일간 거래 생성
    for day in [20, 21]:
        log_file = temp_log_dir / f"trades_2026-01-{day}.jsonl"
        with open(log_file, 'w') as f:
            f.write(json.dumps({"order_id": f"order_{day}", "pnl": 50.0}) + '\n')

    analyzer = TradeAnalyzer(log_dir=str(temp_log_dir))
    trades = analyzer.load_trades("2026-01-20", "2026-01-21")

    assert len(trades) == 2
    assert trades[0]["order_id"] == "order_20"
    assert trades[1]["order_id"] == "order_21"


def test_load_jsonl_invalid_json_warning(temp_log_dir, capsys):
    """경고: 잘못된 JSON 라인은 경고 출력 후 스킵"""
    log_file = temp_log_dir / "trades_2026-01-20.jsonl"
    with open(log_file, 'w') as f:
        f.write('{"order_id": "order_1", "pnl": 100.0}\n')
        f.write('{"invalid json\n')  # 잘못된 JSON
        f.write('{"order_id": "order_2", "pnl": 50.0}\n')

    analyzer = TradeAnalyzer(log_dir=str(temp_log_dir))
    trades = analyzer.load_trades("2026-01-20", "2026-01-20")

    # 경고 출력 확인
    captured = capsys.readouterr()
    assert "Warning: Invalid JSON" in captured.out

    # 유효한 거래만 로드
    assert len(trades) == 2
    assert trades[0]["order_id"] == "order_1"
    assert trades[1]["order_id"] == "order_2"


def test_calculate_metrics_basic(sample_trades):
    """정상: 기본 성과 지표 계산"""
    # 임시 디렉토리 생성 후 분석기 초기화
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        log_file = log_dir / "trades_2026-01-20.jsonl"
        with open(log_file, 'w') as f:
            for trade in sample_trades:
                f.write(json.dumps(trade) + '\n')

        analyzer = TradeAnalyzer(log_dir=str(log_dir))
        trades = analyzer.load_trades("2026-01-20", "2026-01-20")
        metrics = analyzer.calculate_metrics(trades)

        # 기본 지표 검증
        assert metrics.total_trades == 3
        assert metrics.win_count == 2
        assert metrics.loss_count == 1
        assert metrics.winrate == pytest.approx(2 / 3, abs=0.01)

        # PnL 지표 검증
        assert metrics.total_pnl == 250.0  # 100 - 50 + 200
        assert metrics.avg_pnl_per_trade == pytest.approx(250.0 / 3, abs=0.01)
        assert metrics.max_single_win == 200.0
        assert metrics.max_single_loss == -50.0

        # 운영 지표 검증
        assert metrics.avg_holding_time_seconds == pytest.approx((3600 + 1800 + 7200) / 3, abs=1)
        assert metrics.avg_slippage_usd == pytest.approx((2.0 + 1.5 + 3.0) / 3, abs=0.01)
        assert metrics.total_fees_usd == pytest.approx(0.5 * 3, abs=0.01)


def test_calculate_metrics_empty_trades():
    """경계: 거래가 없을 때 계산 → 모든 지표 0 또는 None"""
    with tempfile.TemporaryDirectory() as tmpdir:
        analyzer = TradeAnalyzer(log_dir=str(tmpdir))
        metrics = analyzer.calculate_metrics([])

        assert metrics.total_trades == 0
        assert metrics.win_count == 0
        assert metrics.loss_count == 0
        assert metrics.winrate == 0.0
        assert metrics.total_pnl == 0.0
        assert metrics.sharpe_ratio is None  # std=0이면 None
        assert metrics.sortino_ratio is None


def test_calculate_pnl_from_trade():
    """정상: 개별 거래에서 PnL 추출"""
    with tempfile.TemporaryDirectory() as tmpdir:
        analyzer = TradeAnalyzer(log_dir=str(tmpdir))

        # pnl 필드가 있는 경우
        trade_with_pnl = {"order_id": "order_1", "pnl": 123.45}
        assert analyzer._calculate_pnl(trade_with_pnl) == 123.45

        # pnl 필드가 없는 경우
        trade_without_pnl = {"order_id": "order_2"}
        assert analyzer._calculate_pnl(trade_without_pnl) == 0.0
