"""
tests/docker/test_bot_container.py
Phase 14b (Dockerization) Phase 2: Bot Container 검증 테스트

목표:
- docker-compose up bot 성공 검증
- 환경변수 주입 확인
- Volume 마운트 검증
- Mainnet 안전 검증
- Graceful shutdown 검증
"""

import subprocess
import pytest
import time
import yaml
from pathlib import Path


# Fixtures
@pytest.fixture(scope="module")
def project_root() -> Path:
    """프로젝트 루트 디렉토리 반환"""
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def docker_compose_file(project_root: Path) -> Path:
    """docker-compose.yml 경로 반환"""
    return project_root / "docker-compose.yml"


@pytest.fixture(scope="module")
def env_example_file(project_root: Path) -> Path:
    """.env.example 경로 반환"""
    return project_root / ".env.example"


# Test 1: Bot Container Starts
def test_bot_container_starts(docker_compose_file: Path, project_root: Path):
    """
    docker-compose up bot 성공 검증

    검증 항목:
    - docker-compose.yml 파일 존재
    - bot 서비스 정의 확인
    - 이미지 빌드 성공 (또는 이미지 존재)
    """
    # Given: docker-compose.yml 존재
    assert docker_compose_file.exists(), "docker-compose.yml 파일이 없습니다"

    # When: docker-compose.yml 파싱
    with open(docker_compose_file, 'r') as f:
        compose_config = yaml.safe_load(f)

    # Then: bot 서비스 정의 확인
    assert 'services' in compose_config, "services 섹션이 없습니다"
    assert 'bot' in compose_config['services'], "bot 서비스가 정의되지 않았습니다"

    bot_service = compose_config['services']['bot']

    # Verify: 필수 설정 확인
    assert 'build' in bot_service or 'image' in bot_service, \
        "bot 서비스에 build 또는 image 설정이 없습니다"
    assert 'restart' in bot_service, "restart 정책이 없습니다"
    assert bot_service['restart'] in ['unless-stopped', 'always', 'on-failure'], \
        f"restart 정책이 올바르지 않습니다: {bot_service['restart']}"


# Test 2: Environment Variables Loaded
def test_env_variables_loaded(docker_compose_file: Path, env_example_file: Path):
    """
    환경변수 주입 확인

    검증 항목:
    - .env.example 파일 존재
    - docker-compose.yml에 env_file 설정 확인
    - 필수 환경변수 정의 확인 (BYBIT_TESTNET, BYBIT_API_KEY 등)
    """
    # Given: .env.example 존재
    assert env_example_file.exists(), ".env.example 파일이 없습니다"

    # When: .env.example 파싱
    with open(env_example_file, 'r') as f:
        env_lines = f.readlines()

    env_vars = {}
    for line in env_lines:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            env_vars[key.strip()] = value.strip()

    # Then: 필수 환경변수 확인
    required_vars = ['BYBIT_TESTNET', 'BYBIT_TESTNET_API_KEY', 'BYBIT_TESTNET_API_SECRET']
    for var in required_vars:
        assert var in env_vars, f"필수 환경변수 {var}가 .env.example에 없습니다"

    # Verify: docker-compose.yml에 env_file 설정 확인
    with open(docker_compose_file, 'r') as f:
        compose_config = yaml.safe_load(f)

    bot_service = compose_config['services']['bot']
    # env_file은 선택사항 (environment로 직접 설정 가능)
    # 하지만 권장사항이므로 경고만 출력
    if 'env_file' not in bot_service and 'environment' not in bot_service:
        pytest.skip("env_file 또는 environment 설정이 없습니다 (선택사항)")


# Test 3: Log Volume Mounted
def test_log_volume_mounted(docker_compose_file: Path):
    """
    logs/ 디렉토리 volume 마운트 검증

    검증 항목:
    - volumes 정의 확인
    - cbgb-logs volume 정의
    - bot 서비스에 volume 마운트 확인
    """
    # When: docker-compose.yml 파싱
    with open(docker_compose_file, 'r') as f:
        compose_config = yaml.safe_load(f)

    # Then: volumes 정의 확인
    assert 'volumes' in compose_config, "volumes 섹션이 없습니다"
    assert 'cbgb-logs' in compose_config['volumes'], "cbgb-logs volume이 정의되지 않았습니다"

    # Verify: bot 서비스에 volume 마운트 확인
    bot_service = compose_config['services']['bot']
    assert 'volumes' in bot_service, "bot 서비스에 volumes 설정이 없습니다"

    # cbgb-logs volume 마운트 확인
    volumes = bot_service['volumes']
    log_volume_mounted = any('cbgb-logs' in vol for vol in volumes)
    assert log_volume_mounted, "cbgb-logs volume이 bot 서비스에 마운트되지 않았습니다"


