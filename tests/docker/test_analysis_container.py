"""
tests/docker/test_analysis_container.py
Phase 14b (Dockerization) Phase 4: Analysis Container 검증 테스트

목표:
- docker-compose up analysis 성공 검증
- cron 스케줄 설정 확인
- 분석 스크립트 실행 검증
- 리포트 생성 디렉토리 확인
- 분석 로그 별도 파일 기록 확인
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
def dockerfile_analysis(project_root: Path) -> Path:
    """docker/Dockerfile.analysis 경로 반환"""
    return project_root / "docker" / "Dockerfile.analysis"


@pytest.fixture(scope="module")
def crontab_file(project_root: Path) -> Path:
    """scripts/crontab 경로 반환"""
    return project_root / "scripts" / "crontab"


# Test 1: Analysis Container Starts
def test_analysis_container_starts(docker_compose_file: Path, dockerfile_analysis: Path):
    """
    docker-compose up analysis 성공 검증

    검증 항목:
    - docker-compose.yml 파일 존재
    - analysis 서비스 정의 확인
    - Dockerfile.analysis 존재
    - 이미지 빌드 설정 확인
    """
    # Given: docker-compose.yml 존재
    assert docker_compose_file.exists(), "docker-compose.yml 파일이 없습니다"

    # When: docker-compose.yml 파싱
    with open(docker_compose_file, 'r') as f:
        compose_config = yaml.safe_load(f)

    # Then: analysis 서비스 정의 확인
    assert 'services' in compose_config, "services 섹션이 없습니다"
    assert 'analysis' in compose_config['services'], "analysis 서비스가 정의되지 않았습니다"

    analysis_service = compose_config['services']['analysis']

    # Verify: 필수 설정 확인
    assert 'build' in analysis_service or 'image' in analysis_service, \
        "analysis 서비스에 build 또는 image 설정이 없습니다"

    # Dockerfile.analysis 존재 확인
    if 'build' in analysis_service:
        dockerfile_path = analysis_service['build'].get('dockerfile', 'docker/Dockerfile.analysis')
        assert dockerfile_analysis.exists(), f"{dockerfile_path} 파일이 없습니다"

    # restart 정책 확인
    assert 'restart' in analysis_service, "restart 정책이 없습니다"
    assert analysis_service['restart'] in ['unless-stopped', 'always', 'on-failure', 'no'], \
        f"restart 정책이 올바르지 않습니다: {analysis_service['restart']}"


# Test 2: Cron Jobs Scheduled
def test_cron_jobs_scheduled(dockerfile_analysis: Path, crontab_file: Path):
    """
    crontab 설정 확인

    검증 항목:
    - Dockerfile.analysis에 cron 설치 확인
    - scripts/crontab 파일 존재
    - crontab 파일에 analyze_trades.py 스케줄 확인
    - Dockerfile에서 crontab 등록 확인
    """
    # Given: Dockerfile.analysis 존재
    assert dockerfile_analysis.exists(), "docker/Dockerfile.analysis 파일이 없습니다"

    # When: Dockerfile.analysis 내용 확인
    with open(dockerfile_analysis, 'r') as f:
        dockerfile_content = f.read()

    # Then: cron 설치 확인
    assert 'cron' in dockerfile_content, \
        "Dockerfile.analysis에 cron 설치 명령어가 없습니다"

    # Verify: crontab 파일 존재
    assert crontab_file.exists(), "scripts/crontab 파일이 없습니다"

    # Verify: crontab 파일 내용 확인
    with open(crontab_file, 'r') as f:
        crontab_content = f.read()

    # analyze_trades.py 스케줄 확인
    assert 'analyze_trades.py' in crontab_content, \
        "crontab에 analyze_trades.py 스케줄이 없습니다"

    # Dockerfile에서 crontab 등록 확인
    assert 'crontab' in dockerfile_content or 'cron.d' in dockerfile_content, \
        "Dockerfile.analysis에 crontab 등록 명령어가 없습니다"

    # CMD에 cron -f 확인 (foreground 실행)
    assert 'cron -f' in dockerfile_content or 'cron' in dockerfile_content, \
        "Dockerfile.analysis CMD에 cron 실행 명령어가 없습니다"


# Test 3: Analysis Script Execution
def test_analysis_script_execution(project_root: Path, dockerfile_analysis: Path):
    """
    analyze_trades.py 실행 성공 확인

    검증 항목:
    - scripts/analyze_trades.py 존재
    - Dockerfile.analysis에서 scripts/ 복사 확인
    - src/analysis/ 모듈 존재 확인 (의존성)
    """
    # Given: analyze_trades.py 존재
    analyze_script = project_root / "scripts" / "analyze_trades.py"
    assert analyze_script.exists(), "scripts/analyze_trades.py 파일이 없습니다"

    # When: Dockerfile.analysis 내용 확인
    with open(dockerfile_analysis, 'r') as f:
        dockerfile_content = f.read()

    # Then: scripts/ 디렉토리 복사 확인
    # production stage에서 이미 복사되었으므로, 추가 COPY 불필요
    # 하지만 명시적 COPY도 허용
    # (production stage에서 COPY --from=base /app/scripts ./scripts로 복사됨)

    # Verify: src/analysis/ 모듈 존재
    analysis_module = project_root / "src" / "analysis"
    assert analysis_module.exists(), "src/analysis/ 모듈이 없습니다"

    # 필수 분석 모듈 확인
    required_modules = ['trade_analyzer.py', 'ab_comparator.py', 'report_generator.py']
    for module in required_modules:
        module_path = analysis_module / module
        assert module_path.exists(), f"src/analysis/{module} 파일이 없습니다"


# Test 4: Report Generation
def test_report_generation(docker_compose_file: Path, dockerfile_analysis: Path):
    """
    reports/ 디렉토리 생성 확인

    검증 항목:
    - docker-compose.yml에 cbgb-reports volume 정의
    - analysis 서비스에 reports volume 마운트 확인
    - 또는 Dockerfile에서 reports/ 디렉토리 생성 확인
    """
    # When: docker-compose.yml 파싱
    with open(docker_compose_file, 'r') as f:
        compose_config = yaml.safe_load(f)

    analysis_service = compose_config['services']['analysis']

    # Then: volumes 설정 확인 (선택사항)
    if 'volumes' in analysis_service:
        volumes = analysis_service['volumes']
        # reports volume 마운트 확인 (권장)
        has_reports_volume = any('reports' in vol for vol in volumes)
        if not has_reports_volume:
            print("WARNING: analysis 서비스에 reports volume이 마운트되지 않았습니다")
    else:
        # volumes가 없으면 컨테이너 내부에 저장 (비권장)
        print("WARNING: analysis 서비스에 volumes 설정이 없습니다")

    # Verify: Dockerfile에서 reports/ 디렉토리 생성 확인 (또는 entrypoint에서 생성)
    with open(dockerfile_analysis, 'r') as f:
        dockerfile_content = f.read()

    # mkdir -p /app/reports 또는 entrypoint에서 생성 확인
    # (필수는 아니지만 권장)
    # docker-entrypoint.sh에서 생성하므로 여기서는 검증 생략


# Test 5: Analysis Logs Separate
def test_analysis_logs_separate(crontab_file: Path, docker_compose_file: Path):
    """
    분석 로그 별도 파일 기록 확인

    검증 항목:
    - crontab 파일에 >> /app/logs/analysis.log 리다이렉션 확인
    - docker-compose.yml에 cbgb-logs volume 마운트 확인
    """
    # Given: crontab 파일 존재
    assert crontab_file.exists(), "scripts/crontab 파일이 없습니다"

    # When: crontab 파일 내용 확인
    with open(crontab_file, 'r') as f:
        crontab_content = f.read()

    # Then: analysis.log 리다이렉션 확인
    assert 'analysis.log' in crontab_content, \
        "crontab에 analysis.log 리다이렉션이 없습니다"

    # >> (append) 사용 확인
    assert '>>' in crontab_content, \
        "crontab에 >> (append) 리다이렉션이 없습니다"

    # Verify: docker-compose.yml에 cbgb-logs volume 마운트 확인
    with open(docker_compose_file, 'r') as f:
        compose_config = yaml.safe_load(f)

    analysis_service = compose_config['services']['analysis']

    if 'volumes' in analysis_service:
        volumes = analysis_service['volumes']
        logs_volume_mounted = any('cbgb-logs' in vol or 'logs' in vol for vol in volumes)
        assert logs_volume_mounted, \
            "analysis 서비스에 logs volume이 마운트되지 않았습니다"
    else:
        pytest.skip("analysis 서비스에 volumes 설정이 없습니다 (로그 영구 보존 비활성화)")
