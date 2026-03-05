#!/bin/bash
# CBGB Smart Monitoring - 선제적 알림 시스템
# v6.0 - 이상 징후 자동 감지 & 알림

LOG_FILE="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/monitor.log"
ERROR_LOG="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/errors.log"
STATE_FILE="/Users/ria_home/.openclaw/workspace/dg_bybit/logs/monitor_state.json"
TELEGRAM_BOT_TOKEN="7994781864:AAGGRPvCwr5fJtmRU143MVfRJZUHU6GtNVE"
TELEGRAM_CHAT_ID="2128418205"
CHECK_INTERVAL=60  # 1분

mkdir -p "$(dirname "$LOG_FILE")"

# 초기 상태 파일
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
    
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d text="${prefix}: ${message}" \
        -d parse_mode="Markdown" > /dev/null 2>&1
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
            send_telegram "🚨 Bot 재시작 실패 - 확인 필요!" "critical"
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
    # ENTRY_PENDING 장시간 지속 감지
    CURRENT_STATE=$(docker logs cbgb-bot --tail 50 2>&1 | grep "State: State\." | tail -1)
    
    if echo "$CURRENT_STATE" | grep -q "ENTRY_PENDING"; then
        # 상태 파일 읽기
        PENDING_SINCE=$(cat "$STATE_FILE" | grep -o '"entry_pending_since":[0-9]*' | cut -d':' -f2)
        CURRENT_TIME=$(date +%s)
        
        if [ "$PENDING_SINCE" = "0" ] || [ -z "$PENDING_SINCE" ]; then
            # 처음 발견
            python3 << EOF
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
state['entry_pending_since'] = $CURRENT_TIME
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f)
EOF
            log "📌 ENTRY_PENDING 상태 시작"
        else
            # 지속 시간 확인
            DURATION=$((CURRENT_TIME - PENDING_SINCE))
            
            # 30분 이상 지속
            if [ $DURATION -gt 1800 ]; then
                ALERT_KEY="stuck_entry_pending"
                ALERT_SENT=$(cat "$STATE_FILE" | grep -o "\"$ALERT_KEY\":true" || echo "false")
                
                if [ "$ALERT_SENT" = "false" ]; then
                    HOURS=$((DURATION / 3600))
                    MINS=$(((DURATION % 3600) / 60))
                    log "⚠️ ENTRY_PENDING ${HOURS}h ${MINS}m 지속!"
                    send_telegram "⚠️ *주문 체결 지연*\nENTRY_PENDING ${HOURS}시간 ${MINS}분 지속\n확인 필요!" "warning"
                    
                    # 알림 전송 기록
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
        # ENTRY_PENDING 아니면 초기화
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

check_no_activity() {
    # Tick 번호로 활동 감지
    CURRENT_TICK=$(docker logs cbgb-bot --tail 20 2>&1 | grep "🔄 Tick" | tail -1 | grep -oE 'Tick [0-9]+' | grep -oE '[0-9]+')
    
    if [ ! -z "$CURRENT_TICK" ]; then
        LAST_TICK=$(cat "$STATE_FILE" | grep -o '"last_tick":[0-9]*' | cut -d':' -f2)
        
        if [ "$LAST_TICK" = "$CURRENT_TICK" ]; then
            # Tick 증가 안 함 = 봇 정지?
            log "⚠️ 봇 활동 없음 (Tick 정지)"
            send_telegram "⚠️ *봇 활동 정지 감지*\nTick ${CURRENT_TICK}에서 멈춤\n확인 필요!" "warning"
        fi
        
        # Tick 업데이트
        python3 << EOF
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
state['last_tick'] = $CURRENT_TICK
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f)
EOF
    fi
}

