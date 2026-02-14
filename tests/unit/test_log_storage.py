"""
tests/unit/test_log_storage.py

Phase 10: Log Storage 테스트 (JSONL, O_APPEND, fsync policy, partial line recovery)

DoD:
- append_trade_log_v1(): Single syscall write, flush, fsync policy (batch/periodic/critical)
- read_trade_logs_v1(): 특정 날짜 로그 읽기 + partial line recovery
- Daily rotation (UTC): Handle swap with pre-rotate flush+fsync
- Durability policy: batch (10 lines) / periodic (1s) / critical event fsync
- Crash safety: Startup validation + truncate partial line

Failure-mode tests:
- rotation boundary line 누락 방지
- partial line recovery (마지막 라인 JSON parse 실패 시 truncate)
- fsync policy (batch/periodic/critical)
- single syscall write 검증
"""

import pytest
import os
import json
import shutil
from pathlib import Path


@pytest.fixture
def temp_log_dir():
    """
    임시 로그 디렉토리 생성 (Codex Review Fix #4)

    tempfile.TemporaryDirectory 대신 로컬 디렉터리 사용
    (환경 제약으로 temp 디렉터리 접근 불가)
    """
    # 로컬 temp 디렉터리 사용
    tmpdir = Path("./logs/test_temp")
    tmpdir.mkdir(parents=True, exist_ok=True)

    yield tmpdir

    # Cleanup
    if tmpdir.exists():
        shutil.rmtree(tmpdir)


# Test 1: append_trade_log_v1() - 기본 append 동작
def test_log_storage_append_basic(temp_log_dir):
    """
    append_trade_log_v1()이 JSONL 형식으로 로그를 append한다.
    """
    from src.infrastructure.storage.log_storage import LogStorage

    storage = LogStorage(log_dir=temp_log_dir)
    log_entry = {
        "order_id": "test_123",
        "market_regime": "ranging",
        "schema_version": "1.0",
    }

    storage.append_trade_log_v1(log_entry)

    # 파일이 생성되었는지 확인
    log_files = list(temp_log_dir.glob("*.jsonl"))
    assert len(log_files) == 1

    # 내용 확인
    with open(log_files[0], "r") as f:
        lines = f.readlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["order_id"] == "test_123"


# Test 2: partial line recovery - 마지막 라인이 잘렸을 때 truncate
def test_log_storage_partial_line_recovery(temp_log_dir):
    """
    Failure-mode test: 마지막 라인이 JSON parse 실패하면 truncate
    """
    from src.infrastructure.storage.log_storage import LogStorage

    storage = LogStorage(log_dir=temp_log_dir)

    # 정상 로그 2개 append
    storage.append_trade_log_v1({"order_id": "log1", "schema_version": "1.0"})
    storage.append_trade_log_v1({"order_id": "log2", "schema_version": "1.0"})

    # 파일에 직접 partial line 추가 (JSON parse 실패)
    log_file = list(temp_log_dir.glob("*.jsonl"))[0]
    with open(log_file, "a") as f:
        f.write('{"order_id": "partial_line"')  # 중간에 잘림

    # read_trade_logs_v1() 호출 → partial line 복구 (truncate)
    logs = storage.read_trade_logs_v1()

    # 정상 로그 2개만 읽혀야 함 (partial line은 truncate됨)
    assert len(logs) == 2
    assert logs[0]["order_id"] == "log1"
    assert logs[1]["order_id"] == "log2"

    # 파일 내용 확인 (partial line이 제거되었는지)
    with open(log_file, "r") as f:
        lines = f.readlines()
        assert len(lines) == 2  # partial line 제거됨


# Test 3: fsync policy - batch (10 lines)
def test_log_storage_fsync_policy_batch(temp_log_dir):
    """
    Fsync policy: batch (10 lines) - 10개마다 fsync 호출
    """
    from src.infrastructure.storage.log_storage import LogStorage

    storage = LogStorage(log_dir=temp_log_dir, fsync_policy="batch", fsync_batch_size=10)

    # 9개 append (fsync 아직 호출 안 됨)
    for i in range(9):
        storage.append_trade_log_v1({"order_id": f"log{i}", "schema_version": "1.0"})

    # fsync 카운트 확인 (0이어야 함)
    assert storage.fsync_count == 0

    # 10개째 append → fsync 호출
    storage.append_trade_log_v1({"order_id": "log9", "schema_version": "1.0"})
    assert storage.fsync_count == 1

    # 15개째 append → fsync 호출 안 됨 (다음 batch는 20개)
    for i in range(10, 15):
        storage.append_trade_log_v1({"order_id": f"log{i}", "schema_version": "1.0"})
    assert storage.fsync_count == 1


# Test 4: fsync policy - critical event (HALT/LIQ/ADL)
def test_log_storage_fsync_policy_critical_event(temp_log_dir):
    """
    Fsync policy: critical event - HALT/LIQ/ADL 이벤트는 즉시 fsync
    """
    from src.infrastructure.storage.log_storage import LogStorage

    storage = LogStorage(log_dir=temp_log_dir, fsync_policy="batch", fsync_batch_size=10)

    # 일반 로그 5개 (fsync 아직 호출 안 됨)
    for i in range(5):
        storage.append_trade_log_v1({"order_id": f"log{i}", "schema_version": "1.0"})
    assert storage.fsync_count == 0

    # Critical event (HALT) → 즉시 fsync
    storage.append_trade_log_v1(
        {"order_id": "halt_log", "event_type": "HALT", "schema_version": "1.0"},
        is_critical=True,
    )
    assert storage.fsync_count == 1


