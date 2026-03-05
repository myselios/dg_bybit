#!/bin/bash
# Enhanced CBGB Monitoring v2.0
# 24/7 Professional Quant System

LOG_FILE="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/monitor.log"
TELEGRAM_BOT_TOKEN="7994781864:AAGGRPvCwr5fJtmRU143MVfRJZUHU6GtNVE"
TELEGRAM_CHAT_ID="2128418205"
CHECK_INTERVAL=120  # 2분마다 체크 (API 부담 감소)

# 로그 디렉토리 생성
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

send_telegram() {
    local message="$1"
    local priority="${2:-normal}"
    
    # 우선순위에 따라 이모지 추가
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
    log "컨테이너 상태 체크..."
    
    # Bot 컨테이너 체크
    if ! docker ps | grep -q "cbgb-bot.*healthy"; then
        log "❌ Bot 컨테이너 비정상!"
        send_telegram "Bot 컨테이너 재시작 필요!" "critical"
        
        # 자동 재시작
        cd /Users/ria_home/.openclaw/workspace/dg_bybit
        docker-compose restart bot
        sleep 10
        
        if docker ps | grep -q "cbgb-bot.*healthy"; then
            send_telegram "✅ Bot 컨테이너 재시작 성공" "info"
        else
            send_telegram "🚨 Bot 컨테이너 재시작 실패 - 수동 확인 필요!" "critical"
        fi
    fi
}

check_bot_errors() {
    log "에러 로그 체크..."
    
    # 최근 2분간 로그 체크
    RECENT_LOGS=$(docker logs cbgb-bot --since 2m 2>&1)
    
    # Rate limit 체크
    if echo "$RECENT_LOGS" | grep -qi "rate limit exceeded"; then
        log "⚠️ Rate limit 감지"
        send_telegram "Rate limit 발생 - 정상 처리 중" "warning"
    fi
    
    # Critical 에러 체크
    if echo "$RECENT_LOGS" | grep -qE "CRITICAL|EXCEPTION|청산|Liquidation"; then
        ERROR_MSG=$(echo "$RECENT_LOGS" | grep -E "CRITICAL|EXCEPTION|청산|Liquidation" | tail -3)
        log "🚨 심각한 에러 감지: $ERROR_MSG"
        send_telegram "심각한 에러 발생:\n\`\`\`\n${ERROR_MSG}\n\`\`\`" "critical"
    fi
}

check_position_health() {
    log "포지션 상태 체크..."
    
    # 최근 로그에서 포지션 정보 추출
    POSITION_LOG=$(docker logs cbgb-bot --tail 50 2>&1 | grep -E "Position|Equity|Mark price" | tail -5)
    
    if [ ! -z "$POSITION_LOG" ]; then
        log "포지션: $POSITION_LOG"
    fi
}

# 시작 알림
send_telegram "🚀 모니터링 시스템 v2.0 시작\n감시 간격: ${CHECK_INTERVAL}초" "info"

log "=== CBGB 모니터링 시작 ==="

# 메인 루프
while true; do
    check_containers
    check_bot_errors
    check_position_health
    
    log "--- 다음 체크까지 ${CHECK_INTERVAL}초 대기 ---"
    sleep $CHECK_INTERVAL
done
