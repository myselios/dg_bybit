#!/bin/bash
# scripts/watchdog.sh
# 봇 상태 감시: 정상 거래대기 vs 공회전 vs 멈춤 판별
# 사용법: ./scripts/watchdog.sh [--loop]
#   --loop: 60초마다 반복 실행

set -euo pipefail

# 색상
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

CONTAINER="cbgb-bot"
ALERT_COOLDOWN=300  # 5분 쿨다운 (동일 알림 반복 방지)
ALERT_STATE_FILE="/tmp/watchdog_last_alert"

# Telegram 알림 전송
send_telegram() {
    local message="$1"
    local severity="${2:-WARNING}"  # WARNING or CRITICAL

    # 환경변수 확인
    local token="${TELEGRAM_BOT_TOKEN:-}"
    local chat_id="${TELEGRAM_CHAT_ID:-}"

    if [ -z "$token" ] || [ -z "$chat_id" ]; then
        echo -e "${YELLOW}⚠️  Telegram 미설정 (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID)${NC}"
        return 0
    fi

    # 쿨다운 체크 (동일 severity 5분 내 재전송 방지)
    local state_key="${ALERT_STATE_FILE}_${severity}"
    if [ -f "$state_key" ]; then
        local last_alert
        last_alert=$(cat "$state_key")
        local now
        now=$(date +%s)
        local elapsed=$((now - last_alert))
        if [ "$elapsed" -lt "$ALERT_COOLDOWN" ]; then
            echo -e "${YELLOW}  (Telegram 쿨다운 중: ${elapsed}/${ALERT_COOLDOWN}초)${NC}"
            return 0
        fi
    fi

    # Telegram 전송
    local emoji="⚠️"
    [ "$severity" = "CRITICAL" ] && emoji="🚨"

    local text="${emoji} *Watchdog Alert*%0A${message}"

    curl -s -X POST "https://api.telegram.org/bot${token}/sendMessage" \
        -d "chat_id=${chat_id}" \
        -d "text=${text}" \
        -d "parse_mode=Markdown" \
        > /dev/null 2>&1 && {
        echo -e "${GREEN}  ✅ Telegram 알림 전송 완료 (${severity})${NC}"
        date +%s > "$state_key"
    } || {
        echo -e "${RED}  ❌ Telegram 전송 실패${NC}"
    }
}

