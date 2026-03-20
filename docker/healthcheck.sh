#!/bin/bash
# docker/healthcheck.sh
# Bot healthcheck: log file freshness check
# Fails if mainnet.log has not been written to in the last 120 seconds.

LOG_FILE="/app/logs/mainnet/mainnet.log"

if [ ! -f "$LOG_FILE" ]; then
    exit 1
fi

LAST_MODIFIED=$(stat -c %Y "$LOG_FILE" 2>/dev/null || echo 0)
NOW=$(date +%s)
AGE=$((NOW - LAST_MODIFIED))

if [ "$AGE" -gt 120 ]; then
    exit 1
fi

exit 0