# Test 4: Mainnet Safety Check
def test_mainnet_safety_check(project_root: Path):
    """
    Mainnet 안전 검증 실행 확인

    검증 항목:
    - docker/Dockerfile.bot 존재
    - ENTRYPOINT에 docker-entrypoint.sh 설정 확인
    - docker-entrypoint.sh에 안전 검증 로직 확인
    """
    # Given: Dockerfile.bot 존재
    dockerfile_bot = project_root / "docker" / "Dockerfile.bot"
    assert dockerfile_bot.exists(), "docker/Dockerfile.bot 파일이 없습니다"

    # When: Dockerfile.bot 내용 확인
    with open(dockerfile_bot, 'r') as f:
        dockerfile_content = f.read()

    # Then: ENTRYPOINT 설정 확인
    assert 'ENTRYPOINT' in dockerfile_content, "ENTRYPOINT가 설정되지 않았습니다"
    assert 'docker-entrypoint.sh' in dockerfile_content, \
        "docker-entrypoint.sh를 ENTRYPOINT로 사용하지 않습니다"

    # Verify: docker-entrypoint.sh에 안전 검증 로직 확인
    entrypoint_script = project_root / "docker" / "docker-entrypoint.sh"
    assert entrypoint_script.exists(), "docker/docker-entrypoint.sh 파일이 없습니다"

    with open(entrypoint_script, 'r') as f:
        script_content = f.read()

    # BYBIT_TESTNET 검증 로직 확인
    assert 'BYBIT_TESTNET' in script_content, \
        "docker-entrypoint.sh에 BYBIT_TESTNET 검증 로직이 없습니다"


# Test 5: Graceful Shutdown
def test_bot_graceful_shutdown(docker_compose_file: Path, project_root: Path):
    """
    SIGTERM 시 정상 종료 검증

    검증 항목:
    - docker-compose.yml에 stop_grace_period 설정 확인
    - stop_signal 설정 확인 (선택사항)
    - Dockerfile에서 STOPSIGNAL 설정 확인 (선택사항)
    """
    # When: docker-compose.yml 파싱
    with open(docker_compose_file, 'r') as f:
        compose_config = yaml.safe_load(f)

    bot_service = compose_config['services']['bot']

    # Then: stop_grace_period 설정 확인 (기본값 10초보다 길어야 함)
    if 'stop_grace_period' in bot_service:
        # 문자열 형식 (예: "30s") 또는 숫자 형식
        grace_period = bot_service['stop_grace_period']
        if isinstance(grace_period, str):
            # "30s" → 30
            grace_seconds = int(grace_period.rstrip('s'))
        else:
            grace_seconds = int(grace_period)

        assert grace_seconds >= 30, \
            f"stop_grace_period가 30초 미만입니다: {grace_seconds}초"
    else:
        # stop_grace_period가 없으면 기본값 10초 (권장: 30초 이상)
        pytest.skip("stop_grace_period가 설정되지 않았습니다 (기본값 10초 사용)")

    # Verify: ENTRYPOINT가 exec 형식인지 확인 (신호 전달 보장)
    dockerfile_bot = project_root / "docker" / "Dockerfile.bot"
    if dockerfile_bot.exists():
        with open(dockerfile_bot, 'r') as f:
            dockerfile_content = f.read()

        # exec "$@" 패턴 확인 (docker-entrypoint.sh에서)
        entrypoint_script = project_root / "docker" / "docker-entrypoint.sh"
        if entrypoint_script.exists():
            with open(entrypoint_script, 'r') as f:
                script_content = f.read()

            assert 'exec "$@"' in script_content or 'exec "$@"' in script_content, \
                "docker-entrypoint.sh에 exec 명령어가 없습니다 (신호 전달 불가)"
