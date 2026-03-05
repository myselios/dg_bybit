#!/bin/bash
# CBGB Auto Redeploy Script
# Git pull → Rebuild → Restart

TELEGRAM_BOT_TOKEN="7994781864:AAGGRPvCwr5fJtmRU143MVfRJZUHU6GtNVE"
TELEGRAM_CHAT_ID="2128418205"
PROJECT_DIR="/Users/ria_home/.openclaw/workspace/dg_bybit"

# 텔레그램 메시지 전송
send_telegram() {
    local message="$1"
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
