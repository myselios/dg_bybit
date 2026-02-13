#!/bin/bash
# scripts/watchdog-service-install.sh
# Watchdog systemd service 설치 스크립트
# 사용법: sudo bash scripts/watchdog-service-install.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="cbgb-watchdog"

# .env에서 Telegram 환경변수 로드
ENV_FILE="${PROJECT_DIR}/.env"

echo "📦 CBGB Watchdog Service 설치"
echo "  프로젝트: ${PROJECT_DIR}"
echo "  서비스명: ${SERVICE_NAME}"

# systemd service 파일 생성
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << UNIT
[Unit]
Description=CBGB Bot Watchdog (Telegram Alert)
After=docker.service
Requires=docker.service

[Service]
Type=simple
EnvironmentFile=-${ENV_FILE}
ExecStart=${PROJECT_DIR}/scripts/watchdog.sh --loop
Restart=always
RestartSec=30
User=$(whoami)

# 로그
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
UNIT

# 서비스 활성화 및 시작
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl start "${SERVICE_NAME}"
systemctl status "${SERVICE_NAME}" --no-pager

echo ""
echo "✅ Watchdog 서비스 설치 완료"
echo ""
echo "관리 명령어:"
echo "  systemctl status ${SERVICE_NAME}    # 상태 확인"
echo "  journalctl -u ${SERVICE_NAME} -f    # 로그 확인"
echo "  systemctl restart ${SERVICE_NAME}   # 재시작"
echo "  systemctl stop ${SERVICE_NAME}      # 중지"
