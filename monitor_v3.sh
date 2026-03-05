#!/bin/bash
# Enhanced CBGB Monitoring v3.0
# 실시간 에러 감지 + 빠른 알림

LOG_FILE="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/monitor.log"
ERROR_LOG="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/errors.log"
TELEGRAM_BOT_TOKEN="7994781864:AAGGRPvCwr5fJtmRU143MVfRJZUHU6GtNVE"
TELEGRAM_CHAT_ID="2128418205"
CHECK_INTERVAL=30  # 30초마다 체크 (빠른 감지)

# 로그 디렉토리 생성
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

send_telegram() {
    local message="$1"
    local priority="${2:-normal}"
    
    case $priority in
        critical) prefix="🚨 CRITICAL" ;;
        warning)  prefix="⚠️ WARNING" ;;
        info)     prefix="ℹ️ INFO" ;;
        *)        prefix="📊 MONITOR" ;;
    esac
    
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d text="${prefix}: ${message}" \
        -d parse_mode="Markdown" > /dev/null 2>&1
}

check_containers() {
    # Bot 컨테이너 체크
    if ! docker ps | grep -q "cbgb-bot.*healthy"; then
        log "❌ Bot 컨테이너 비정상!"
        send_telegram "Bot 컨테이너 재시작 필요!" "critical"
        
        # 자동 재시작
        cd /Users/ria_home/.openclaw/workspace/dg_bybit
        docker-compose restart bot
        sleep 10
        
        if docker ps | grep -q "cbgb-bot.*healthy"; then
            send_telegram "✅ Bot 재시작 성공" "info"
        else
            send_telegram "🚨 Bot 재시작 실패 - 수동 확인 필요!" "critical"
        fi
    fi
}

check_bot_errors() {
    # 실시간 로그 체크 (마지막 50줄)
    RECENT_LOGS=$(docker logs cbgb-bot --tail 50 2>&1)
    
    # Critical 에러 체크
    CRITICAL_ERRORS=$(echo "$RECENT_LOGS" | grep -iE "ERROR|EXCEPTION|Traceback|UnboundLocalError|HALT" | tail -5)
    
    if [ ! -z "$CRITICAL_ERRORS" ]; then
        # 에러 로그에 기록
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] CRITICAL ERROR DETECTED:" >> "$ERROR_LOG"
        echo "$CRITICAL_ERRORS" >> "$ERROR_LOG"
        echo "---" >> "$ERROR_LOG"
        
        # 에러 타입 추출
        ERROR_TYPE=$(echo "$CRITICAL_ERRORS" | grep -oE "(UnboundLocalError|ValueError|RuntimeError|HALT)" | head -1)
        
        # 간단한 메시지로 Telegram 알림
        SHORT_MSG=$(echo "$CRITICAL_ERRORS" | head -2 | tail -1)
        log "🚨 에러 감지: $ERROR_TYPE"
        send_telegram "🔥 Bot Error Detected\nType: ${ERROR_TYPE}\n\`${SHORT_MSG:0:100}\`" "critical"
    fi
}

check_position_health() {
    # 포지션 & Equity 정보
    POSITION_LOG=$(docker logs cbgb-bot --tail 30 2>&1 | grep -E "Equity|Position|Stop Loss" | tail -3)
    
    if [ ! -z "$POSITION_LOG" ]; then
        log "📊 $(echo "$POSITION_LOG" | tail -1)"
    fi
}

# 시작 알림
send_telegram "🚀 모니터링 v3.0 시작\n감시 간격: ${CHECK_INTERVAL}초 (빠른 감지)" "info"
log "=== CBGB 모니터링 v3.0 시작 ==="

# 메인 루프
while true; do
    check_containers
    check_bot_errors  # 에러 감지 강화!
    check_position_health
    
    sleep $CHECK_INTERVAL
done
