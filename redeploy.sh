#!/bin/bash
# CBGB Auto Redeploy Script
# Git pull → Rebuild → Restart

# 프로젝트 루트: 스크립트 위치 기준으로 결정 (하드코딩된 절대경로 금지).
# 이전에는 macOS 절대경로가 하드코딩돼 있어, 이 호스트에서는 아래 cd 가 실패해
# 스크립트가 조용히 exit 1 → "재배포"가 no-op 이 됐다.
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 텔레그램 크레덴셜은 환경변수/.env 에서 읽는다 (시크릿 하드코딩 금지).
: "${TELEGRAM_BOT_TOKEN:=}"
: "${TELEGRAM_CHAT_ID:=}"

# 텔레그램 메시지 전송 (토큰 미설정 시 조용히 스킵)
send_telegram() {
    local message="$1"
    [ -z "${TELEGRAM_BOT_TOKEN}" ] || [ -z "${TELEGRAM_CHAT_ID}" ] && return 0
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d text="${message}" \
        -d parse_mode="Markdown" > /dev/null
}

echo "🔄 Starting redeploy process..."
send_telegram "🔄 *재배포 시작*\n\n코드 업데이트 중..."

cd "$PROJECT_DIR" || exit 1

# Git pull
echo "📥 Pulling latest changes..."
if git pull origin main; then
    send_telegram "✅ Git pull 성공"
else
    send_telegram "❌ Git pull 실패!"
    exit 1
fi

# 빌드 시점 커밋을 이미지에 굽기 위해 export (docker-compose build.args 가 참조)
GIT_COMMIT="$(git rev-parse --short HEAD)"
export GIT_COMMIT
echo "📌 빌드 대상 커밋: ${GIT_COMMIT}"

# Docker Compose down
echo "🛑 Stopping containers..."
docker-compose down
send_telegram "🛑 컨테이너 중지됨"

# Rebuild images
echo "🔨 Rebuilding images..."
send_telegram "🔨 이미지 재빌드 중... (3-5분 소요)"

if docker build -t cbgb:production -f docker/Dockerfile.base .; then
    send_telegram "✅ Base 이미지 빌드 완료"
else
    send_telegram "❌ Base 이미지 빌드 실패!"
    exit 1
fi

if docker-compose build; then
    send_telegram "✅ 서비스 이미지 빌드 완료"
else
    send_telegram "❌ 서비스 이미지 빌드 실패!"
    exit 1
fi

# Start containers
echo "🚀 Starting containers..."
if docker-compose up -d; then
    send_telegram "✅ 컨테이너 시작 완료!"
else
    send_telegram "❌ 컨테이너 시작 실패!"
    exit 1
fi

# Wait for health check
sleep 10

# 배포 검증: 컨테이너에 구워진 커밋 == HEAD 확인
# 불일치 = 구코드 실행 중 (재빌드 누락/캐시) → 즉시 실패.
echo "🔎 배포 검증: 컨테이너 커밋 == HEAD 확인..."
ACTUAL_COMMIT="$(docker exec cbgb-bot cat /app/BUILD_COMMIT 2>/dev/null | tr -d '[:space:]')"
if [ "$ACTUAL_COMMIT" != "$GIT_COMMIT" ]; then
    send_telegram "❌ *배포 검증 실패!*\n\n구코드 실행 중: 컨테이너=${ACTUAL_COMMIT:-none}, HEAD=${GIT_COMMIT}"
    echo "❌ 배포 검증 실패: 컨테이너 커밋(${ACTUAL_COMMIT:-none}) != HEAD(${GIT_COMMIT})"
    exit 1
fi
echo "✅ 배포 검증 통과: 컨테이너 == HEAD (${GIT_COMMIT})"

# Check status
STATUS=$(docker-compose ps --format json | jq -r '.[].Health' | grep -v "healthy" | wc -l)

if [ "$STATUS" -eq 0 ]; then
    send_telegram "🎉 *재배포 완료!*\n\n모든 컨테이너 정상 작동 중"
    echo "✅ Redeploy completed successfully!"
else
    send_telegram "⚠️ 재배포 완료했지만 일부 컨테이너 상태 확인 필요"
    echo "⚠️ Some containers may not be healthy"
fi

# Show logs
echo ""
echo "📜 Recent bot logs:"
docker logs cbgb-bot --tail 20
