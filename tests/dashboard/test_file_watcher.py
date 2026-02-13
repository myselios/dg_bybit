"""
tests/dashboard/test_file_watcher.py

Phase 14a (Dashboard) Phase 4: File Watcher 테스트

TDD RED Phase: 파일 감시 테스트 먼저 작성
"""

import pytest
from pathlib import Path
import time
import tempfile
from src.dashboard.file_watcher import (
    get_latest_modification_time,
    has_directory_changed,
)


# Test 1: 최신 수정 시간 추출
def test_get_latest_modification_time():
    """
    디렉토리 내 최신 수정 시간 추출

    Given: 여러 파일이 있는 디렉토리
    When: get_latest_modification_time() 호출
    Then: 가장 최근 수정된 파일의 timestamp 반환
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # 파일 3개 생성 (시간차를 두고)
        file1 = tmp_path / "old.log"
        file1.write_text("old data")
        time.sleep(0.1)

        file2 = tmp_path / "middle.log"
        file2.write_text("middle data")
        time.sleep(0.1)

        file3 = tmp_path / "new.log"
        file3.write_text("new data")

        # Act: 최신 수정 시간 가져오기
        latest_time = get_latest_modification_time(tmp_path, pattern="*.log")

        # Assert: file3의 수정 시간과 같아야 함
        assert latest_time is not None
        assert latest_time == file3.stat().st_mtime


# Test 2: 빈 디렉토리 처리
def test_get_latest_modification_time_empty_directory():
    """
    빈 디렉토리 처리

    Given: 빈 디렉토리
    When: get_latest_modification_time() 호출
    Then: None 반환
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Act
        latest_time = get_latest_modification_time(tmp_path, pattern="*.log")

        # Assert: 빈 디렉토리 → None
        assert latest_time is None


# Test 3: 디렉토리 변경 감지 (새 파일 추가)
def test_has_directory_changed_new_file():
    """
    새 파일 추가 감지

    Given: 디렉토리에 파일 1개 존재
    When: 새 파일 추가
    Then: has_directory_changed() → True
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Setup: 초기 파일 생성
        file1 = tmp_path / "initial.log"
        file1.write_text("initial data")

        # 초기 상태 기록
        initial_time = get_latest_modification_time(tmp_path, pattern="*.log")
        time.sleep(0.1)

        # Act: 새 파일 추가
        file2 = tmp_path / "new.log"
        file2.write_text("new data")

        # Assert: 변경 감지
        assert has_directory_changed(tmp_path, initial_time, pattern="*.log") is True


# Test 4: 디렉토리 변경 감지 (기존 파일 수정)
def test_has_directory_changed_file_modified():
    """
    기존 파일 수정 감지

    Given: 디렉토리에 파일 1개 존재
    When: 기존 파일 수정
    Then: has_directory_changed() → True
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Setup: 초기 파일 생성
        file1 = tmp_path / "data.log"
        file1.write_text("initial data")

        # 초기 상태 기록
        initial_time = get_latest_modification_time(tmp_path, pattern="*.log")
        time.sleep(0.1)

        # Act: 파일 수정 (append)
        with open(file1, "a") as f:
            f.write("\nnew line")

        # Assert: 변경 감지
        assert has_directory_changed(tmp_path, initial_time, pattern="*.log") is True


# Test 5: 변경 없음
def test_has_directory_changed_no_change():
    """
    변경 없음 감지

    Given: 디렉토리에 파일 1개 존재
    When: 아무 변경 없음
    Then: has_directory_changed() → False
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Setup: 초기 파일 생성
        file1 = tmp_path / "data.log"
        file1.write_text("initial data")

        # 초기 상태 기록
        initial_time = get_latest_modification_time(tmp_path, pattern="*.log")

        # Act: 변경 없음
        # (아무것도 하지 않음)

        # Assert: 변경 감지되지 않음
        assert has_directory_changed(tmp_path, initial_time, pattern="*.log") is False
