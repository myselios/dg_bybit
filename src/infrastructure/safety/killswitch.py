"""
src/infrastructure/safety/killswitch.py
Kill Switch — Manual halt mechanism

Purpose:
- Manual halt: touch .halt → 즉시 HALT
- Manual reset only

SSOT:
- config/safety_limits.yaml: killswitch.manual_halt_file
- task_plan.md Phase 9c: 기존 안전장치

Exports:
- KillSwitch: Manual halt checker
"""

import os


class KillSwitch:
    """
    Kill Switch — Manual halt mechanism

    Usage:
        # Manual halt
        touch .halt

        # Reset
        rm .halt
    """

    def __init__(self, halt_file: str = ".halt"):
        """
        Kill Switch 초기화

        Args:
            halt_file: Manual halt 파일 경로 (default: .halt)
        """
        self.halt_file = halt_file

    def is_halted(self) -> bool:
        """
        Manual halt 상태 확인

        Returns:
            True if .halt file exists, False otherwise
        """
        return os.path.exists(self.halt_file)

    def halt(self) -> None:
        """
        Manual halt 활성화 (touch .halt)
        """
        with open(self.halt_file, "w") as f:
            f.write("manual_halt\n")

    def reset(self) -> None:
        """
        Manual halt 해제 (rm .halt)
        """
        if os.path.exists(self.halt_file):
            os.remove(self.halt_file)
