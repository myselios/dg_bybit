#!/bin/bash
# CBGB Monitoring FINAL - 청산 감지 포함
# v5.0 - 완전판

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
    # Bot 컨테이너 체크 (healthy 또는 starting 상태 허용)
    if ! docker ps | grep -q "cbgb-bot"; then
        # 컨테이너가 아예 없거나 중지됨
        log "❌ Bot 컨테이너 중지됨!"
        send_telegram "Bot 컨테이너 중지 감지, 재시작 시도..." "critical"
        
        cd /Users/ria_home/.openclaw/workspace/dg_bybit
        docker-compose restart bot
        sleep 15
        
        if docker ps | grep -q "cbgb-bot"; then
            send_telegram "✅ Bot 재시작 성공" "info"
        else
            send_telegram "🚨 Bot 재시작 실패!" "critical"
        fi
    elif docker ps | grep "cbgb-bot" | grep -q "unhealthy"; then
        # unhealthy 상태만 재시작
        log "⚠️ Bot 컨테이너 unhealthy!"
        send_telegram "Bot unhealthy 감지, 재시작..." "warning"
        
        cd /Users/ria_home/.openclaw/workspace/dg_bybit
        docker-compose restart bot
        sleep 15
        
        if docker ps | grep -q "cbgb-bot.*healthy"; then
            send_telegram "✅ Bot 재시작 성공" "info"
        fi
    fi
}

check_bot_errors() {
    # 마지막 1분간 로그 체크
    RECENT_LOGS=$(docker logs cbgb-bot --since 1m 2>&1)
    
    # 실제 에러만 감지
    CRITICAL_ERRORS=$(echo "$RECENT_LOGS" | grep -E " - (ERROR|CRITICAL) - |Traceback|Exception:|🚨 HALT" | grep -v "Halt: None")
    
    if [ ! -z "$CRITICAL_ERRORS" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] CRITICAL ERROR:" >> "$ERROR_LOG"
        echo "$CRITICAL_ERRORS" >> "$ERROR_LOG"
        echo "---" >> "$ERROR_LOG"
        
        # 에러 타입 추출
        if echo "$CRITICAL_ERRORS" | grep -q "UnboundLocalError"; then
            ERROR_TYPE="UnboundLocalError"
        elif echo "$CRITICAL_ERRORS" | grep -q "🚨 HALT"; then
            ERROR_TYPE="HALT"
        else
            ERROR_TYPE="ERROR"
        fi
        
        FIRST_ERROR=$(echo "$CRITICAL_ERRORS" | head -1 | cut -c1-100)
        
        log "🚨 에러: $ERROR_TYPE"
        send_telegram "🔥 Bot Error\nType: ${ERROR_TYPE}\n\`${FIRST_ERROR}\`" "critical"
    fi
}

check_liquidation_risk() {
    # 포지션 정보 추출
    POSITION_INFO=$(docker logs cbgb-bot --tail 200 2>&1 | grep "Position recovered" | tail -1)
    
    if [ -z "$POSITION_INFO" ]; then
        # 포지션 없음
        return
    fi
    
    # 진입가 추출 (예: "Sell 3 contracts @ $70076.10")
    ENTRY_PRICE=$(echo "$POSITION_INFO" | grep -oE '\$[0-9]+\.[0-9]+' | tr -d '$')
    DIRECTION=$(echo "$POSITION_INFO" | grep -oE 'Sell|Buy')
    
    if [ -z "$ENTRY_PRICE" ]; then
        return
    fi
    
    # 현재가 추출 (최근 market data)
    CURRENT_PRICE=$(docker logs cbgb-bot --tail 50 2>&1 | grep "mark_price" | tail -1 | grep -oE 'mark_price=\$[0-9,]+\.[0-9]+' | grep -oE '[0-9,]+\.[0-9]+' | tr -d ',')
    
    if [ -z "$CURRENT_PRICE" ]; then
        return
    fi
    
    # Python으로 청산 거리 계산
    LIQUIDATION_INFO=$(python3 << PYEOF
entry = float("$ENTRY_PRICE")
current = float("$CURRENT_PRICE")
leverage = 5
direction = "$DIRECTION"

if direction == "Sell":  # SHORT
    liq_price = entry * (1 + 1/leverage)
    liq_distance_pct = ((liq_price - current) / current) * 100
else:  # LONG
    liq_price = entry * (1 - 1/leverage)
    liq_distance_pct = ((current - liq_price) / current) * 100

print(f"{liq_price:.2f}|{liq_distance_pct:.2f}")
PYEOF
)
    
    LIQ_PRICE=$(echo "$LIQUIDATION_INFO" | cut -d'|' -f1)
    LIQ_DISTANCE=$(echo "$LIQUIDATION_INFO" | cut -d'|' -f2)
    
    # 청산 거리에 따라 알림
    if (( $(echo "$LIQ_DISTANCE < 10" | bc -l) )); then
        # 🔴 위험 (10% 이하)
        log "🔴 청산 위험! 거리: ${LIQ_DISTANCE}%"
        send_telegram "🔴 *청산 위험!*\n현재가: \$${CURRENT_PRICE}\n청산가: \$${LIQ_PRICE}\n거리: ${LIQ_DISTANCE}%" "critical"
    elif (( $(echo "$LIQ_DISTANCE < 15" | bc -l) )); then
        # 🟡 주의 (15% 이하)
        log "🟡 청산 주의! 거리: ${LIQ_DISTANCE}%"
        send_telegram "🟡 *청산 주의*\n거리: ${LIQ_DISTANCE}% (15% 이하)" "warning"
    else
        # 🟢 안전
        log "🟢 청산 안전: ${LIQ_DISTANCE}%"
    fi
}

check_position_health() {
    # Equity & Stop Loss 정보
    EQUITY=$(docker logs cbgb-bot --tail 50 2>&1 | grep "Equity:" | tail -1 | grep -oE '\$[0-9]+\.[0-9]+')
    STOP_LOSS=$(docker logs cbgb-bot --tail 50 2>&1 | grep "Stop Loss set:" | tail -1 | grep -oE '\$[0-9,]+\.[0-9]+')
    
    if [ ! -z "$EQUITY" ]; then
        log "💰 Equity: $EQUITY | SL: $STOP_LOSS"
    fi
}

# 시작 알림
send_telegram "🚀 모니터링 FINAL v5.0\n✅ 에러 감지\n✅ 청산 감지\n간격: ${CHECK_INTERVAL}초" "info"
log "=== CBGB 모니터링 FINAL v5.0 시작 ==="

# 메인 루프
while true; do
    check_containers
    check_bot_errors
    check_liquidation_risk  # 청산 감지 추가!
    check_position_health
    
    sleep $CHECK_INTERVAL
done
