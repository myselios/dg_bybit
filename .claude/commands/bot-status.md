봇 상태를 확인한다.

1. `docker ps` — 컨테이너 상태 (cbgb-bot, cbgb-dashboard, cbgb-analysis)
2. `docker logs cbgb-bot --tail 20` — 최근 봇 로그
3. 상태 요약: State, Halt, Tick, trades, API 상태
4. 이상 감지 시 원인 분석 + 권장 조치 제시
