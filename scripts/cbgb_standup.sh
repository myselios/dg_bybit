#!/bin/bash
set -euo pipefail

export PATH="/home/selios/.nvm/versions/node/v24.12.0/bin:$PATH"

MODE=${1:-standup}
CBGB_DIR="/home/selios/dg_bybit"
LOG_DIR="$CBGB_DIR/logs/standup"
PROMPT_DIR="$CBGB_DIR/scripts/prompts"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
TODAY=$(date '+%Y-%m-%d %H:%M KST')

mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/cbgb_${MODE}_$(date '+%Y-%m-%d').log"
PROMPT_FILE="$PROMPT_DIR/cbgb_${MODE}.md"

echo "[$TIMESTAMP] START: cbgb_standup mode=$MODE" >> "$LOG_FILE"

if [ ! -f "$PROMPT_FILE" ]; then
    echo "[$TIMESTAMP] ERROR: prompt not found: $PROMPT_FILE" >> "$LOG_FILE"
    exit 1
fi

PROMPT="오늘 날짜 및 시각: ${TODAY}
프로젝트 경로: ${CBGB_DIR}

$(cat $PROMPT_FILE)"

cd "$CBGB_DIR"

result=$(claude --print --dangerously-skip-permissions -p "$PROMPT" 2>> "$LOG_FILE")

echo "[$TIMESTAMP] DONE: $result" >> "$LOG_FILE"
echo "[$TIMESTAMP] END: cbgb_standup mode=$MODE" >> "$LOG_FILE"
