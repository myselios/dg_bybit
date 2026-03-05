#!/bin/bash
# CBGB Robust Monitoring - 절대 놓치지 않는 알림
# v7.0 - Telegram 재시도 + 백업 알림

LOG_FILE="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/monitor.log"
ERROR_LOG="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/errors.log"
ALERT_FILE="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/ALERTS.txt"  # 백업 알림
STATE_FILE="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/monitor_state.json"
TELEGRAM_BOT_TOKEN="7994781864:AAGGRPvCwr5fJtmRU143MVfRJZUHU6GtNVE"
TELEGRAM_CHAT_ID="2128418205"
CHECK_INTERVAL=60

mkdir -p "$(dirname "$LOG_FILE")"

if [ ! -f "$STATE_FILE" ]; then
    echo '{"last_tick": 0, "entry_pending_since": 0, "last_trade_time": 0, "alert_sent": {}}' > "$STATE_FILE"
fi

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
    
    local full_message="${prefix}: ${message}"
    
    # 3번 재시도
    local success=false
    for i in {1..3}; do
        if curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d chat_id="${TELEGRAM_CHAT_ID}" \
            -d text="${full_message}" \
            -d parse_mode="Markdown" > /dev/null 2>&1; then
            success=true
            break
        fi
        sleep 2
    done
    
    # 실패 시 로컬 알림 파일에 기록
    if [ "$success" = false ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] TELEGRAM FAILED: ${full_message}" >> "$ALERT_FILE"
        log "⚠️ Telegram 전송 실패 - 로컬 파일에 기록"
    fi
}

check_containers() {
    if ! docker ps | grep -q "cbgb-bot.*healthy"; then
        log "❌ Bot 컨테이너 비정상!"
        send_telegram "Bot 컨테이너 다운! 재시작 중..." "critical"
        
        cd /Users/ria_home/.openclaw/workspace/dg_bybit
        docker-compose restart bot
        sleep 10
        
        if docker ps | grep -q "cbgb-bot.*healthy"; then
            send_telegram "✅ Bot 재시작 성공" "info"
        else
            send_telegram "🚨 Bot 재시작 실패!" "critical"
        fi
    fi
}

check_bot_errors() {
    RECENT_LOGS=$(docker logs cbgb-bot --since 1m 2>&1)
    CRITICAL_ERRORS=$(echo "$RECENT_LOGS" | grep -E " - (ERROR|CRITICAL) - |Traceback|Exception:|🚨 HALT" | grep -v "Halt: None")
    
    if [ ! -z "$CRITICAL_ERRORS" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] CRITICAL ERROR:" >> "$ERROR_LOG"
        echo "$CRITICAL_ERRORS" >> "$ERROR_LOG"
        echo "---" >> "$ERROR_LOG"
        
        if echo "$CRITICAL_ERRORS" | grep -q "🚨 HALT"; then
            ERROR_TYPE="HALT"
            # HALT은 매우 중요!
            send_telegram "🚨🚨🚨 *BOT HALTED*\n확인 필요!" "critical"
            echo "[$(date)] 🚨 HALT 발생!" >> "$ALERT_FILE"
        elif echo "$CRITICAL_ERRORS" | grep -q "Exception"; then
            ERROR_TYPE="Exception"
        else
            ERROR_TYPE="ERROR"
        fi
        
        FIRST_ERROR=$(echo "$CRITICAL_ERRORS" | head -1 | cut -c1-100)
        log "🚨 에러: $ERROR_TYPE"
        send_telegram "🔥 Bot Error\nType: ${ERROR_TYPE}\n\`${FIRST_ERROR}\`" "critical"
    fi
}

check_stuck_state() {
    CURRENT_STATE=$(docker logs cbgb-bot --tail 50 2>&1 | grep "State: State\." | tail -1)
    
    if echo "$CURRENT_STATE" | grep -q "ENTRY_PENDING"; then
        PENDING_SINCE=$(cat "$STATE_FILE" | grep -o '"entry_pending_since":[0-9]*' | cut -d':' -f2)
        CURRENT_TIME=$(date +%s)
        
        if [ "$PENDING_SINCE" = "0" ] || [ -z "$PENDING_SINCE" ]; then
            python3 << EOF
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
state['entry_pending_since'] = $CURRENT_TIME
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f)
EOF
            log "📌 ENTRY_PENDING 시작"
        else
            DURATION=$((CURRENT_TIME - PENDING_SINCE))
            
            if [ $DURATION -gt 1800 ]; then  # 30분
                ALERT_KEY="stuck_entry_pending"
                ALERT_SENT=$(cat "$STATE_FILE" | grep -o "\"$ALERT_KEY\":true" || echo "false")
                
                if [ "$ALERT_SENT" = "false" ]; then
                    HOURS=$((DURATION / 3600))
                    MINS=$(((DURATION % 3600) / 60))
                    log "⚠️ ENTRY_PENDING ${HOURS}h ${MINS}m!"
                    send_telegram "⚠️ *주문 체결 지연*\n${HOURS}시간 ${MINS}분 지속\n확인 필요!" "warning"
                    
                    python3 << EOF
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
if 'alert_sent' not in state:
    state['alert_sent'] = {}
state['alert_sent']['$ALERT_KEY'] = True
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f)
EOF
                fi
            fi
        fi
    else
        python3 << EOF
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
state['entry_pending_since'] = 0
if 'alert_sent' in state and 'stuck_entry_pending' in state['alert_sent']:
    del state['alert_sent']['stuck_entry_pending']
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f)
EOF
    fi
}

check_position_health() {
    EQUITY=$(docker logs cbgb-bot --tail 100 2>&1 | grep "Equity:" | tail -1 | grep -oE '\$[0-9]+\.[0-9]+')
    
    if [ ! -z "$EQUITY" ]; then
        log "💰 Equity: $EQUITY"
    fi
}

# 시작 알림
send_telegram "🚀 *Robust Monitoring v7.0*\n✅ Telegram 재시도 3회\n✅ 백업 알림 파일\n간격: ${CHECK_INTERVAL}초" "info"
log "=== Robust Monitoring v7.0 시작 ==="

while true; do
    check_containers
    check_bot_errors
    check_stuck_state
    check_position_health
    
    sleep $CHECK_INTERVAL
done
