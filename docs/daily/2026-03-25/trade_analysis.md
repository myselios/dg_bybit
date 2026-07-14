# 트레이드 분석 — 2026-03-24

## 트레이드 요약

| 항목 | 값 |
|------|-----|
| 날짜 | 2026-03-24 |
| 총 트레이드 수 | 1 |
| 방향 | LONG |
| 진입가 | $68,947.6 |
| 청산가 | $69,493.2 |
| 수량 | 0.003 BTC |
| Realized PnL | +$1.6368 |
| 수수료 | $0.1147 |
| 순 PnL | +$1.5221 |
| 마켓 레짐 | ranging |

## 신호 품질

| 항목 | 값 |
|------|-----|
| signal_score | 4 / 7 (진입 임계값 ≥4 충족) |
| rsi | +2 |
| macd | 0 |
| bb | +1 |
| volume | +1 |
| ma_slope | 0 |
| breakout | 0 |

**분석**: RSI + BB + Volume 3개 컴포넌트 활성화로 최소 score=4 달성. MACD/ma_slope/breakout 비기여. ranging 레짐에서도 threshold=5(Wave 6 설정) 미만이지만, ranging 레짐의 경우 별도 경로로 진입된 것으로 추정 — 확인 필요.

## 수수료 분석

| 항목 | 값 |
|------|-----|
| fee_usd (실측) | $0.11466378 |
| 진입가 기준 계산 | 0.003 BTC × $68,947.6 × 요율 |
| 추정 fee rate | ~0.055% (Taker 요율 적용됨) |

**Post-Only 적용 여부 (git_commit=dfc513501eba 기준)**:
- 수수료율 ~0.055%는 **Taker fee** 수준
- Maker fee = 0.01%, Taker fee = 0.055%
- 청산(EXIT) 주문에서 발생한 수수료이므로, Wave 5에서 추가된 Post-Only는 진입(ENTRY)에만 적용됨
- EXIT 시장가 청산 → Taker fee 정상 적용
- **결론**: Post-Only 미적용 대상(EXIT)에서 정상 Taker fee 발생. 이상 없음.

## 버그 발견 (Wave 7 수정 대상)

### BUG-1: hold_seconds 음수 (ms vs s 단위 불일치) — CRITICAL

```
entry_time: 1774374327646.0   ← milliseconds (Unix ms timestamp)
exit_time:  1774377743.1409247 ← seconds (Unix s timestamp)
hold_seconds: -1772599949902.8591 ← 오버플로우로 음수 발생
```

**원인**: `entry_time`은 ms 단위, `exit_time`은 s 단위로 기록됨.
`hold_seconds = exit_time - entry_time` 계산 시 단위 불일치로 음수 발생.

**수정 방향**:
- `entry_time`을 ms → s 변환 후 계산: `hold_seconds = exit_time - (entry_time / 1000)`
- 또는 두 값을 ms 단위로 통일

**수정 시 예상 hold_seconds**: `1774377743.14 - 1774374327.646 = 3415.5초 (약 56.9분)` — 합리적인 값.

### BUG-2: git_commit 구버전 (태스크 1에서 수정 완료)

```
git_commit: "dfc513501eba"  ← Wave 6 이전 코드
현재 HEAD:  "9af266cd2d35c771d48b4c84c30ada4469bc6a14"
```

**수정**: `.env`의 `GIT_COMMIT`을 현재 HEAD로 업데이트 완료.

### BUG-3: signal_reason, reflection_pattern, hypothesis, param_delta = null

Wave 2에서 ReflectionAgent 구현 완료되었으나 실제 트레이드 로그에 미기록.
Wave 7에서 ReflectionAgent 연결 상태 확인 필요.

## docker-compose.yml GIT_COMMIT 자동화 분석

**현황**: `docker-compose.yml` line 29에 `GIT_COMMIT=${GIT_COMMIT:-unknown}` 패턴 존재.
`.env` 파일에서 `GIT_COMMIT` 값을 읽어 컨테이너에 주입하는 구조.

**문제**: 배포 시 `.env`의 `GIT_COMMIT`을 수동으로 업데이트해야 함 → 누락 위험.

**자동화 권장 방안** (Makefile 또는 scripts/deploy.sh 생성 시):
```makefile
update-git-commit:
    @sed -i "s/^GIT_COMMIT=.*/GIT_COMMIT=$(shell git rev-parse HEAD)/" .env

deploy: update-git-commit
    docker compose build --no-cache bot
    docker compose up -d bot
```

`Makefile`, `scripts/deploy.sh` 미존재 — 사용자 확인 후 생성 권장.

## Wave 7 수정 우선순위

| 우선순위 | 버그 | 파일 |
|----------|------|------|
| P0 | hold_seconds ms/s 단위 불일치 | trade log 기록 코드 |
| P1 | git_commit 배포 자동화 | Makefile 또는 deploy.sh |
| P2 | ReflectionAgent null 기록 | reflection_agent 연결 확인 |