check_bot() {
    echo "========================================"
    echo -e "${CYAN}🔍 CBGB Bot Watchdog$(date +'  %Y-%m-%d %H:%M:%S')${NC}"
    echo "========================================"

    # 1) 컨테이너 실행 여부
    status=$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "not_found")
    if [ "$status" != "running" ]; then
        echo -e "${RED}❌ 컨테이너 상태: $status (실행 중 아님)${NC}"
        send_telegram "컨테이너 중단: ${CONTAINER} (${status})" "CRITICAL"
        return 1
    fi
    health=$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "unknown")
    echo -e "${GREEN}✅ 컨테이너: running (health: $health)${NC}"

    # 2) 최근 로그에서 Tick 추출 (마지막 20줄)
    last_logs=$(docker logs "$CONTAINER" --tail 20 2>&1)
    last_tick_line=$(echo "$last_logs" | grep "Tick " | tail -1)

    if [ -z "$last_tick_line" ]; then
        echo -e "${RED}❌ Tick 로그 없음 — 봇이 멈춘 상태${NC}"
        send_telegram "Tick 로그 없음: 봇이 멈춘 상태" "CRITICAL"
        return 1
    fi

    # Tick 번호 & 시간 추출
    tick_num=$(echo "$last_tick_line" | grep -oP 'Tick \K[0-9]+')
    tick_time=$(echo "$last_tick_line" | grep -oP '^\K[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}')
    trades_info=$(echo "$last_tick_line" | grep -oP 'trades: \K[0-9]+/[0-9]+')

    # 마지막 Tick 시간과 현재 시간 차이 (초)
    # Docker 로그는 UTC, 호스트는 로컬 시간 → UTC로 통일 비교
    tick_epoch=$(date -u -d "$tick_time" +%s 2>/dev/null || echo 0)
    now_epoch=$(date -u +%s)
    lag=$((now_epoch - tick_epoch))

    echo -e "  Tick: ${CYAN}#$tick_num${NC}  시간: $tick_time  거래: $trades_info"

    if [ "$lag" -gt 60 ]; then
        echo -e "${RED}❌ 마지막 Tick ${lag}초 전 — 봇 응답 없음${NC}"
    elif [ "$lag" -gt 10 ]; then
        echo -e "${YELLOW}⚠️  마지막 Tick ${lag}초 전 — 약간 지연${NC}"
    else
        echo -e "${GREEN}✅ Tick 활성 (${lag}초 전)${NC}"
    fi

    # 3) State 확인
    state_line=$(echo "$last_logs" | grep "State:" | tail -1)
    if [ -n "$state_line" ]; then
        state=$(echo "$state_line" | grep -oP 'State\.\K[A-Z_]+')
        halt=$(echo "$state_line" | grep -oP 'Halt: \K\S+')
        echo -e "  상태: ${CYAN}$state${NC}  Halt: $halt"

        if [ "$halt" != "None" ]; then
            echo -e "${RED}🚨 HALT 상태 — 수동 개입 필요${NC}"
        fi
    fi

    # 4) API 응답 확인 (최근 100줄에서 마지막 API 호출)
    api_line=$(docker logs "$CONTAINER" --tail 100 2>&1 | grep "API Response" | tail -1)
    if [ -n "$api_line" ]; then
        api_time=$(echo "$api_line" | grep -oP '^\K[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}')
        api_epoch=$(date -u -d "$api_time" +%s 2>/dev/null || echo 0)
        api_lag=$((now_epoch - api_epoch))
        ret_code=$(echo "$api_line" | grep -oP 'retCode=\K[0-9]+')

        if [ "$api_lag" -gt 120 ]; then
            echo -e "${RED}❌ API 호출 ${api_lag}초 전 — 마켓 데이터 갱신 안 됨${NC}"
        else
            echo -e "${GREEN}✅ API 활성 (${api_lag}초 전, retCode=$ret_code)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  최근 API 호출 기록 없음${NC}"
    fi

    # 5) 에러/경고 카운트 (최근 500줄)
    recent=$(docker logs "$CONTAINER" --tail 500 2>&1)
    error_count=$(echo "$recent" | grep -c "ERROR" || true)
    warning_count=$(echo "$recent" | grep -c "WARNING\|Warning" || true)
    fill_count=$(echo "$recent" | grep -c "FILL" || true)
    signal_count=$(echo "$recent" | grep -c "Signal\|signal" || true)

    echo ""
    echo "  최근 500줄 요약:"
    if [ "$error_count" -gt 0 ]; then
        echo -e "    ${RED}ERROR: $error_count건${NC}"
        # 마지막 에러 표시
        last_error=$(echo "$recent" | grep "ERROR" | tail -1 | cut -c1-120)
        echo -e "    ${RED}  └ $last_error${NC}"
    else
        echo -e "    ${GREEN}ERROR: 0건${NC}"
    fi
    echo "    WARNING: ${warning_count}건  |  FILL: ${fill_count}건  |  Signal: ${signal_count}건"

    # 6) 판정 + Telegram 알림
    echo ""
    echo "----------------------------------------"
    if [ "$lag" -gt 60 ]; then
        echo -e "${RED}🔴 판정: 봇 멈춤 (Tick 갱신 없음)${NC}"
        send_telegram "봇 멈춤: 마지막 Tick ${lag}초 전%0ATick #${tick_num}" "CRITICAL"
    elif [ "$halt" != "None" ] 2>/dev/null; then
        echo -e "${RED}🔴 판정: HALT 상태 (수동 복구 필요)${NC}"
        send_telegram "HALT 상태 감지%0AReason: ${halt}%0ATick #${tick_num}" "CRITICAL"
    elif [ "$error_count" -gt 10 ]; then
        echo -e "${YELLOW}🟡 판정: 에러 다발 (확인 필요)${NC}"
        send_telegram "에러 다발: ${error_count}건 (최근 500줄)%0ATick #${tick_num}" "WARNING"
    elif [ "$fill_count" -eq 0 ] && [ "$signal_count" -eq 0 ]; then
        echo -e "${YELLOW}🟡 판정: 정상 대기 중 (신호/체결 없음)${NC}"
    else
        echo -e "${GREEN}🟢 판정: 정상 운영 중${NC}"
    fi
    echo "========================================"
    echo ""
}

# 메인
if [ "${1:-}" = "--loop" ]; then
    while true; do
        check_bot || true
        sleep 60
    done
else
    check_bot
fi
