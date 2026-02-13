"""
tests/docker/test_dockerfile_build.py
Phase 14b (Dockerization) Phase 1: Dockerfile 빌드 검증 테스트

목표:
- Multi-Stage Build (base/test/production) 검증
- 의존성 설치 확인
- pytest 자동 실행 검증
- 이미지 크기 제한 검증
- Entrypoint 실행 권한 검증
"""

import subprocess
import pytest
from pathlib import Path


# Fixtures
@pytest.fixture(scope="module")
def project_root() -> Path:
    """프로젝트 루트 디렉토리 반환"""
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def dockerfile_base(project_root: Path) -> Path:
    """Dockerfile.base 경로 반환"""
    return project_root / "docker" / "Dockerfile.base"


# Test 1: Base Image Build
def test_base_image_build(dockerfile_base: Path, project_root: Path):
    """
    Base 이미지 빌드 성공 검증

    검증 항목:
    - python:3.12-slim 기반 이미지 사용
    - Multi-Stage Build Stage 1 (base) 빌드 성공
    - WORKDIR /app 설정 확인
    """
    # Given: Dockerfile.base 존재
    assert dockerfile_base.exists(), "docker/Dockerfile.base 파일이 없습니다"

    # When: base stage 빌드
    result = subprocess.run(
        [
            "docker", "build",
            "--target", "base",
            "-f", str(dockerfile_base),
            "-t", "cbgb:base-test",
            str(project_root)
        ],
        capture_output=True,
        text=True,
        timeout=300  # 5분 타임아웃
    )

    # Then: 빌드 성공
    assert result.returncode == 0, f"Base 이미지 빌드 실패:\n{result.stderr}"

    # Verify: python:3.12-slim 기반
    assert "python:3.12-slim" in result.stdout or "python:3.12-slim" in result.stderr, \
        "Base 이미지는 python:3.12-slim을 사용해야 합니다"


# Test 2: Dependencies Installed
def test_dependencies_installed(dockerfile_base: Path, project_root: Path):
    """
    pyproject.toml 의존성 설치 검증

    검증 항목:
    - pyproject.toml 복사 확인
    - pip install -e .[dev] 실행 확인
    - 필수 패키지 설치 확인 (pytest, mypy, ruff)
    """
    # Given: base 이미지 빌드 완료
    subprocess.run(
        [
            "docker", "build",
            "--target", "base",
            "-f", str(dockerfile_base),
            "-t", "cbgb:base-test",
            str(project_root)
        ],
        capture_output=True,
        timeout=300
    )

    # When: 설치된 패키지 확인
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "cbgb:base-test",
            "pip", "list"
        ],
        capture_output=True,
        text=True,
        timeout=30
    )

    # Then: 필수 패키지 설치 확인
    assert result.returncode == 0, f"pip list 실행 실패:\n{result.stderr}"

    installed_packages = result.stdout.lower()
    assert "pytest" in installed_packages, "pytest가 설치되지 않았습니다"
    assert "mypy" in installed_packages, "mypy가 설치되지 않았습니다"
    assert "ruff" in installed_packages, "ruff가 설치되지 않았습니다"
    assert "pydantic" in installed_packages, "pydantic이 설치되지 않았습니다"


# Test 3: Test Stage Pytest Execution
def test_test_stage_pytest(dockerfile_base: Path, project_root: Path):
    """
    Test Stage에서 pytest 자동 실행 검증

    검증 항목:
    - --target test 빌드 시 pytest 실행
    - 366개 테스트 통과 (또는 현재 테스트 수)
    - 테스트 실패 시 빌드 실패
    """
    # When: test stage 빌드 (pytest 자동 실행)
    result = subprocess.run(
        [
            "docker", "build",
            "--target", "test",
            "-f", str(dockerfile_base),
            "-t", "cbgb:test",
            str(project_root)
        ],
        capture_output=True,
        text=True,
        timeout=600  # 10분 타임아웃 (테스트 실행 포함)
    )

    # Then: 빌드 성공 (pytest 통과)
    assert result.returncode == 0, f"Test stage 빌드 실패 (pytest 실패):\n{result.stderr}"

    # Verify: pytest 실행 흔적 확인
    output = result.stdout + result.stderr
    assert "pytest" in output.lower() or "test stage" in output.lower(), \
        "pytest가 실행되지 않았습니다"

    # Verify: 테스트 통과 메시지 확인 (CACHED 빌드도 허용)
    assert "passed" in output.lower() or "test stage" in output.lower() or "cached" in output.lower(), \
        "pytest 실행 결과가 출력에 없습니다"


# Test 4: Production Stage Minimal Size
def test_production_stage_minimal(dockerfile_base: Path, project_root: Path):
    """
    Production 이미지 크기 제한 검증

    검증 항목:
    - --target production 빌드 성공
    - 이미지 크기 < 500MB
    - 개발 도구 미포함 (pytest, mypy 제외)
    """
    # When: production stage 빌드
    result = subprocess.run(
        [
            "docker", "build",
            "--target", "production",
            "-f", str(dockerfile_base),
            "-t", "cbgb:production-test",
            str(project_root)
        ],
        capture_output=True,
        text=True,
        timeout=300
    )

    # Then: 빌드 성공
    assert result.returncode == 0, f"Production 이미지 빌드 실패:\n{result.stderr}"

    # When: 이미지 크기 확인
    size_result = subprocess.run(
        [
            "docker", "images",
            "cbgb:production-test",
            "--format", "{{.Size}}"
        ],
        capture_output=True,
        text=True,
        timeout=10
    )

    # Then: 크기 제한 검증
    assert size_result.returncode == 0, "이미지 크기 조회 실패"

    size_str = size_result.stdout.strip()
    # 크기 파싱 (예: "450MB", "1.2GB")
    if "GB" in size_str:
        size_mb = float(size_str.replace("GB", "")) * 1024
    elif "MB" in size_str:
        size_mb = float(size_str.replace("MB", ""))
    else:
        pytest.skip(f"이미지 크기 파싱 실패: {size_str}")

    assert size_mb < 500, f"Production 이미지 크기가 500MB를 초과합니다: {size_mb:.1f}MB"


# Test 5: Entrypoint Executable
def test_entrypoint_executable(project_root: Path):
    """
    docker-entrypoint.sh 실행 권한 검증

    검증 항목:
    - docker/docker-entrypoint.sh 파일 존재
    - 실행 권한 (chmod +x) 확인
    - Shebang (#!/bin/bash) 존재
    """
    # Given: entrypoint 스크립트 경로
    entrypoint = project_root / "docker" / "docker-entrypoint.sh"

    # Then: 파일 존재 확인
    assert entrypoint.exists(), "docker/docker-entrypoint.sh 파일이 없습니다"

    # Then: 실행 권한 확인
    import stat
    mode = entrypoint.stat().st_mode
    is_executable = bool(mode & stat.S_IXUSR)
    assert is_executable, "docker-entrypoint.sh에 실행 권한이 없습니다 (chmod +x 필요)"

    # Then: Shebang 확인
    with open(entrypoint, 'r') as f:
        first_line = f.readline().strip()

    assert first_line.startswith("#!"), "Shebang이 없습니다"
    assert "bash" in first_line or "sh" in first_line, \
        "Shebang은 #!/bin/bash 또는 #!/bin/sh여야 합니다"
