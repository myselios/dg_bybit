#!/bin/bash
# CBGB Bot Monitor Script

TELEGRAM_BOT_TOKEN="7994781864:AAGGRPvCwr5fJtmRU143MVfRJZUHU6GtNVE"
TELEGRAM_CHAT_ID="2128418205"
PROJECT_DIR="/Users/ria_home/.openclaw/workspace/dg_bybit"

# 텔레그램 전송
send_telegram() {
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d text="$1" > /dev/null
}

# 컨테이너 상태 체크
check_containers() {
    for container in cbgb-bot cbgb-dashboard cbgb-analysis; do
        if ! docker ps | grep -q "$container.*Up"; then
            send_telegram "🚨 $container 중지됨! 재시작 중..."
            cd "$PROJECT_DIR" && docker-compose restart "$container"
        fi
    done
}

# 에러 로그 체크
check_errors() {
    errors=$(docker logs cbgb-bot --tail 50 2>&1 | grep -iE "ERROR|EXCEPTION|청산")
    if [ -n "$errors" ]; then
        send_telegram "⚠️ 에러 감지: ${errors:0:200}"
    fi
}

# 메인 루프
while true; do
    check_containers
    check_errors
    sleep 60
done
