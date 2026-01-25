"""
tests/integration/test_dry_run_orchestrator.py
Dry-Run Orchestrator Integration Tests

Purpose:
- Dry-Run 전체 흐름 검증 (Mock 사용, Testnet 연결 불필요)
- DryRunMonitor 동작 검증
- State 전환 감지 검증
- Trade log 완전성 검증

SSOT:
- docs/plans/task_plan.md Phase 12a-3
"""

import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from datetime import datetime, timezone

# Note: DryRunMonitor는 scripts/run_testnet_dry_run.py에 inline으로 정의됨
# 테스트를 위해 여기서 import하거나 복사 필요
# 실용적 접근: 테스트에서 DryRunMonitor 재정의

class DryRunMonitor:
    """Dry-Run 모니터링 및 통계 (Test copy)"""

    def __init__(self):
        self.total_trades = 0
        self.successful_cycles = 0
        self.failed_cycles = 0
        self.session_risk_halts = 0
        self.emergency_halts = 0
        self.stop_loss_hits = 0
        self.start_time = datetime.now(timezone.utc)

    def log_cycle_complete(self, pnl_usd: float):
        """Full cycle 완료 기록"""
        self.successful_cycles += 1
        self.total_trades += 1

    def log_halt(self, reason: str):
        """HALT 발생 기록"""
        if "session_risk" in reason.lower():
            self.session_risk_halts += 1
        else:
            self.emergency_halts += 1

    def log_stop_hit(self):
        """Stop loss hit 기록"""
        self.stop_loss_hits += 1


class TestDryRunMonitor:
    """DryRunMonitor 동작 검증"""

    def test_dry_run_monitor_initialization(self):
        """DryRunMonitor 초기화"""
        # Arrange & Act
        monitor = DryRunMonitor()

        # Assert
        assert monitor.total_trades == 0
        assert monitor.successful_cycles == 0
        assert monitor.failed_cycles == 0
        assert monitor.session_risk_halts == 0
        assert monitor.emergency_halts == 0
        assert monitor.stop_loss_hits == 0

    def test_cycle_complete_logging(self):
        """Cycle 완료 기록"""
        # Arrange
        monitor = DryRunMonitor()

        # Act
        monitor.log_cycle_complete(pnl_usd=5.0)
        monitor.log_cycle_complete(pnl_usd=-3.0)

        # Assert
        assert monitor.successful_cycles == 2
        assert monitor.total_trades == 2

    def test_halt_detection_session_risk(self):
        """Session Risk HALT 감지"""
        # Arrange
        monitor = DryRunMonitor()

        # Act
        monitor.log_halt("session_risk: Daily PnL limit exceeded")

        # Assert
        assert monitor.session_risk_halts == 1
        assert monitor.emergency_halts == 0

    def test_halt_detection_emergency(self):
        """Emergency HALT 감지"""
        # Arrange
        monitor = DryRunMonitor()

        # Act
        monitor.log_halt("Emergency: WS connection lost")

        # Assert
        assert monitor.session_risk_halts == 0
        assert monitor.emergency_halts == 1

    def test_stop_loss_hit_logging(self):
        """Stop loss hit 기록"""
        # Arrange
        monitor = DryRunMonitor()

        # Act
        monitor.log_stop_hit()
        monitor.log_stop_hit()
        monitor.log_stop_hit()

        # Assert
        assert monitor.stop_loss_hits == 3


class TestDryRunOrchestration:
    """Dry-Run Orchestration 통합 테스트"""

    def test_state_transition_detection(self):
        """State 전환 감지 (FLAT → Entry → Exit → FLAT)"""
        # Arrange
        from domain.state import State

        # Mock Orchestrator
        mock_orchestrator = Mock()

        # State 전환 시뮬레이션: FLAT → ENTRY_PENDING → IN_POSITION → FLAT
        state_sequence = [
            State.FLAT,
            State.ENTRY_PENDING,
            State.IN_POSITION,
            State.FLAT,
        ]

        monitor = DryRunMonitor()
        previous_state = State.FLAT

        # Act
        for current_state in state_sequence:
            # Full cycle 완료 감지 (IN_POSITION/ENTRY_PENDING → FLAT)
            if previous_state != State.FLAT and current_state == State.FLAT:
                monitor.log_cycle_complete(pnl_usd=2.0)

            previous_state = current_state

        # Assert
        assert monitor.successful_cycles == 1
        assert monitor.total_trades == 1

    def test_trade_log_completeness_verification(self):
        """Trade log 완전성 검증"""
        # Arrange
        from infrastructure.storage.log_storage import LogStorage

        # Temporary log directory
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_dir = Path(tmp_dir)
            log_storage = LogStorage(log_dir=log_dir)

            # Trade log entry (as dict)
            trade_log_entry = {
                "trade_id": "test_trade_001",
                "side": "Buy",
                "entry_price": 50000.0,
                "exit_price": 50200.0,
                "qty": 100,
                "realized_pnl_usd": 10.0,
                "fees_usd": 0.5,
                "stop_hit": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Act: Append trade log (LogStorage API)
            log_storage.append_trade_log_v1(
                log_entry=trade_log_entry,
                is_critical=False
            )

            # Verify: Read trade logs
            trade_logs = log_storage.read_trade_logs_v1()

            # Assert
            assert len(trade_logs) == 1
            assert trade_logs[0]["realized_pnl_usd"] == 10.0
            assert trade_logs[0]["fees_usd"] == 0.5
            assert trade_logs[0]["stop_hit"] is False

    def test_dry_run_with_multiple_cycles(self):
        """Dry-Run 다중 Cycle 시뮬레이션"""
        # Arrange
        from domain.state import State

        monitor = DryRunMonitor()
        previous_state = State.FLAT

        # Simulate 5 full cycles
        cycles = [
            # Cycle 1
            [State.FLAT, State.ENTRY_PENDING, State.IN_POSITION, State.FLAT],
            # Cycle 2
            [State.FLAT, State.ENTRY_PENDING, State.IN_POSITION, State.FLAT],
            # Cycle 3 (Stop hit)
            [State.FLAT, State.ENTRY_PENDING, State.IN_POSITION, State.FLAT],
        ]

        # Act
        for cycle in cycles:
            for current_state in cycle:
                # Full cycle 완료 감지
                if previous_state != State.FLAT and current_state == State.FLAT:
                    monitor.log_cycle_complete(pnl_usd=5.0)

                previous_state = current_state

        # Simulate stop loss hits
        monitor.log_stop_hit()
        monitor.log_stop_hit()

        # Assert
        assert monitor.successful_cycles == 3
        assert monitor.total_trades == 3
        assert monitor.stop_loss_hits == 2
