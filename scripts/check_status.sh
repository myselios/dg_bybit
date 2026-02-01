#!/bin/bash
# scripts/check_status.sh
# Testnet 실행 상태를 한눈에 보여주는 간단한 요약 도구

LOG_FILE="logs/testnet_dry_run/testnet_dry_run.log"
TRADE_LOG_DIR="logs/testnet_dry_run"

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

clear
echo "================================================="
echo "📊 Testnet 상태 요약"
echo "================================================="
echo ""

# 1. 실행 상태 확인
if [ -f "$LOG_FILE" ]; then
    echo -e "${GREEN}✅ 실행 상태:${NC} Testnet 실행 중 또는 실행 완료"

    # 최근 업데이트 시간
    last_update=$(stat -c %y "$LOG_FILE" | cut -d'.' -f1)
    echo -e "${BLUE}📅 마지막 업데이트:${NC} $last_update"
else
    echo -e "${RED}❌ 실행 상태:${NC} Testnet 미실행"
    echo ""
    echo "실행 방법:"
    echo "  python scripts/run_testnet_dry_run.py --target-trades 5"
    exit 0
fi

echo ""

# 2. 거래 통계
if [ -f "$LOG_FILE" ]; then
    total_trades=$(grep -c "Cycle.*complete" "$LOG_FILE" 2>/dev/null || echo "0")
    successful=$(grep -c "PnL: \\\$[0-9]" "$LOG_FILE" 2>/dev/null || echo "0")
    losses=$(grep -c "PnL: \\\$-" "$LOG_FILE" 2>/dev/null || echo "0")
    halts=$(grep -c "HALT" "$LOG_FILE" 2>/dev/null || echo "0")

    echo "================================================="
    echo "📈 거래 통계"
    echo "================================================="
    echo -e "${BLUE}총 거래:${NC} $total_trades"
    echo -e "${GREEN}수익 거래:${NC} $successful"
    echo -e "${YELLOW}손실 거래:${NC} $losses"
    echo -e "${RED}정지 발생:${NC} $halts"

    # 승률 계산
    if [ "$total_trades" -gt 0 ]; then
        winrate=$(echo "scale=1; $successful * 100 / $total_trades" | bc)
        echo -e "${BLUE}승률:${NC} $winrate%"
    fi
fi

echo ""

# 3. 최근 이벤트 (최근 5개)
echo "================================================="
echo "📝 최근 이벤트 (최근 5개)"
echo "================================================="

if [ -f "$LOG_FILE" ]; then
    grep -E "(Cycle.*complete|FILL event|HALT|ERROR)" "$LOG_FILE" | tail -5 | while read line; do
        timestamp=$(echo "$line" | cut -d' ' -f1-2)

        if echo "$line" | grep -q "Cycle.*complete"; then
            pnl=$(echo "$line" | grep -oP "PnL: \\\$\K[-0-9.]+")
            if [[ $(echo "$pnl >= 0" | bc -l) -eq 1 ]]; then
                echo -e "${GREEN}[$timestamp]${NC} 거래 완료: +\$$pnl"
            else
                echo -e "${YELLOW}[$timestamp]${NC} 거래 완료: \$$pnl"
            fi
        elif echo "$line" | grep -q "FILL event"; then
            side=$(echo "$line" | grep -oP "(Buy|Sell)")
            echo -e "${BLUE}[$timestamp]${NC} $side 체결"
        elif echo "$line" | grep -q "HALT"; then
            echo -e "${RED}[$timestamp]${NC} 시스템 정지"
        elif echo "$line" | grep -q "ERROR"; then
            echo -e "${RED}[$timestamp]${NC} 오류 발생"
        fi
    done
else
    echo -e "${YELLOW}이벤트 없음${NC}"
fi

echo ""

# 4. Trade Log 파일 확인
echo "================================================="
echo "📁 Trade Log 파일"
echo "================================================="

trade_logs=$(find "$TRADE_LOG_DIR" -name "trade_log_*.jsonl" 2>/dev/null | wc -l)
if [ "$trade_logs" -gt 0 ]; then
    echo -e "${GREEN}✅ Trade Log:${NC} $trade_logs 파일 발견"

    # 최근 파일
    latest_log=$(find "$TRADE_LOG_DIR" -name "trade_log_*.jsonl" 2>/dev/null | sort -r | head -1)
    if [ -n "$latest_log" ]; then
        log_count=$(wc -l < "$latest_log" 2>/dev/null || echo "0")
        echo -e "${BLUE}📄 최근 로그:${NC} $(basename "$latest_log") ($log_count 거래)"
    fi
else
    echo -e "${YELLOW}⚠️ Trade Log:${NC} 파일 없음"
fi

echo ""

# 5. 에러/경고 확인
echo "================================================="
echo "⚠️ 에러/경고 확인"
echo "================================================="

if [ -f "$LOG_FILE" ]; then
    error_count=$(grep -c "ERROR" "$LOG_FILE" 2>/dev/null || echo "0")
    warning_count=$(grep -c "WARNING" "$LOG_FILE" 2>/dev/null || echo "0")

    if [ "$error_count" -gt 0 ]; then
        echo -e "${RED}❌ 에러:${NC} $error_count 건"
        echo "최근 에러:"
        grep "ERROR" "$LOG_FILE" | tail -3 | while read line; do
            msg=$(echo "$line" | grep -oP "ERROR - \K.*")
            echo -e "  ${RED}▶${NC} $msg"
        done
    else
        echo -e "${GREEN}✅ 에러:${NC} 없음"
    fi

    if [ "$warning_count" -gt 0 ]; then
        echo -e "${YELLOW}⚠️ 경고:${NC} $warning_count 건"
    else
        echo -e "${GREEN}✅ 경고:${NC} 없음"
    fi
else
    echo -e "${YELLOW}로그 파일 없음${NC}"
fi

echo ""
echo "================================================="
echo "💡 팁: 실시간 모니터링"
echo "================================================="
echo "  ./scripts/monitor_testnet.sh"
echo ""
