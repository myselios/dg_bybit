#!/bin/bash
# cron_watchdog.sh — cron 전용 봇 상태 체크
# crontab: 0 * * * * /home/selios/dg_bybit/scripts/cron_watchdog.sh

set -uo pipefail

BOT_TOKEN="7994781864:AAGGRPvCwr5fJtmRU143MVfRJZUHU6GtNVE"
CHAT_ID="2128418205"
CONTAINER="cbgb-bot"
LOG="/home/selios/dg_bybit/logs/watchdog_cron.log"
DOCKER="/usr/bin/docker"

NOW=$(date '+%Y-%m-%d %H:%M:%S KST')

send() {
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="${CHAT_ID}" \
        -d text="$1" \
        -d parse_mode="Markdown" > /dev/null 2>&1
}

log() { echo "[${NOW}] $1" >> "$LOG"; }

# 1) 컨테이너 상태 확인
STATUS=$("$DOCKER" inspect --format='{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "not_found")
HEALTH=$("$DOCKER" inspect --format='{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "unknown")

if [ "$STATUS" = "not_found" ]; then
    log "CRITICAL — container not found"
    send "🚨 *CBGB 봇 없음*

컨테이너가 존재하지 않습니다.
직접 재시작이 필요합니다.
시각: ${NOW}"
    exit 1
fi

if [ "$STATUS" != "running" ]; then
    log "CRITICAL — status=${STATUS}"
    send "🚨 *CBGB 봇 다운*

상태: \`${STATUS}\`
시각: ${NOW}"
    exit 1
fi

if [ "$HEALTH" = "unhealthy" ]; then
    LAST_LOG=$("$DOCKER" logs "$CONTAINER" --tail 3 2>&1 | tr '\n' ' ' | cut -c1-200)
    log "UNHEALTHY — $LAST_LOG"
    send "⚠️ *CBGB 봇 unhealthy*

마지막 로그:
\`${LAST_LOG}\`
시각: ${NOW}"
    exit 1
fi

# 2) Tick 갱신 확인 (최근 로그에 Tick이 있는지)
LAST_TICK=$("$DOCKER" logs "$CONTAINER" --tail 30 2>&1 | grep "Tick " | tail -1)
if [ -z "$LAST_TICK" ]; then
    log "WARNING — no tick in last 30 lines"
    send "⚠️ *CBGB 봇 Tick 없음*

컨테이너는 실행 중이지만 Tick 로그가 없습니다.
시각: ${NOW}"
    exit 1
fi

# 3) 정상 — 로그만 기록
TICK_NUM=$(echo "$LAST_TICK" | grep -oP 'Tick \K[0-9]+' || echo "?")
TRADES=$(echo "$LAST_TICK" | grep -oP 'trades: \K[0-9]+/[0-9]+' || echo "?")
log "OK — status=running health=${HEALTH} tick=#${TICK_NUM} trades=${TRADES}"
