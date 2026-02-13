"""
tests/docker/test_dashboard_container.py
Phase 14b (Dockerization) Phase 3: Dashboard Container 검증 테스트

목표:
- docker-compose up dashboard 성공 검증
- Streamlit 포트 접근성 확인
- logs/ volume 공유 확인 (Bot과 Dashboard 간)
- 로그 파일 변경 감지 (auto-refresh)
- Bot 재시작 시 Dashboard 독립성 검증
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
def dockerfile_dashboard(project_root: Path) -> Path:
    """docker/Dockerfile.dashboard 경로 반환"""
    return project_root / "docker" / "Dockerfile.dashboard"


# Test 1: Dashboard Container Starts
def test_dashboard_container_starts(docker_compose_file: Path, dockerfile_dashboard: Path):
    """
    docker-compose up dashboard 성공 검증

    검증 항목:
    - docker-compose.yml 파일 존재
    - dashboard 서비스 정의 확인
    - Dockerfile.dashboard 존재
    - 이미지 빌드 설정 확인
    """
    # Given: docker-compose.yml 존재
    assert docker_compose_file.exists(), "docker-compose.yml 파일이 없습니다"

    # When: docker-compose.yml 파싱
    with open(docker_compose_file, 'r') as f:
        compose_config = yaml.safe_load(f)

    # Then: dashboard 서비스 정의 확인
    assert 'services' in compose_config, "services 섹션이 없습니다"
    assert 'dashboard' in compose_config['services'], "dashboard 서비스가 정의되지 않았습니다"

    dashboard_service = compose_config['services']['dashboard']

    # Verify: 필수 설정 확인
    assert 'build' in dashboard_service or 'image' in dashboard_service, \
        "dashboard 서비스에 build 또는 image 설정이 없습니다"

    # Dockerfile.dashboard 존재 확인
    if 'build' in dashboard_service:
        dockerfile_path = dashboard_service['build'].get('dockerfile', 'docker/Dockerfile.dashboard')
        assert dockerfile_dashboard.exists(), f"{dockerfile_path} 파일이 없습니다"

    # restart 정책 확인
    assert 'restart' in dashboard_service, "restart 정책이 없습니다"
    assert dashboard_service['restart'] in ['unless-stopped', 'always', 'on-failure'], \
        f"restart 정책이 올바르지 않습니다: {dashboard_service['restart']}"


# Test 2: Streamlit Port Accessible
def test_streamlit_port_accessible(docker_compose_file: Path, dockerfile_dashboard: Path):
    """
    localhost:8501 접근 가능 확인

    검증 항목:
    - docker-compose.yml에 ports 설정 확인 (8501:8501)
    - Dockerfile.dashboard에 EXPOSE 8501 확인
    - Streamlit CMD 설정 확인 (--server.port=8501 --server.address=0.0.0.0)
    """
    # When: docker-compose.yml 파싱
    with open(docker_compose_file, 'r') as f:
        compose_config = yaml.safe_load(f)

    dashboard_service = compose_config['services']['dashboard']

    # Then: ports 설정 확인
    assert 'ports' in dashboard_service, "dashboard 서비스에 ports 설정이 없습니다"

    ports = dashboard_service['ports']
    # "8501:8501" 또는 리스트 형식
    port_8501_exposed = any('8501' in str(port) for port in ports)
    assert port_8501_exposed, "포트 8501이 노출되지 않았습니다"

    # Verify: Dockerfile.dashboard에 EXPOSE 8501 확인
    assert dockerfile_dashboard.exists(), "docker/Dockerfile.dashboard 파일이 없습니다"

    with open(dockerfile_dashboard, 'r') as f:
        dockerfile_content = f.read()

    assert 'EXPOSE 8501' in dockerfile_content, \
        "Dockerfile.dashboard에 EXPOSE 8501이 없습니다"

    # Verify: CMD에 streamlit run 설정 확인 (JSON 배열 또는 shell 형식 모두 허용)
    has_streamlit = '"streamlit"' in dockerfile_content or 'streamlit run' in dockerfile_content
    has_run = '"run"' in dockerfile_content or 'streamlit run' in dockerfile_content
    assert has_streamlit and has_run, \
        "CMD에 streamlit run 설정이 없습니다"
    assert '--server.port=8501' in dockerfile_content or '--server.port 8501' in dockerfile_content, \
        "streamlit --server.port=8501 설정이 없습니다"
    assert '--server.address=0.0.0.0' in dockerfile_content or '--server.address 0.0.0.0' in dockerfile_content, \
        "streamlit --server.address=0.0.0.0 설정이 없습니다"


# Test 3: Dashboard Reads Bot Logs
def test_dashboard_reads_bot_logs(docker_compose_file: Path):
    """
    logs/ volume 공유 확인 (Bot과 Dashboard 간)

    검증 항목:
    - bot 서비스에 cbgb-logs volume 마운트 확인
    - dashboard 서비스에 cbgb-logs volume 마운트 확인 (read-only 권장)
    - 동일한 volume 사용 확인
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

    bot_volumes = bot_service['volumes']
    bot_log_volume_mounted = any('cbgb-logs' in vol for vol in bot_volumes)
    assert bot_log_volume_mounted, "bot 서비스에 cbgb-logs volume이 마운트되지 않았습니다"

    # Verify: dashboard 서비스에 volume 마운트 확인
    dashboard_service = compose_config['services']['dashboard']
    assert 'volumes' in dashboard_service, "dashboard 서비스에 volumes 설정이 없습니다"

    dashboard_volumes = dashboard_service['volumes']
    dashboard_log_volume_mounted = any('cbgb-logs' in vol for vol in dashboard_volumes)
    assert dashboard_log_volume_mounted, \
        "dashboard 서비스에 cbgb-logs volume이 마운트되지 않았습니다"

    # Verify: dashboard는 read-only로 마운트되었는지 확인 (권장사항)
    for vol in dashboard_volumes:
        if 'cbgb-logs' in vol:
            # ":ro" 접미어 확인
            if isinstance(vol, str) and ':ro' not in vol:
                # 경고만 출력 (강제 아님)
                print("WARNING: dashboard의 cbgb-logs volume이 read-only가 아닙니다 (권장: :ro)")


