"""resolve_git_commit 단위 테스트 (배포 신뢰성).

핵심 계약:
  1. 이미지에 구워진 BUILD_COMMIT 파일이 최우선이다.
  2. 파일이 있으면 낡은 GIT_COMMIT 환경변수가 이를 덮어쓰지 못한다.
  3. 파일이 없으면 명시적 환경변수를 쓴다.
  4. 신뢰할 소스가 없으면 "unknown" (낡은 값 추측 금지).
"""

from pathlib import Path

from infrastructure.version import resolve_git_commit


def _write(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def test_baked_file_is_used(tmp_path: Path) -> None:
    build_file = _write(tmp_path / "BUILD_COMMIT", "abc1234")
    assert resolve_git_commit(build_commit_file=build_file, env_value=None) == "abc1234"


def test_baked_file_wins_over_stale_env(tmp_path: Path) -> None:
    # 파일(신코드) 이 낡은 .env 값(dfc5135) 을 반드시 이긴다 — 회귀 방지.
    build_file = _write(tmp_path / "BUILD_COMMIT", "newc0de")
    assert (
        resolve_git_commit(build_commit_file=build_file, env_value="dfc5135")
        == "newc0de"
    )


def test_env_used_when_file_absent(tmp_path: Path) -> None:
    missing = tmp_path / "BUILD_COMMIT"  # 생성하지 않음
    assert resolve_git_commit(build_commit_file=missing, env_value="ef56789") == "ef56789"


def test_unknown_when_no_source(tmp_path: Path) -> None:
    missing = tmp_path / "BUILD_COMMIT"
    assert resolve_git_commit(build_commit_file=missing, env_value=None) == "unknown"


def test_empty_env_treated_as_unknown(tmp_path: Path) -> None:
    missing = tmp_path / "BUILD_COMMIT"
    assert resolve_git_commit(build_commit_file=missing, env_value="   ") == "unknown"


def test_literal_unknown_env_ignored(tmp_path: Path) -> None:
    missing = tmp_path / "BUILD_COMMIT"
    assert resolve_git_commit(build_commit_file=missing, env_value="unknown") == "unknown"


def test_blank_baked_file_falls_back_to_env(tmp_path: Path) -> None:
    # 빌드 arg 가 비어있어 파일이 공백이면 파일을 무시하고 env 로 폴백.
    build_file = _write(tmp_path / "BUILD_COMMIT", "\n")
    assert resolve_git_commit(build_commit_file=build_file, env_value="aa11bb2") == "aa11bb2"


def test_baked_file_whitespace_is_stripped(tmp_path: Path) -> None:
    build_file = _write(tmp_path / "BUILD_COMMIT", "  cd34ef5\n")
    assert resolve_git_commit(build_commit_file=build_file, env_value=None) == "cd34ef5"
