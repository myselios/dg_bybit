#!/bin/bash
# scripts/docker_rebuild.sh
# Docker 컨테이너 재빌드 및 재시작 스크립트

set -e

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 도움말
show_help() {
    echo -e "${BLUE}==================================================${NC}"
    echo -e "${BLUE}  CBGB Docker 재빌드 및 재시작 스크립트${NC}"
    echo -e "${BLUE}==================================================${NC}"
    echo ""
    echo "사용법:"
    echo "  $0 [옵션] [서비스명]"
    echo ""
    echo "옵션:"
    echo "  -h, --help       이 도움말 표시"
    echo "  -l, --logs       재시작 후 로그 tail"
    echo "  -n, --no-build   빌드 없이 재시작만"
    echo "  -c, --clean      볼륨 포함 전체 삭제 후 재시작"
    echo ""
    echo "서비스명 (선택사항):"
    echo "  bot              Bot 컨테이너만"
    echo "  dashboard        Dashboard 컨테이너만"
    echo "  analysis         Analysis 컨테이너만"
    echo "  (없음)           전체 서비스"
    echo ""
    echo "예시:"
    echo "  $0                     # 전체 재빌드"
    echo "  $0 -l                  # 전체 재빌드 후 로그"
    echo "  $0 bot                 # Bot만 재빌드"
    echo "  $0 -n dashboard        # Dashboard 재시작만"
    echo "  $0 -c                  # 볼륨 포함 전체 삭제 후 재빌드"
    echo ""
}

# 기본값
SERVICE=""
SHOW_LOGS=false
NO_BUILD=false
CLEAN=false

# 옵션 파싱
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -l|--logs)
            SHOW_LOGS=true
            shift
            ;;
        -n|--no-build)
            NO_BUILD=true
            shift
            ;;
        -c|--clean)
            CLEAN=true
            shift
            ;;
        bot|dashboard|analysis)
            SERVICE=$1
            shift
            ;;
        *)
            echo -e "${RED}❌ 알 수 없는 옵션: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# 프로젝트 루트로 이동
cd "$(dirname "$0")/.."

# 빌드 시점 커밋을 이미지에 굽기 위해 export (docker-compose build.args 가 참조)
# 낡은 .env 의 GIT_COMMIT 대신 항상 현재 HEAD 를 사용한다.
GIT_COMMIT="$(git rev-parse --short HEAD)"
export GIT_COMMIT
echo -e "${BLUE}  빌드 대상 커밋: ${GIT_COMMIT}${NC}"

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}  CBGB Docker 재빌드 시작${NC}"
echo -e "${BLUE}==================================================${NC}"
echo ""

# Step 1: 기존 컨테이너 중지 및 삭제
if [ "$CLEAN" = true ]; then
    echo -e "${YELLOW}🗑️  전체 정리 (볼륨 포함)...${NC}"
    docker-compose down -v
else
    echo -e "${YELLOW}🛑 기존 컨테이너 중지 및 삭제...${NC}"
    if [ -n "$SERVICE" ]; then
        docker-compose stop "$SERVICE"
        docker-compose rm -f "$SERVICE"
    else
        docker-compose down
    fi
fi
echo ""

# Step 2: 이미지 빌드 (--no-build가 아닌 경우)
if [ "$NO_BUILD" = false ]; then
    echo -e "${YELLOW}🔨 Docker 이미지 빌드...${NC}"
    if [ -n "$SERVICE" ]; then
        docker-compose build "$SERVICE"
    else
        docker-compose build
    fi
    echo ""
fi

# Step 3: 컨테이너 시작
echo -e "${YELLOW}🚀 컨테이너 시작...${NC}"
if [ -n "$SERVICE" ]; then
    docker-compose up -d "$SERVICE"
else
    docker-compose up -d
fi
echo ""

# Step 4: 잠시 대기 (컨테이너 초기화)
echo -e "${YELLOW}⏳ 컨테이너 초기화 대기 (5초)...${NC}"
sleep 5
echo ""

# Step 5: 상태 확인
echo -e "${GREEN}✅ 컨테이너 상태:${NC}"
docker-compose ps
echo ""

# Step 5.5: 배포 검증 (실행 중인 코드 == HEAD 확인)
# bot 컨테이너에 구워진 커밋이 현재 HEAD 와 일치하는지 확인한다.
# 불일치 = 구코드가 돌고 있다는 뜻 (재빌드 누락/캐시/‑n 재시작) → 즉시 실패.
if [ -z "$SERVICE" ] || [ "$SERVICE" = "bot" ]; then
    echo -e "${YELLOW}🔎 배포 검증: 컨테이너 커밋 == HEAD 확인...${NC}"
    EXPECTED_COMMIT="$(git rev-parse --short HEAD)"
    ACTUAL_COMMIT="$(docker exec cbgb-bot cat /app/BUILD_COMMIT 2>/dev/null | tr -d '[:space:]')"

    if [ -z "$ACTUAL_COMMIT" ]; then
        echo -e "${RED}❌ 배포 검증 실패: 컨테이너에서 /app/BUILD_COMMIT 을 읽지 못함${NC}"
        echo -e "${RED}   (이미지에 커밋 스탬프가 없음 — 재빌드 필요)${NC}"
        exit 1
    fi

    if [ "$ACTUAL_COMMIT" != "$EXPECTED_COMMIT" ]; then
        echo -e "${RED}❌ 배포 검증 실패: 구코드가 실행 중입니다${NC}"
        echo -e "${RED}   컨테이너 커밋: ${ACTUAL_COMMIT}${NC}"
        echo -e "${RED}   HEAD 커밋:     ${EXPECTED_COMMIT}${NC}"
        echo -e "${RED}   → 재빌드(-n 없이)로 다시 배포하세요.${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ 배포 검증 통과: 컨테이너 == HEAD (${ACTUAL_COMMIT})${NC}"
    echo ""
fi

# Step 6: 로그 확인 (옵션)
if [ "$SHOW_LOGS" = true ]; then
    echo -e "${BLUE}==================================================${NC}"
    echo -e "${BLUE}  실시간 로그 (Ctrl+C로 종료)${NC}"
    echo -e "${BLUE}==================================================${NC}"
    echo ""
    if [ -n "$SERVICE" ]; then
        docker-compose logs -f "$SERVICE"
    else
        docker-compose logs -f
    fi
fi

echo -e "${GREEN}✅ Docker 재빌드 완료!${NC}"
echo ""
echo "추가 명령어:"
echo "  docker-compose ps                # 상태 확인"
echo "  docker-compose logs -f bot       # Bot 로그"
echo "  docker-compose logs -f dashboard # Dashboard 로그"
echo "  tail -f logs/mainnet_dry_run/mainnet_dry_run.log  # Mainnet 로그"
echo ""
