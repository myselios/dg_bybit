#!/bin/bash
# scripts/monitor_testnet.sh
# Testnet 실행 상태를 실시간으로 간단하게 보여주는 모니터링 도구

LOG_FILE="logs/testnet_dry_run/testnet_dry_run.log"

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "================================================="
echo "🚀 Testnet 모니터링 대시보드"
echo "================================================="
echo ""

# 로그 파일이 생성될 때까지 대기
while [ ! -f "$LOG_FILE" ]; do
    echo "⏳ Testnet 시작 대기 중..."
    sleep 2
done

echo "✅ Testnet 실행 감지! 실시간 모니터링 시작..."
echo ""

# 실시간 모니터링 (핵심 이벤트만 추출)
tail -f "$LOG_FILE" | while read line; do
    # 시작 메시지
    if echo "$line" | grep -q "Starting Testnet Dry-Run"; then
        echo -e "${GREEN}[시작]${NC} Testnet 실행 시작"
    fi

    # 초기 잔고
    if echo "$line" | grep -q "Initial equity"; then
        equity=$(echo "$line" | grep -oP '\$\K[0-9.]+')
        echo -e "${BLUE}[잔고]${NC} 초기 잔고: \$$equity"
    fi

    # Entry 주문
    if echo "$line" | grep -q "Order placed:"; then
        side=$(echo "$line" | grep -oP "(Buy|Sell)")
        qty=$(echo "$line" | grep -oP "[0-9.]{6,10} BTC")
        echo -e "${GREEN}[진입]${NC} $side 주문 발주: $qty"
    fi

    # FILL 이벤트
    if echo "$line" | grep -q "FILL event received"; then
        side=$(echo "$line" | grep -oP "(Buy|Sell)")
        qty=$(echo "$line" | grep -oP "[0-9.]{6,10} BTC")
        price=$(echo "$line" | grep -oP "@\\s*\\\$\\K[0-9,]+")
        echo -e "${GREEN}[체결]${NC} $side $qty 체결 완료 @ \$$price"
    fi

    # Cycle 완료 (거래 성공)
    if echo "$line" | grep -q "Cycle.*complete"; then
        cycle=$(echo "$line" | grep -oP "Cycle \K[0-9]+")
        pnl=$(echo "$line" | grep -oP "PnL: \\\$\K[-0-9.]+")
        if [[ $(echo "$pnl >= 0" | bc -l) -eq 1 ]]; then
            echo -e "${GREEN}[성공]${NC} 거래 #$cycle 완료 | 수익: \$$pnl ✅"
        else
            echo -e "${YELLOW}[손실]${NC} 거래 #$cycle 완료 | 손실: \$$pnl"
        fi
    fi

    # Stop loss hit
    if echo "$line" | grep -q "Stop loss hit"; then
        echo -e "${YELLOW}[정지]${NC} Stop loss 발동"
    fi

    # HALT 발생
    if echo "$line" | grep -q "HALT"; then
        reason=$(echo "$line" | grep -oP "HALT: \K.*" || echo "Unknown")
        echo -e "${RED}[중단]${NC} 시스템 정지: $reason ⚠️"
    fi

    # Session Risk 경고
    if echo "$line" | grep -q "session_risk"; then
        echo -e "${RED}[위험]${NC} Session Risk 발동 🚨"
    fi

    # 에러 메시지
    if echo "$line" | grep -q "ERROR"; then
        error=$(echo "$line" | grep -oP "ERROR - \K.*")
        echo -e "${RED}[오류]${NC} $error"
    fi

    # 요약 통계
    if echo "$line" | grep -q "Summary"; then
        echo ""
        echo "================================================="
        echo -e "${BLUE}📊 최종 통계 요약${NC}"
        echo "================================================="
    fi

    if echo "$line" | grep -q "Total trades:"; then
        total=$(echo "$line" | grep -oP "Total trades: \K[0-9]+")
        echo -e "${BLUE}총 거래:${NC} $total"
    fi

    if echo "$line" | grep -q "Successful cycles:"; then
        success=$(echo "$line" | grep -oP "Successful cycles: \K[0-9]+")
        echo -e "${GREEN}성공:${NC} $success"
    fi

    if echo "$line" | grep -q "Stop loss hits:"; then
        stops=$(echo "$line" | grep -oP "Stop loss hits: \K[0-9]+")
        echo -e "${YELLOW}손절:${NC} $stops"
    fi

    if echo "$line" | grep -q "Session Risk halts:"; then
        halts=$(echo "$line" | grep -oP "Session Risk halts: \K[0-9]+")
        echo -e "${RED}정지:${NC} $halts"
    fi
done