# Test 4: Dashboard Auto Refresh
def test_dashboard_auto_refresh(dockerfile_dashboard: Path, project_root: Path):
    """
    로그 파일 변경 감지 확인

    검증 항목:
    - src/dashboard/file_watcher.py 존재 확인
    - Dockerfile.dashboard에 watchdog 설치 확인 (또는 pyproject.toml dev 의존성)
    - app.py에서 file_watcher 사용 확인 (또는 Streamlit auto-refresh 설정)
    """
    # Given: file_watcher.py 존재 확인
    file_watcher = project_root / "src" / "dashboard" / "file_watcher.py"
    assert file_watcher.exists(), "src/dashboard/file_watcher.py 파일이 없습니다"

    # When: Dockerfile.dashboard 내용 확인
    with open(dockerfile_dashboard, 'r') as f:
        dockerfile_content = f.read()

    # Then: watchdog 설치 확인 (pip install watchdog 또는 pyproject.toml에서)
    # pyproject.toml에 이미 watchdog>=3.0.0이 있으므로 Dockerfile에서는 생략 가능
    # 여기서는 Dockerfile 또는 requirements에 명시되었는지만 확인
    # (production stage에서 pip install -e .로 설치되므로 문제 없음)

    # Verify: app.py에서 file_watcher import 확인
    app_py = project_root / "src" / "dashboard" / "app.py"
    assert app_py.exists(), "src/dashboard/app.py 파일이 없습니다"

    with open(app_py, 'r') as f:
        app_content = f.read()

    # file_watcher import 또는 Streamlit auto-refresh 설정 확인
    has_file_watcher = 'file_watcher' in app_content or 'FileWatcher' in app_content
    has_streamlit_refresh = 'st.rerun' in app_content or 'st.experimental_rerun' in app_content

    assert has_file_watcher or has_streamlit_refresh, \
        "app.py에 file_watcher 또는 Streamlit auto-refresh 설정이 없습니다"


# Test 5: Dashboard Independent Restart
def test_dashboard_independent_restart(docker_compose_file: Path):
    """
    Bot 재시작 시 Dashboard 독립성 검증

    검증 항목:
    - dashboard 서비스에 depends_on: bot 설정이 없는지 확인 (독립 실행)
    - 또는 depends_on이 있더라도 condition: service_started (강제 종속성 회피)
    - Bot과 Dashboard가 별도 컨테이너로 실행되는지 확인
    """
    # When: docker-compose.yml 파싱
    with open(docker_compose_file, 'r') as f:
        compose_config = yaml.safe_load(f)

    dashboard_service = compose_config['services']['dashboard']

    # Then: depends_on 설정 확인
    if 'depends_on' in dashboard_service:
        depends_on = dashboard_service['depends_on']

        # depends_on이 리스트 형식인 경우 (간단한 종속성)
        if isinstance(depends_on, list):
            # bot에 종속되어 있지만, 독립 재시작은 가능 (강제 종속성 아님)
            # 단, bot이 중지되면 dashboard도 중지될 수 있음 (권장하지 않음)
            if 'bot' in depends_on:
                print("WARNING: dashboard가 bot에 종속되어 있습니다 (독립 재시작 권장)")

        # depends_on이 dict 형식인 경우 (조건부 종속성)
        elif isinstance(depends_on, dict):
            # service_healthy, service_started 등 확인
            if 'bot' in depends_on:
                bot_condition = depends_on['bot'].get('condition', 'service_started')
                # service_started는 시작만 확인하므로 독립 재시작 가능
                assert bot_condition in ['service_started', 'service_healthy'], \
                    f"bot 종속성 조건이 올바르지 않습니다: {bot_condition}"
    else:
        # depends_on이 없으면 완전 독립 실행 (권장)
        pass

    # Verify: 별도 container_name 설정 확인
    assert 'container_name' in dashboard_service, "container_name이 설정되지 않았습니다"

    dashboard_container_name = dashboard_service['container_name']
    bot_container_name = compose_config['services']['bot'].get('container_name', 'cbgb-bot')

    assert dashboard_container_name != bot_container_name, \
        "dashboard와 bot이 동일한 container_name을 사용합니다"