# Test 5: rotation boundary - line 누락 방지
def test_log_storage_rotation_boundary_no_line_loss(temp_log_dir):
    """
    Failure-mode test: rotation boundary에서 line이 누락되지 않아야 한다.
    """
    from src.infrastructure.storage.log_storage import LogStorage
    from datetime import datetime, timezone

    storage = LogStorage(log_dir=temp_log_dir)

    # Day 1 로그 10개
    day1 = datetime(2026, 1, 24, 23, 59, 50, tzinfo=timezone.utc)
    storage.set_current_time(day1)
    for i in range(10):
        storage.append_trade_log_v1({"order_id": f"day1_log{i}", "schema_version": "1.0"})

    # Day 2로 rotation (UTC 00:00:00)
    day2 = datetime(2026, 1, 25, 0, 0, 0, tzinfo=timezone.utc)
    storage.set_current_time(day2)
    storage.rotate_if_needed()

    # Day 2 로그 5개
    for i in range(5):
        storage.append_trade_log_v1({"order_id": f"day2_log{i}", "schema_version": "1.0"})

    # Day 1 로그 파일 확인 (10개 모두 있어야 함)
    day1_file = temp_log_dir / "trades_2026-01-24.jsonl"
    with open(day1_file, "r") as f:
        lines = f.readlines()
        assert len(lines) == 10

    # Day 2 로그 파일 확인 (5개)
    day2_file = temp_log_dir / "trades_2026-01-25.jsonl"
    with open(day2_file, "r") as f:
        lines = f.readlines()
        assert len(lines) == 5


# Test 6: single syscall write 검증
def test_log_storage_single_syscall_write(temp_log_dir):
    """
    Failure-mode test: append는 single syscall write (os.write)로 수행되어야 한다.
    """
    from src.infrastructure.storage.log_storage import LogStorage

    storage = LogStorage(log_dir=temp_log_dir)

    # append 호출
    log_entry = {"order_id": "test_123", "schema_version": "1.0"}
    storage.append_trade_log_v1(log_entry)

    # write_count 검증 (1회만 호출되어야 함)
    assert storage.write_syscall_count == 1


# Test 7: read_trade_logs_v1() - 특정 날짜 로그 읽기
def test_log_storage_read_specific_date(temp_log_dir):
    """
    read_trade_logs_v1(date)은 특정 날짜의 로그만 읽어야 한다.
    """
    from src.infrastructure.storage.log_storage import LogStorage
    from datetime import datetime, timezone

    storage = LogStorage(log_dir=temp_log_dir)

    # Day 1 로그 3개
    day1 = datetime(2026, 1, 24, 12, 0, 0, tzinfo=timezone.utc)
    storage.set_current_time(day1)
    for i in range(3):
        storage.append_trade_log_v1({"order_id": f"day1_log{i}", "schema_version": "1.0"})

    # Day 2로 rotation
    day2 = datetime(2026, 1, 25, 0, 0, 0, tzinfo=timezone.utc)
    storage.set_current_time(day2)
    storage.rotate_if_needed()

    # Day 2 로그 2개
    for i in range(2):
        storage.append_trade_log_v1({"order_id": f"day2_log{i}", "schema_version": "1.0"})

    # Day 1 로그만 읽기
    day1_logs = storage.read_trade_logs_v1(date="2026-01-24")
    assert len(day1_logs) == 3
    assert all("day1_log" in log["order_id"] for log in day1_logs)

    # Day 2 로그만 읽기
    day2_logs = storage.read_trade_logs_v1(date="2026-01-25")
    assert len(day2_logs) == 2
    assert all("day2_log" in log["order_id"] for log in day2_logs)


# Test 8: pre-rotate flush+fsync
def test_log_storage_pre_rotate_flush_and_fsync(temp_log_dir):
    """
    Rotation 전에 flush + fsync가 호출되어야 한다.
    """
    from src.infrastructure.storage.log_storage import LogStorage
    from datetime import datetime, timezone

    storage = LogStorage(log_dir=temp_log_dir, fsync_policy="batch", fsync_batch_size=100)

    # Day 1 로그 5개 (batch size 미만이므로 fsync 호출 안 됨)
    day1 = datetime(2026, 1, 24, 23, 59, 50, tzinfo=timezone.utc)
    storage.set_current_time(day1)
    for i in range(5):
        storage.append_trade_log_v1({"order_id": f"day1_log{i}", "schema_version": "1.0"})

    assert storage.fsync_count == 0

    # Day 2로 rotation → pre-rotate flush+fsync 호출되어야 함
    day2 = datetime(2026, 1, 25, 0, 0, 0, tzinfo=timezone.utc)
    storage.set_current_time(day2)
    storage.rotate_if_needed()

    # fsync가 1회 호출되었는지 확인 (pre-rotate flush+fsync)
    assert storage.fsync_count == 1

    # Day 1 파일 모든 라인이 기록되었는지 확인
    day1_file = temp_log_dir / "trades_2026-01-24.jsonl"
    with open(day1_file, "r") as f:
        lines = f.readlines()
        assert len(lines) == 5


# ========== P1-7: rotate_if_needed NoneType 방어 ==========


def test_rotate_if_needed_handles_none_path():
    """
    P1-7: current_file_path가 None일 때 rotate_if_needed()가 AttributeError 없이 동작
    lazy open 전에 rotate가 호출되는 경우 방어
    """
    import tempfile
    from infrastructure.storage.log_storage import LogStorage
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = LogStorage(log_dir=Path(tmpdir))

        # 초기 상태: current_file_path=None, current_file_fd=None
        assert storage.current_file_path is None
        assert storage.current_file_fd is None

        # rotate_if_needed()가 에러 없이 실행되어야 함 (lazy open 수행)
        storage.rotate_if_needed()

        # lazy open이 수행되어 파일이 열려야 함
        assert storage.current_file_path is not None
        assert storage.current_file_fd is not None
