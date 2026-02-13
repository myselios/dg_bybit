#!/bin/bash
# docker/docker-entrypoint.sh
# Phase 14b (Dockerization) Phase 1: Docker 진입점 스크립트
# 역할:
# - 환경변수 로드 (.env 파일)
# - 필수 환경변수 검증
# - 유연한 명령어 실행 (exec "$@")

set -e  # 에러 발생 시 즉시 중단

# ============================================================
# 1. 환경변수 로드
# ============================================================
echo "🔧 Docker Entrypoint: Loading environment variables..."

# .env 파일이 있으면 로드 (docker-compose가 주입하지 않은 경우)
if [ -f /app/.env ]; then
    echo "📄 Loading /app/.env"
    export $(grep -v '^#' /app/.env | xargs)
elif [ -f /app/.env.production ]; then
    echo "📄 Loading /app/.env.production"
    export $(grep -v '^#' /app/.env.production | xargs)
else
    echo "⚠️  No .env file found (using docker-compose env_file or environment)"
fi

# ============================================================
# 2. 필수 환경변수 검증
# ============================================================
echo "🔍 Validating required environment variables..."

# BYBIT_TESTNET 검증 (true/false만 허용)
if [ -z "${BYBIT_TESTNET}" ]; then
    echo "❌ ERROR: BYBIT_TESTNET is not set"
    echo "   Set BYBIT_TESTNET=true (testnet) or BYBIT_TESTNET=false (mainnet)"
    exit 1
fi

if [ "${BYBIT_TESTNET}" != "true" ] && [ "${BYBIT_TESTNET}" != "false" ]; then
    echo "❌ ERROR: BYBIT_TESTNET must be 'true' or 'false', got: ${BYBIT_TESTNET}"
    exit 1
fi

echo "✅ BYBIT_TESTNET=${BYBIT_TESTNET}"

# API Key 검증 (Testnet/Mainnet에 따라)
if [ "${BYBIT_TESTNET}" = "true" ]; then
    if [ -z "${BYBIT_TESTNET_API_KEY}" ] || [ -z "${BYBIT_TESTNET_API_SECRET}" ]; then
        echo "❌ ERROR: BYBIT_TESTNET_API_KEY or BYBIT_TESTNET_API_SECRET is not set"
        exit 1
    fi
    echo "✅ Testnet API credentials present"
else
    if [ -z "${BYBIT_API_KEY}" ] || [ -z "${BYBIT_API_SECRET}" ]; then
        echo "❌ ERROR: BYBIT_API_KEY or BYBIT_API_SECRET is not set"
        exit 1
    fi
    echo "✅ Mainnet API credentials present"
fi

# ============================================================
# 3. 디렉토리 생성 (logs, config)
# ============================================================
echo "📁 Creating directories..."
mkdir -p /app/logs /app/config /app/docs/evidence

# ============================================================
# 4. 명령어 실행
# ============================================================
echo "🚀 Starting command: $@"
echo "=================================================="

# exec로 실행 (PID 1로 전환, 시그널 전달 보장)
exec "$@"
