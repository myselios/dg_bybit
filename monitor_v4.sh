#!/bin/bash
# Enhanced CBGB Monitoring v4.0
# 정확한 에러 감지 + 오탐지 방지

LOG_FILE="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/monitor.log"
ERROR_LOG="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/errors.log"
TELEGRAM_BOT_TOKEN="7994781864:AAGGRPvCwr5fJtmRU143MVfRJZUHU6GtNVE"
TELEGRAM_CHAT_ID="2128418205"
CHECK_INTERVAL=60  # 1분마다 체크

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
    # 마지막 1분간 로그 체크
    RECENT_LOGS=$(docker logs cbgb-bot --since 1m 2>&1)
    
    # 실제 에러만 감지 (정확한 패턴)
    # - " - ERROR - " : 로그 레벨이 ERROR
    # - " - CRITICAL - " : 로그 레벨이 CRITICAL
    # - "Traceback" : Python traceback
    # - "Exception:" : 실제 예외
    # - "🚨 HALT" : HALT 발동 (이모지 포함)
    CRITICAL_ERRORS=$(echo "$RECENT_LOGS" | grep -E " - (ERROR|CRITICAL) - |Traceback|Exception:|🚨 HALT" | grep -v "Halt: None")
    
    if [ ! -z "$CRITICAL_ERRORS" ]; then
        # 에러 로그에 기록
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] CRITICAL ERROR DETECTED:" >> "$ERROR_LOG"
        echo "$CRITICAL_ERRORS" >> "$ERROR_LOG"
        echo "---" >> "$ERROR_LOG"
        
        # 에러 타입 추출
        if echo "$CRITICAL_ERRORS" | grep -q "UnboundLocalError"; then
            ERROR_TYPE="UnboundLocalError"
        elif echo "$CRITICAL_ERRORS" | grep -q "ValueError"; then
            ERROR_TYPE="ValueError"
        elif echo "$CRITICAL_ERRORS" | grep -q "🚨 HALT"; then
            ERROR_TYPE="HALT"
        elif echo "$CRITICAL_ERRORS" | grep -q "Exception"; then
            ERROR_TYPE="Exception"
        else
            ERROR_TYPE="ERROR"
        fi
        
        # 첫 에러 라인 추출 (최대 100자)
        FIRST_ERROR=$(echo "$CRITICAL_ERRORS" | head -1)
        SHORT_MSG="${FIRST_ERROR:0:100}"
        
        log "🚨 에러 감지: $ERROR_TYPE"
        send_telegram "🔥 Bot Error\nType: ${ERROR_TYPE}\n\`${SHORT_MSG}\`" "critical"
    fi
}

check_position_health() {
    # 포지션 & Equity 정보
    POSITION_LOG=$(docker logs cbgb-bot --tail 20 2>&1 | grep -E "Equity:|Position recovered|Stop Loss set" | tail -2)
    
    if [ ! -z "$POSITION_LOG" ]; then
        log "📊 $(echo "$POSITION_LOG" | tail -1)"
    fi
}

# 시작 알림
send_telegram "🚀 모니터링 v4.0 시작\n간격: ${CHECK_INTERVAL}초\n에러 감지: 정확도 개선" "info"
log "=== CBGB 모니터링 v4.0 시작 ==="

# 메인 루프
while true; do
    check_containers
    check_bot_errors
    check_position_health
    
    sleep $CHECK_INTERVAL
done
