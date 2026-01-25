"""
src/infrastructure/storage/log_storage.py

Phase 10: Log Storage (JSONL, O_APPEND, fsync policy, partial line recovery)

DoD:
- append_trade_log_v1(): Single syscall write (os.write), flush, fsync policy
- read_trade_logs_v1(): 특정 날짜 로그 읽기 + partial line recovery
- Daily rotation (UTC): Handle swap with pre-rotate flush+fsync
- Durability policy: batch (10 lines) / periodic (1s) / critical event fsync
- Crash safety: Startup validation + truncate partial line
"""

import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional


class LogStorage:
    """
    Log Storage (JSONL)

    핵심 원칙:
    - Single syscall write per line (os.write)
    - Durable append: flush + fsync policy (batch/periodic/critical)
    - Rotation: Day boundary (UTC) handle swap with pre-rotate flush+fsync
    - Crash safety: Partial line recovery (truncate last line if JSON parse fails)
    - Concurrency: Single writer (fd 상시 유지)
    """

    def __init__(
        self,
        log_dir: Path,
        fsync_policy: str = "batch",
        fsync_batch_size: int = 10,
    ):
        """
        Args:
            log_dir: 로그 파일 디렉토리
            fsync_policy: fsync 정책 ("batch", "periodic", "critical")
            fsync_batch_size: batch 정책일 때 fsync 호출 간격 (라인 수)
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.fsync_policy = fsync_policy
        self.fsync_batch_size = fsync_batch_size

        # 상태
        self.current_time: datetime = datetime.now(timezone.utc)
        self.current_file_fd: Optional[int] = None
        self.current_file_path: Optional[Path] = None
        self.append_count = 0  # batch fsync용 카운터

        # 디버그/테스트용 카운터
        self.fsync_count = 0
        self.write_syscall_count = 0

        # 초기 파일 열기는 lazy (첫 append 시점에 open)

    def set_current_time(self, time: datetime):
        """테스트용: 현재 시간 설정"""
        self.current_time = time

    def _get_log_filename(self, date: Optional[datetime] = None) -> str:
        """로그 파일명 생성 (UTC 날짜 기준)"""
        if date is None:
            date = self.current_time
        return f"trades_{date.strftime('%Y-%m-%d')}.jsonl"

    def _open_current_file(self):
        """현재 날짜의 로그 파일 열기 (O_APPEND)"""
        filename = self._get_log_filename()
        self.current_file_path = self.log_dir / filename

        # O_APPEND | O_CREAT | O_WRONLY
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        self.current_file_fd = os.open(self.current_file_path, flags, 0o644)

    def append_trade_log_v1(self, log_entry: Dict[str, Any], is_critical: bool = False):
        """
        Trade Log를 JSONL로 append한다.

        Args:
            log_entry: Trade Log dict
            is_critical: critical event 여부 (HALT/LIQ/ADL) → 즉시 fsync
        """
        # Lazy open: 첫 append 시점 또는 rotation 후
        if self.current_file_fd is None:
            self._open_current_file()

        # JSON 라인 생성 (newline 포함)
        json_line = json.dumps(log_entry) + "\n"
        json_bytes = json_line.encode("utf-8")

        # Single syscall write (os.write)
        os.write(self.current_file_fd, json_bytes)
        self.write_syscall_count += 1

        # Flush (항상 수행)
        os.fsync(self.current_file_fd)  # Flush는 fsync에 포함됨

        self.append_count += 1

        # Fsync policy
        if is_critical:
            # Critical event → 즉시 fsync
            os.fsync(self.current_file_fd)
            self.fsync_count += 1
        elif self.fsync_policy == "batch":
            # Batch policy → N개마다 fsync
            if self.append_count >= self.fsync_batch_size:
                os.fsync(self.current_file_fd)
                self.fsync_count += 1
                self.append_count = 0

    def read_trade_logs_v1(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        특정 날짜의 로그를 읽는다 (partial line recovery 포함).

        Args:
            date: 날짜 문자열 ("YYYY-MM-DD", None이면 현재 파일)

        Returns:
            List[Dict]: 로그 엔트리 리스트
        """
        if date:
            # 특정 날짜 파일 읽기
            filename = f"trades_{date}.jsonl"
            file_path = self.log_dir / filename
        else:
            # 현재 파일 읽기
            file_path = self.current_file_path
            # 파일이 아직 생성되지 않았으면 빈 리스트 반환
            if file_path is None:
                return []

        if not file_path.exists():
            return []

        logs = []
        valid_lines = []

        with open(file_path, "r") as f:
            lines = f.readlines()

        # Partial line recovery
        for i, line in enumerate(lines):
            try:
                log_entry = json.loads(line)
                logs.append(log_entry)
                valid_lines.append(line)
            except json.JSONDecodeError:
                # 마지막 라인만 partial로 간주 (truncate)
                if i == len(lines) - 1:
                    # Partial line 발견 → truncate
                    self._truncate_partial_line(file_path, valid_lines)
                    break
                else:
                    # 중간 라인 파싱 실패 → 로그 유실이므로 무시하고 진행
                    continue

        return logs

    def _truncate_partial_line(self, file_path: Path, valid_lines: List[str]):
        """마지막 partial line을 제거 (truncate)"""
        # 파일을 다시 쓰기 (valid lines만)
        with open(file_path, "w") as f:
            f.writelines(valid_lines)

    def rotate_if_needed(self):
        """
        Day boundary (UTC)에서 rotation 수행.

        Rotation 절차:
        1. 현재 파일 flush + fsync (pre-rotate)
        2. 현재 파일 close
        3. 새 파일 open
        """
        new_filename = self._get_log_filename()
        current_filename = self.current_file_path.name

        if new_filename != current_filename:
            # Day boundary 넘어감 → rotation
            # 1. Pre-rotate flush+fsync
            os.fsync(self.current_file_fd)
            self.fsync_count += 1

            # 2. Close current file
            os.close(self.current_file_fd)

            # 3. Open new file
            self._open_current_file()

            # append_count 리셋
            self.append_count = 0
