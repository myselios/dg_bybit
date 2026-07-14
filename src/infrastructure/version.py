"""Git commit resolution for trade-log code-version tracking.

배포 신뢰성: 트레이드 로그의 git_commit은 반드시 "실제로 실행 중인 이미지에
구워진(baked) 커밋"을 가리켜야 한다. 과거에는 .env의 수동 GIT_COMMIT 값을
읽었기 때문에, 코드가 재배포돼도 로그의 git_commit이 옛 값(dfc5135)에 고정됐다.

해결: 이미지 빌드 시점에 `docker build --build-arg GIT_COMMIT=$(git rev-parse
--short HEAD)`로 커밋을 이미지 안 파일(BUILD_COMMIT)에 굽는다. 런타임은 그 파일을
우선 읽는다. 파일은 env_file(.env)/environment 주입으로 덮어쓸 수 없으므로 낡은
.env 값이 로그를 오염시키지 못한다.

우선순위:
  1. 이미지에 구워진 BUILD_COMMIT 파일 (빌드 시점 진실)
  2. 명시적 GIT_COMMIT 환경변수 (도커 밖 로컬 실행용)
  3. "unknown" — 낡은 값을 추측/신뢰하지 않는다
"""

from __future__ import annotations

import os
from pathlib import Path

# 이미지 빌드 시 Dockerfile이 이 경로에 커밋 해시를 기록한다.
BUILD_COMMIT_FILE = Path("/app/BUILD_COMMIT")

_UNKNOWN = "unknown"


def _clean(value: str | None) -> str:
    """공백 제거 후 빈 값/unknown 은 빈 문자열로 정규화."""
    if value is None:
        return ""
    stripped = value.strip()
    if not stripped or stripped == _UNKNOWN:
        return ""
    return stripped


def resolve_git_commit(
    build_commit_file: Path = BUILD_COMMIT_FILE,
    env_value: str | None = None,
) -> str:
    """실행 중인 코드의 git commit 을 결정한다.

    Args:
        build_commit_file: 이미지 빌드 시 구워진 커밋 파일 경로.
        env_value: GIT_COMMIT 환경변수 값. None 이면 os.environ 에서 읽는다.

    Returns:
        커밋 해시 문자열. 신뢰할 소스가 없으면 "unknown".
    """
    # 1) 빌드 시점에 이미지에 구워진 파일이 최우선 (낡은 .env 주입에 면역)
    try:
        if build_commit_file.exists():
            baked = _clean(build_commit_file.read_text())
            if baked:
                return baked
    except OSError:
        pass

    # 2) 명시적 환경변수 (도커 밖 로컬 실행 등)
    env = env_value if env_value is not None else os.getenv("GIT_COMMIT")
    cleaned_env = _clean(env)
    if cleaned_env:
        return cleaned_env

    # 3) 추측 금지 — 낡은 값을 신뢰하느니 unknown
    return _UNKNOWN
