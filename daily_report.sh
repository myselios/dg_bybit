#!/bin/bash
# Daily Trading Report

TELEGRAM_BOT_TOKEN="7994781864:AAGGRPvCwr5fJtmRU143MVfRJZUHU6GtNVE"
TELEGRAM_CHAT_ID="2128418205"

send_telegram() {
    local message="$1"
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d text="${message}" \
        -d parse_mode="Markdown" > /dev/null 2>&1
}

# 로그에서 정보 추출
LOGS=$(docker logs cbgb-bot --since 24h 2>&1)

# Equity 추출
CURRENT_EQUITY=$(echo "$LOGS" | grep "Equity:" | tail -1 | grep -oE '[0-9]+\.[0-9]+')

# Tick 수 계산 (대략적인 활동량)
TICK_COUNT=$(echo "$LOGS" | grep -c "🔄 Tick")

# 에러 수
ERROR_COUNT=$(echo "$LOGS" | grep -ci "error")

# 거래 수
TRADE_COUNT=$(echo "$LOGS" | grep -c "trades:")

# 리포트 생성
REPORT="📊 *CBGB 일일 리포트*
━━━━━━━━━━━━━━━━━
💰 현재 Equity: \$${CURRENT_EQUITY}
🔄 총 Tick: ${TICK_COUNT}
📈 거래 수: ${TRADE_COUNT}
⚠️ 에러 수: ${ERROR_COUNT}

⏰ 보고 시각: $(date '+%Y-%m-%d %H:%M')
━━━━━━━━━━━━━━━━━
🚀 5배 레버리지 전략 실행 중
🎯 목표: \$100 → \$1,000 (한 달)"

send_telegram "$REPORT"
echo "Daily report sent!"
