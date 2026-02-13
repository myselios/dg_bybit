"""
src/dashboard/file_watcher.py

Phase 14a (Dashboard) Phase 4: 파일 감시 유틸리티

DoD:
- 디렉토리 내 최신 수정 시간 추출
- 변경 감지 (새 파일 추가 / 기존 파일 수정)
- Streamlit 친화적인 polling 방식
"""

from pathlib import Path
from typing import Optional


def get_latest_modification_time(
    directory: Path,
    pattern: str = "*.log"
) -> Optional[float]:
    """
    디렉토리 내 최신 수정 시간 추출

    Args:
        directory: 감시할 디렉토리
        pattern: 파일 패턴 (기본: *.log)

    Returns:
        Optional[float]: 최신 수정 시간 (Unix timestamp), 파일 없으면 None
    """
    if not directory.exists():
        return None

    # 패턴에 맞는 모든 파일 찾기
    log_files = list(directory.glob(pattern))
    jsonl_files = list(directory.glob(pattern.replace(".log", ".jsonl")))
    all_files = log_files + jsonl_files

    if not all_files:
        return None

    # 가장 최근 수정 시간 반환
    latest_time = max(f.stat().st_mtime for f in all_files)
    return latest_time


def has_directory_changed(
    directory: Path,
    last_check_time: Optional[float],
    pattern: str = "*.log"
) -> bool:
    """
    디렉토리 변경 감지

    Args:
        directory: 감시할 디렉토리
        last_check_time: 마지막 확인 시간 (Unix timestamp)
        pattern: 파일 패턴 (기본: *.log)

    Returns:
        bool: 변경 발생 시 True
    """
    if last_check_time is None:
        # 처음 확인하는 경우 → 변경 없음으로 간주
        return False

    current_time = get_latest_modification_time(directory, pattern)

    if current_time is None:
        # 파일이 없으면 변경 없음
        return False

    # 최신 수정 시간이 마지막 확인 시간보다 나중이면 변경됨
    return current_time > last_check_time
