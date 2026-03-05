#!/bin/bash
# Quick Status Check

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 CBGB 트레이딩 봇 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 컨테이너 상태
echo ""
echo "📦 컨테이너 상태:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep cbgb

# 최근 로그
echo ""
echo "📊 최근 활동 (최근 5 Tick):"
docker logs cbgb-bot --tail 100 2>&1 | grep "🔄 Tick" | tail -5

# 포지션 정보
echo ""
echo "💰 포지션 정보:"
docker logs cbgb-bot --tail 200 2>&1 | grep -E "Position recovered|Equity:|Mark price" | tail -5

# 에러 체크
echo ""
echo "⚠️ 최근 에러 (있을 경우):"
ERRORS=$(docker logs cbgb-bot --since 5m 2>&1 | grep -i error | tail -3)
if [ -z "$ERRORS" ]; then
    echo "✅ 에러 없음"
else
    echo "$ERRORS"
fi

# 대시보드 URL
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 대시보드: http://localhost:8501"
echo "📝 로그: docker logs cbgb-bot -f"
echo "🔍 모니터링 로그: tail -f /Users/ria_home/.openclaw/workspace/dg_bybit/logs/monitor.log"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
