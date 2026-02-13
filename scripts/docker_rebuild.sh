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