check_liquidation_risk() {
    POSITION_INFO=$(docker logs cbgb-bot --tail 200 2>&1 | grep "Position recovered" | tail -1)
    
    if [ -z "$POSITION_INFO" ]; then
        return
    fi
    
    ENTRY_PRICE=$(echo "$POSITION_INFO" | grep -oE '\$[0-9]+\.[0-9]+' | tr -d '$')
    DIRECTION=$(echo "$POSITION_INFO" | grep -oE 'Sell|Buy')
    
    if [ -z "$ENTRY_PRICE" ]; then
        return
    fi
    
    CURRENT_PRICE=$(docker logs cbgb-bot --tail 50 2>&1 | grep "mark_price" | tail -1 | grep -oE 'mark_price=\$[0-9,]+\.[0-9]+' | grep -oE '[0-9,]+\.[0-9]+' | tr -d ',')
    
    if [ -z "$CURRENT_PRICE" ]; then
        return
    fi
    
    LIQUIDATION_INFO=$(python3 << PYEOF
entry = float("$ENTRY_PRICE")
current = float("$CURRENT_PRICE")
leverage = 5
direction = "$DIRECTION"

if direction == "Sell":
    liq_price = entry * (1 + 1/leverage)
    liq_distance_pct = ((liq_price - current) / current) * 100
else:
    liq_price = entry * (1 - 1/leverage)
    liq_distance_pct = ((current - liq_price) / current) * 100

print(f"{liq_price:.2f}|{liq_distance_pct:.2f}")
PYEOF
)
    
    LIQ_PRICE=$(echo "$LIQUIDATION_INFO" | cut -d'|' -f1)
    LIQ_DISTANCE=$(echo "$LIQUIDATION_INFO" | cut -d'|' -f2)
    
    if (( $(echo "$LIQ_DISTANCE < 10" | bc -l) )); then
        log "🔴 청산 위험! 거리: ${LIQ_DISTANCE}%"
        send_telegram "🔴 *청산 위험!*\n현재: \$${CURRENT_PRICE}\n청산가: \$${LIQ_PRICE}\n거리: ${LIQ_DISTANCE}%" "critical"
    elif (( $(echo "$LIQ_DISTANCE < 15" | bc -l) )); then
        ALERT_KEY="liq_warning_15"
        ALERT_SENT=$(cat "$STATE_FILE" | grep -o "\"$ALERT_KEY\":true" || echo "false")
        
        if [ "$ALERT_SENT" = "false" ]; then
            log "🟡 청산 주의! 거리: ${LIQ_DISTANCE}%"
            send_telegram "🟡 *청산 주의*\n거리: ${LIQ_DISTANCE}% (15% 이하)" "warning"
            
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
    else
        # 안전 구간이면 알림 초기화
        python3 << EOF
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
if 'alert_sent' in state and 'liq_warning_15' in state['alert_sent']:
    del state['alert_sent']['liq_warning_15']
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f)
EOF
        log "🟢 청산 안전: ${LIQ_DISTANCE}%"
    fi
}

check_position_health() {
    EQUITY=$(docker logs cbgb-bot --tail 50 2>&1 | grep "Equity:" | tail -1 | grep -oE '\$[0-9]+\.[0-9]+')
    STOP_LOSS=$(docker logs cbgb-bot --tail 50 2>&1 | grep "Stop Loss set:" | tail -1 | grep -oE '\$[0-9,]+\.[0-9]+')
    
    if [ ! -z "$EQUITY" ]; then
        log "💰 Equity: $EQUITY | SL: $STOP_LOSS"
    fi
}

# 시작 알림
send_telegram "🚀 *Smart Monitoring v6.0*\n✅ 선제적 알림 활성화\n✅ 이상 징후 자동 감지\n간격: ${CHECK_INTERVAL}초" "info"
log "=== Smart Monitoring v6.0 시작 ==="

# 메인 루프
while true; do
    check_containers
    check_bot_errors
    check_stuck_state        # 🆕 ENTRY_PENDING 장시간 감지
    check_no_activity        # 🆕 봇 정지 감지
    check_liquidation_risk
    check_position_health
    
    sleep $CHECK_INTERVAL
done
