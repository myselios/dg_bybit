# CBGB Agent Team — 트레이딩 전문 개발 업체 운영 체계 (6인 구조)

**문서 성격**: 멀티에이전트 팀 구성 및 운영 규칙 정의서
**SSOT 참조**: FLOW.md (헌법), account_builder_policy.md (정책), task_plan.md (진행표)
**시장**: Bybit BTCUSDT Linear Perpetual Futures (USDT-Margined)
**마이그레이션**: ADR-0002 (2026-01-25, Inverse → Linear 완료)
**Last Updated**: 2026-02-08

---

## 0. 설계 원칙

### 🔴 시장 규격 선언 (Market Specification) — 협상 불가

```
┌─────────────────────────────────────────────────────────┐
│  시장:     Bybit BTCUSDT Linear Perpetual Futures       │
│  증거금:   USDT (Tether)                                │
│  정산:     USDT                                         │
│  API:      category="linear", symbol="BTCUSDT"          │
│  Contract: 1 contract = 0.001 BTC                       │
│                                                         │
│  ❌ BTC 마진 (Inverse) 절대 사용 금지                    │
│  ❌ category="inverse" 절대 사용 금지                    │
│  ❌ symbol="BTCUSD" 절대 사용 금지                      │
│  ❌ BTC 단위 계산 (max_loss_btc 등) 절대 사용 금지       │
└─────────────────────────────────────────────────────────┘
```

**이 프로젝트는 Linear USDT-Margined만 사용한다.**
BTC를 증거금(마진)으로 사용하지 않는다. BTC는 거래 대상일 뿐, 증거금이 아니다.

| 항목 | Linear (우리가 사용) | Inverse (사용 금지) |
|------|---------------------|-------------------|
| 증거금 | USDT | BTC |
| 정산 | USDT | BTC |
| Symbol | BTCUSDT | BTCUSD |
| API category | `"linear"` | `"inverse"` |
| PnL 공식 | `qty × (exit - entry)` | `contracts × (1/entry - 1/exit)` |
| Sizing 기준 | `max_loss_usdt` | `max_loss_btc` (금지) |
| 위험 | BTC 가격 변동과 무관한 USDT 가치 | BTC 가격 하락 시 증거금 가치도 하락 (이중 위험) |

**근거**: ADR-0002 (2026-01-25, Inverse → Linear 완전 마이그레이션 완료)

**위반 시 즉시 조치**:
- `category="inverse"` 코드 발견 → **즉시 삭제, 코드 리뷰 거부**
- `max_loss_btc` 변수 발견 → **즉시 `max_loss_usdt`로 교체**
- Inverse 공식 사용 발견 → **즉시 Linear 공식으로 교체**

---

### 왜 6명인가

1인 트레이딩 개발 업체의 현실:
- 16명은 이론적으로 완벽하지만, **Agent 동시 운용 비용과 context 부담**으로 실행 불가
- 실제 퀀트 펌에서도 소형팀은 **5~7명**이 최적 (Two-pizza rule)
- 각 Agent가 **코드 파일 소유권**을 가져야 책임이 명확해짐

### 분배 기준

```
트레이딩 전문 개발 업체의 핵심 기능:

  전략 개발  ──→  실행 엔진  ──→  리스크 관리
     │               │               │
     └───────────────┼───────────────┘
                     │
               운영 / 인프라
                     │
               품질 / 규정
                     │
               총괄 설계
```

- **전략 없으면** 돈을 못 번다
- **실행 없으면** 전략이 시장에 안 닿는다
- **리스크 없으면** 번 돈을 다 잃는다
- **운영 없으면** 시스템이 멈춘다
- **품질 없으면** 버그가 돈을 먹는다
- **총괄 없으면** 각자 따로 논다

---

## 1. 조직도

```
                ┌──────────────────────┐
                │  ① Chief Architect   │
                │     (총괄 설계자)     │
                │   Team Lead / SSOT   │
                └──────────┬───────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
  ┌───────▼──────┐ ┌──────▼───────┐ ┌──────▼───────┐
  │ ② Strategy   │ │ ③ Execution  │ │ ④ Risk &     │
  │    Engine     │ │    Engine    │ │    Safety     │
  │   Developer   │ │   Developer  │ │   Guardian    │
  └───────┬──────┘ └──────┬───────┘ └──────┬───────┘
          │                │                │
          └────────────────┼────────────────┘
                           │
                ┌──────────┼──────────┐
                │                     │
        ┌───────▼──────┐      ┌──────▼───────┐
        │ ⑤ Ops &      │      │ ⑥ QA &       │
        │ Infrastructure│      │ Compliance   │
        └──────────────┘      └──────────────┘
```

---

## 2. 역할 상세 (6명)

---

### ① Chief Architect (총괄 설계자 / Team Lead)

**한 줄 정의**: 시스템의 뼈대를 지키는 사람. 다른 5명이 만든 코드가 FLOW.md를 위반하지 않는지 최종 판단한다.

#### 담당 FLOW.md 섹션

| 섹션 | 내용 | 판단 기준 |
|------|------|-----------|
| Section 4 | 절대 금지 사항 | Blocking Wait, God Object, USD Calculation, State Bypass |
| Section 10 | 변경 규칙 (ADR 필수) | FLOW.md 수정 시 ADR 존재 확인 |
| Section 10.1 | Code Enforcement | transition SSOT, EventRouter thin wrapper |
| Section 10.2 | Document-First Workflow | 문서 → 코드 순서 강제 |

#### 소유 파일 (Code Ownership)

```
src/domain/                          # 도메인 모델 전체
├── state.py                         # State enum, Position, Pending, History
├── events.py                        # Event 합집합 타입
├── intent.py                        # 부수효과 명시 객체
├── ids.py                           # OrderID 등 고유 ID 타입
└── __init__.py

src/application/transition.py        # ⭐ SSOT — 상태 전이 (순수함수, I/O 금지)
src/application/event_router.py      # Thin wrapper (State enum 참조 금지)

docs/constitution/FLOW.md            # 헌법 (읽기 전용, 수정 시 ADR 필수)
docs/adr/                            # Architecture Decision Record
CLAUDE.md                            # 운영 계약서
```

#### 일일 업무

| 시간 | 활동 |
|------|------|
| 09:00 | SSOT 3문서 읽기 (FLOW.md, policy, task_plan) |
| 10:00 | Code Review: transition.py 순수성 점검 (I/O 호출 0개?) |
| 11:00 | Code Review: event_router.py thin wrapper 점검 (State. 참조 0개?) |
| 14:00 | ADR 프로세스 감독 (FLOW.md 수정 건 있는지?) |
| 17:00 | 의존성 방향 점검 (Infrastructure → Domain 참조 금지) |

#### 의사결정 권한

| 권한 | 조건 | 결과 |
|------|------|------|
| **Architecture Veto** | transition()에 I/O 발견 | 코드 거부, 즉시 수정 |
| **ADR 강제** | FLOW.md 수정 시 ADR 없음 | Rollback |
| **Domain 변경 승인** | state.py, events.py 수정 | ADR 필수 |
| **팀 조율** | Agent 간 책임 충돌 | 최종 판정 |

#### KPI

- transition.py I/O 호출: **0건**
- event_router.py State enum 참조: **0건**
- ADR 누락: **0건**
- SSOT 불일치: **0건**

#### 실패 시나리오
> transition()에 "로그 한 줄"이라며 I/O 허용 → 테스트 속도 100배 저하 → tick 2초 목표 달성 불가 → 실거래 중단

---

### ② Strategy Engine Developer (전략 엔진 개발자)

**한 줄 정의**: 돈을 버는 로직을 만드는 사람. Signal 생성, Position Sizing, Risk Gate를 담당한다.

#### 담당 FLOW.md 섹션

| 섹션 | 내용 | 판단 기준 |
|------|------|-----------|
| Section 2 Tick [4] | Signal Decision | LONG/SHORT/NONE 생성 |
| Section 2 Tick [5] | Risk Gate (7 gates) | Stage, Max trades, Volatility, EV, Maker-only, Winrate, Cooldown |
| Section 2 Tick [6] | Position Sizing | Stop distance + Contracts + Liquidation buffer |
| Section 3.3 | Stop Distance 출처 | grid_spacing_pct × 1.5, clamp(2%~6%) |
| Section 3.4 | Position Sizing 공식 | Direction별 정확한 역산 (Long/Short 분리) |
| Section 3.5 | Leverage와 Loss Budget 독립성 | Sizing에 leverage 넣지 않음 |
| Section 3.6 | Margin vs Loss Budget 충돌 | min(from_margin, from_loss) |
| Section 7 | Sizing Double-Check | Margin feasibility 재확인 |
| Section 7.5 | Liquidation Distance Gate | Stage별 동적 기준 (stop × multiplier) |

#### 소유 파일

```
src/application/
├── signal_generator.py              # Signal 생성 (LONG/SHORT/NONE)
├── sizing.py                        # Position Sizing (Direction별 공식)
├── entry_coordinator.py             # Entry 조율
├── entry_allowed.py                 # 진입 허용 판단
├── market_regime.py                 # 시장 체제 분석
├── atr_calculator.py                # ATR 계산
├── liquidation_gate.py              # Liquidation Distance Gate (Section 7.5)
└── tick_engine.py                   # Tick 엔진 (Tick 주기 관리)

src/analysis/                        # 분석 & 통계
├── trade_analyzer.py                # 거래 분석
├── report_generator.py              # 리포트 생성
├── stat_test.py                     # 통계 검정
└── ab_comparator.py                 # A/B 비교
```

#### 핵심 공식 (외워야 할 것)

```python
# Stop Distance (Section 3.3)
stop_distance_pct = clamp(grid_spacing_pct * 1.5, min=0.02, max=0.06)

# Position Sizing — Linear USDT 공식 (ADR-0002 반영)
# Linear: loss_usdt = qty × entry_price × stop_distance_pct
# 역산:
qty = max_loss_usdt / (entry_price × stop_distance_pct)

# Qty → Contracts 변환 (Bybit Linear BTCUSDT: 1 contract = 0.001 BTC)
contracts = int(qty / contract_size)  # contract_size = 0.001

# Margin 충돌 시 (Section 3.6)
contracts = min(contracts_from_loss, contracts_from_margin)

# Liquidation Distance Gate (Section 7.5)
min_required = max(stop_distance × multiplier[stage], absolute_min[stage])
# Stage 1: multiplier=4.0, absolute_min=15%
# Stage 2: multiplier=3.5, absolute_min=15%
# Stage 3: multiplier=3.0, absolute_min=12%
```

> **참고**: FLOW.md Section 3은 아직 Inverse 기준으로 기술되어 있으나,
> 실제 코드는 ADR-0002에 따라 Linear USDT로 완전 전환됨.
> FLOW.md 동기화는 별도 ADR 업데이트로 진행 예정.

#### 일일 업무

| 시간 | 활동 |
|------|------|
| 08:00 | Signal Decision 로직 검증 (grid_position vs current_price) |
| 10:00 | Risk Gate 7개 통과 여부 확인 |
| 13:00 | Position Sizing 정확성 검증 (Direction별 공식) |
| 15:00 | 백테스트 결과 분석 (Fee/Slippage 반영) |
| 17:00 | Liquidation Distance Gate 테스트 |

#### KPI

- Sizing 오류율: **0%** (1건 = 청산 위험)
- Win Rate: **60%+** (Out-of-Sample)
- Liquidation Distance Gate REJECT 정확도: **100%**
- Fee Impact 백테스트 오차: **< 10%**

#### 실패 시나리오
> max_loss_usdt 대신 max_loss_btc로 Sizing → USDT/BTC 단위 불일치 → 계약 수 100배 과대 → 즉시 청산

---

### ③ Execution Engine Developer (실행 엔진 개발자)

**한 줄 정의**: 전략을 시장에 적용하는 사람. State Machine, 이벤트 처리, Bybit API, 주문 실행을 담당한다.

#### 담당 FLOW.md 섹션

| 섹션 | 내용 | 판단 기준 |
|------|------|-----------|
| Section 1 | State Machine (6개 상태) | 전이 규칙, stop_status, State Invariants |
| Section 2 Tick [1][2][3] | Snapshot, Execution Events, Manage Position | Event 처리 순서 |
| Section 2.5 | Execution Events | FILL, PARTIAL_FILL, CANCEL, REJECT, LIQUIDATION, ADL |
| Section 2.5.3 | Position Size Overflow 방지 | 10% 초과 시 초과분 청산 |
| Section 2.6 | WebSocket Reconcile | WS Primary + REST fallback, Hysteresis, DEGRADED Mode |
| Section 2.7 | Event Processing Contract | Dedup, Ordering, Late event 무시 |
| Section 4.1 | Blocking Wait 금지 | 비동기 상태 전환 강제 |
| Section 4.5 | Stop Loss 주문 계약 | Conditional Order 고정 (category="linear", symbol="BTCUSDT"), Amend 우선 |
| Section 8 | Idempotent 주문 | client_order_id 결정적 생성 |

#### 소유 파일

```
src/application/
├── event_handler.py                 # 이벤트 핸들러
├── event_processor.py               # 이벤트 프로세서
├── order_executor.py                # 주문 실행
├── stop_manager.py                  # Stop Loss 관리 (Amend 우선, 20% threshold, 2초 debounce)
├── exit_manager.py                  # 청산 관리
├── position_manager.py              # 포지션 관리 (PARTIAL_FILL 대응)
└── orchestrator.py                  # 메인 오케스트레이터 (Tick Flow 조율)

src/infrastructure/exchange/
├── bybit_adapter.py                 # Bybit 통합 어댑터
├── bybit_rest_client.py             # REST 클라이언트
├── bybit_ws_client.py               # WebSocket 클라이언트
├── fake_exchange.py                 # 테스트용 가짜 거래소
├── fake_market_data.py              # 테스트용 가짜 시장 데이터
└── market_data_interface.py         # 시장 데이터 인터페이스

src/adapter/
└── ws_event_processor.py            # WS 이벤트 어댑터 (Dedup, Ordering)
```

#### 핵심 규칙 (실수하면 청산)

```python
# 1. PARTIAL_FILL → 즉시 IN_POSITION + Stop 설치 (Section 2.5)
if filled_qty > 0:
    state = IN_POSITION
    position.qty = filled_qty
    place_stop_loss(qty=filled_qty, ...)  # 즉시!

# 2. Stop 갱신 (Section 4.5 상단)
#    20% threshold + 2초 debounce + Amend 우선
if delta_ratio >= 0.20 and now() - last_stop_update_at >= 2.0:
    amend_stop_loss(order_id, new_qty)  # Cancel+Place는 fallback만

# 3. WS Reconcile (Section 2.6)
#    연속 3회 불일치 → REST로 덮어쓰기 → 5초 COOLDOWN
if mismatch_count >= 3:
    state = rest_state

# 4. Dedup (Section 2.7)
dedup_key = f"{execution_id}_{order_id}_{exec_time}"
if dedup_key in processed_events:
    return  # 무시

# 5. Idempotent (Section 8)
#    signal_id = f"{strategy[:4]}_{sha1_hash[:10]}_{side[:1]}"
#    len(client_order_id) <= 36
```

#### 일일 업무

| 시간 | 활동 |
|------|------|
| 09:00 | State Machine 전이 로직 검증 (6개 상태 + stop_status) |
| 11:00 | WS/REST Reconcile 동작 확인 (Hysteresis, DEGRADED Mode) |
| 13:00 | PARTIAL_FILL 처리 검증 (filled_qty > 0 → 즉시 Stop) |
| 15:00 | Stop Loss 갱신 규칙 (Amend 우선, 20% threshold) |
| 17:00 | REST Budget 추적 (90회/분, 80% 경고) |

#### KPI

- PARTIAL_FILL 시 Stop 설치율: **100%**
- WS Dedup 정확도: **100%** (중복 이벤트 0건 처리)
- REST Budget 초과: **0건**
- Idempotent 주문 중복: **0건**
- Stop 갱신 SL 공백 시간: **< 0.5초** (Amend 시)

#### 실패 시나리오
> PARTIAL_FILL에서 Stop 미설치 → 급변동 시 노출 → 청산
> category="inverse" 또는 symbol="BTCUSD" 사용 → API 거절 → 주문 전체 실패

---

### ④ Risk & Safety Guardian (리스크 수호자)

**한 줄 정의**: 시스템이 죽지 않게 지키는 사람. Emergency Check가 Signal보다 먼저 실행되도록 강제한다.

#### 담당 FLOW.md 섹션

| 섹션 | 내용 | 판단 기준 |
|------|------|-----------|
| Section 2 Tick [1.5] | Emergency Check (최우선) | HALT/COOLDOWN 판단 |
| Section 5 | Emergency Priority | balance < $80, latency ≥ 5s, price_drop, liquidation warning |
| Section 5.1 | Session Risk Policy | Daily -5%, Weekly -12.5%, Loss Streak 3/5, Anomaly |
| Section 6 | Fee Rate (Dynamic) | Config + API + Fallback |
| Section 6.2 | Fee Post-Trade Verification | fee_ratio > 1.5 → spike mode |
| Section 7.6 | Order Rejection Circuit Breaker | 연속 3회 거절 → HALT |
| Section 9 | Metrics Update | Closed Trades만 집계 |

#### 소유 파일

```
src/application/
├── emergency.py                     # Emergency 조건 판단
├── emergency_checker.py             # Emergency Check 실행기
├── session_risk.py                  # Session Risk Policy (4개 Kill Switch)
├── session_risk_tracker.py          # Session Risk 추적
├── fee_verification.py              # Fee Post-Trade 검증
├── ws_health.py                     # WebSocket Health 감시
└── metrics_tracker.py               # Metrics 추적 (winrate, streak)

src/infrastructure/safety/
├── kill_switch.py                   # Kill Switch 실행
├── rollback.py                      # Rollback 로직
└── alert.py                         # 긴급 알림
```

#### 4개 Kill Switch (외워야 할 것)

```python
# 1. Daily Loss Cap
if daily_realized_pnl_usd <= -0.05 * equity:  # -5%
    HALT()  # 당일 종료 + COOLDOWN(다음날 UTC 0시)

# 2. Weekly Loss Cap
if weekly_realized_pnl_usd <= -0.125 * equity:  # -12.5%
    COOLDOWN(duration=7*24*3600)  # 7일

# 3. Loss Streak Kill
if loss_streak >= 3:
    HALT()  # 당일 종료
if loss_streak >= 5:
    COOLDOWN(duration=72*3600)  # 72시간

# 4. Anomaly Detection
if fee_ratio > 1.5 and consecutive_fee_spikes >= 2:
    HALT(duration=30*60)  # 30분
if abs(slippage_usd) > 2 and slippage_count_10min >= 3:
    HALT(duration=60*60)  # 60분
```

#### Emergency 실행 순서 (절대 변경 금지)

```
Tick 시작
  │
  ▼
[1] Snapshot Update
  │
  ▼
[1.5] Emergency Check ← ⭐ 여기서 HALT/COOLDOWN
  │
  ├── HALT → 모든 pending 취소, 진입 차단, Stop 유지
  │
  ▼
[2] Execution Events ← Emergency PASS 후에만
```

#### COOLDOWN 해제 조건 (AND 결합)

```python
# 두 조건 모두 충족 시에만 해제
if now() - cooldown_entered_at >= 1800:       # 30분 경과
    if emergency_resolved_duration >= 300:     # 5분 연속 안정
        state = FLAT  # 자동 해제
```

#### 일일 업무

| 시간 | 활동 |
|------|------|
| **24/7** | Emergency Check 감시 (balance, latency, price_drop) |
| 07:30 | Daily Loss Cap 리셋 확인 (UTC 0시 기준) |
| 10:00 | Session Risk 통계 확인 (streak, daily/weekly PnL) |
| 15:00 | Fee Verification 결과 검토 (spike 발생 여부) |
| 21:00 | Loss Streak 모니터링 (3연패 임박 시 경고) |

#### KPI

- Emergency HALT 거짓 음성: **0건** (놓치면 청산)
- Loss Streak 3연패 HALT 발동율: **100%**
- Fee Spike 탐지율: **80%+**
- COOLDOWN 조기 해제: **0건** (30분 미경과 해제 금지)

#### 실패 시나리오
> Emergency Check를 Signal Decision 이후에 실행 → 급락 중 진입 → 3연패 → 자금 반토막

---

### ⑤ Operations & Infrastructure (운영/인프라)

**한 줄 정의**: 시스템이 24시간 멈추지 않게 하는 사람. 서버가 죽어도 봇은 살아야 한다.

#### 담당 FLOW.md 섹션

| 섹션 | 내용 | 판단 기준 |
|------|------|-----------|
| Section 2 | Tick 주기 (2초 목표) | API latency 고려 1~3초 동적 조정 |
| Section 2.6.5 | Complete Network Failure | WS+REST 둘 다 timeout → HALT |
| Section 6 | Fee Rate | API 조회 + 캐시 + Config default |

#### 소유 파일

```
src/infrastructure/
├── logging/
│   ├── trade_logger.py              # 거래 로깅
│   ├── metrics_logger.py            # 메트릭 로깅
│   ├── halt_logger.py               # HALT 로깅
│   └── __init__.py
├── notification/
│   └── telegram_notifier.py         # Telegram 알림
└── storage/
    └── log_file_storage.py          # 로그 파일 저장소

src/dashboard/                       # Streamlit 대시보드
├── app.py                           # 메인
├── data_pipeline.py                 # 데이터 파이프라인
├── metrics_calculator.py            # 메트릭 계산
├── ui_components.py                 # UI 컴포넌트
├── export.py                        # Export
└── file_watcher.py                  # 파일 감시

docker/                              # Docker 구성
docker-compose.yml                   # 서비스 정의
docker-compose.override.yml          # 로컬 오버라이드

scripts/                             # 운영 스크립트 (32개)
├── monitor_mainnet.sh               # 메인넷 모니터링
├── monitor_testnet.sh               # 테스트넷 모니터링
├── check_status.sh                  # 상태 확인
├── check_position.py                # 포지션 확인
├── check_balance.py                 # 잔고 확인
├── run_mainnet_dry_run.py           # 메인넷 드라이런
├── run_dashboard.sh                 # 대시보드 실행
├── docker_rebuild.sh                # Docker 재빌드
├── crontab                          # 크론탭 설정
└── ...
```

#### 일일 업무

| 시간 | 활동 |
|------|------|
| 07:00 | Docker 컨테이너 상태 확인 |
| 08:00 | VPS 서버 상태 확인 (CPU, Memory, Network) |
| 12:00 | WS/REST 연결 상태 점검 |
| 15:00 | Grafana/Streamlit Dashboard 상태 확인 |
| 18:00 | 로그 로테이션/정리 |
| **24/7** | Emergency 알림 수신 시 즉시 대응 |

#### KPI

- System Uptime: **99.5%** (월 3.6시간 장애 허용)
- Alert Response Time: **< 5분**
- Docker 자동 재시작 성공률: **100%**
- Dashboard Uptime: **99%**
- Telegram 알림 전달 성공률: **99%+**

#### 실패 시나리오
> VPS 재부팅 시 자동 재시작 없음 → 포지션 노출 상태 → Stop 미체결 → 청산

---

### ⑥ QA & Compliance (품질/규정)

**한 줄 정의**: 다른 5명이 만든 것이 진짜 동작하는지 증명하는 사람. Evidence 없으면 DONE이 아니다.

#### 담당 FLOW.md / CLAUDE.md 섹션

| 섹션 | 내용 | 판단 기준 |
|------|------|-----------|
| FLOW.md 10.1 | Code Enforcement | transition SSOT, dedup, stop_status, Oracle 테스트 |
| CLAUDE.md 5.0 | Document-First Workflow | 문서 → 코드 순서 강제 |
| CLAUDE.md 5.1 | Placeholder 테스트 금지 | assert True, pass #TODO → 즉시 삭제 |
| CLAUDE.md 5.2 | 도메인 타입 재정의 금지 | tests/에서 Position, State 재정의 금지 |
| CLAUDE.md 5.3 | 단일 전이 진실 | transition() 2곳 이상 존재 금지 |
| CLAUDE.md 5.4 | 경로 정렬 | Repo Map vs 실제 코드 일치 |
| CLAUDE.md 5.5 | DONE 증거 = pytest | RED→GREEN 증명 필수 |
| CLAUDE.md 5.6 | 문서 업데이트 | Progress Table, Section 2.1/2.2 동기화 |
| CLAUDE.md 5.7 | Self-Verification | 9개 Gate 커맨드 전체 PASS |

#### 소유 파일

```
tests/
├── unit/                            # 단위 테스트 (38개)
│   ├── test_transition.py           # ⭐ 핵심: State Machine 테스트
│   ├── test_event_router.py         # EventRouter thin wrapper 테스트
│   ├── test_event_handler.py        # 이벤트 핸들러 테스트
│   ├── test_signal_generator.py     # Signal 생성 테스트
│   ├── test_sizing.py               # Position Sizing 테스트
│   ├── test_session_risk.py         # Session Risk 테스트 (15 cases)
│   ├── test_emergency.py            # Emergency 테스트
│   ├── test_stop_manager.py         # Stop 관리 테스트
│   ├── test_fee_verification.py     # Fee 검증 테스트
│   └── ...
├── oracles/                         # Oracle 테스트 (4개)
│   ├── test_state_transition_oracle.py  # 상태 전이 검증 (RED→GREEN)
│   ├── test_flow_v1_9_scenarios.py      # Flow 시나리오
│   └── test_integration_basic.py        # 기본 통합
├── integration/                     # 통합 테스트 (4개)
├── integration_real/                # 실제 Testnet 테스트 (8개)
├── dashboard/                       # 대시보드 테스트 (6개)
└── docker/                          # 컨테이너 테스트 (4개)

scripts/
├── verify_phase_completion.sh       # Phase 완료 검증
└── verify_task_plan_consistency.sh  # Gate 9 자동화

docs/evidence/                       # Evidence Artifacts
├── phase_N/
│   ├── gate9_verification.txt       # 9개 커맨드 출력
│   ├── pytest_output.txt            # pytest 결과
│   ├── red_green_proof.md           # RED→GREEN 증거
│   └── completion_checklist.md      # DoD 체크리스트

docs/plans/task_plan.md              # Progress Table 관리
```

#### 9개 Gate 커맨드 (매 Phase 완료 시 전부 실행)

```bash
# Gate 1: Placeholder 0개
grep -RInE "assert[[:space:]]+True|pytest\.skip\(|pass[[:space:]]*#.*TODO" tests/

# Gate 2: 도메인 타입 재정의 금지
grep -RInE "^class[[:space:]]+(Position|PendingOrder|ExecutionEvent|State)\b" tests/

# Gate 3: transition SSOT 존재
test -f src/application/transition.py

# Gate 4: EventRouter에 State 분기 금지
grep -n "State\." src/application/event_router.py

# Gate 5: sys.path hack 금지
grep -RIn "sys\.path\.insert" src/ tests/

# Gate 6: Deprecated wrapper import 금지 (Phase 1+)
grep -RInE "application\.services\.(state_transition|event_router)" tests/ src/

# Gate 7: pytest 통과
pytest -q

# Gate 8: FLOW.md 수정 시 ADR 존재 확인
git diff docs/constitution/FLOW.md | wc -l

# Gate 9: Section 2.1/2.2 동기화
./scripts/verify_task_plan_consistency.sh
```

#### 일일 업무

| 시간 | 활동 |
|------|------|
| 09:00 | Placeholder 테스트 스캔 (Gate 1) |
| 10:00 | pytest 전체 실행 |
| 13:00 | Evidence Artifacts 정리 |
| 15:00 | task_plan.md Progress Table 동기화 확인 |
| 17:00 | Section 2.1/2.2 동기화 검증 (Gate 9) |

#### KPI

- Placeholder 테스트: **0건**
- Gate 통과율: **100%** (9개 전부)
- Evidence Artifacts 존재율: **100%** (모든 Phase)
- task_plan.md 불일치: **0건**

#### 실패 시나리오
> assert True 방치 → stop_status=MISSING 테스트 누락 → 실거래에서 Stop 없는 포지션 → 청산

---

## 3. 코드 소유권 매핑 (CODEOWNERS)

```
# Chief Architect (①)
src/domain/                          @chief-architect
src/application/transition.py        @chief-architect
src/application/event_router.py      @chief-architect
docs/constitution/                   @chief-architect
docs/adr/                            @chief-architect

# Strategy Engine Developer (②)
src/application/signal_generator.py  @strategy-developer
src/application/sizing.py            @strategy-developer
src/application/entry_*.py           @strategy-developer
src/application/market_regime.py     @strategy-developer
src/application/atr_calculator.py    @strategy-developer
src/application/liquidation_gate.py  @strategy-developer
src/application/tick_engine.py       @strategy-developer
src/analysis/                        @strategy-developer

# Execution Engine Developer (③)
src/application/event_handler.py     @execution-developer
src/application/event_processor.py   @execution-developer
src/application/order_executor.py    @execution-developer
src/application/stop_manager.py      @execution-developer
src/application/exit_manager.py      @execution-developer
src/application/position_manager.py  @execution-developer
src/application/orchestrator.py      @execution-developer
src/infrastructure/exchange/         @execution-developer
src/adapter/                         @execution-developer

# Risk & Safety Guardian (④)
src/application/emergency*.py        @risk-guardian
src/application/session_risk*.py     @risk-guardian
src/application/fee_verification.py  @risk-guardian
src/application/ws_health.py         @risk-guardian
src/application/metrics_tracker.py   @risk-guardian
src/infrastructure/safety/           @risk-guardian

# Operations & Infrastructure (⑤)
src/infrastructure/logging/          @ops-infra
src/infrastructure/notification/     @ops-infra
src/infrastructure/storage/          @ops-infra
src/dashboard/                       @ops-infra
docker/                              @ops-infra
scripts/                             @ops-infra

# QA & Compliance (⑥)
tests/                               @qa-compliance
docs/evidence/                       @qa-compliance
docs/plans/task_plan.md              @qa-compliance
scripts/verify_*.sh                  @qa-compliance
```

---

## 4. 의사결정 흐름

### 4.1 매매 진입 (실시간, 매 Tick)

```
④ Risk Guardian: Emergency Check (Section 5)
    │ PASS
    ▼
② Strategy Dev: Signal Decision (Section 2 Tick [4])
    │ Signal = LONG/SHORT
    ▼
② Strategy Dev: Risk Gate 7개 (Section 2 Tick [5])
    │ PASS
    ▼
② Strategy Dev: Position Sizing + Liquidation Gate (Section 3.4, 7.5)
    │ contracts 확정
    ▼
③ Execution Dev: place_order (Section 8 Idempotent)
    │ state = ENTRY_PENDING
    ▼
③ Execution Dev: WS 이벤트 수신 → state = IN_POSITION + Stop 설치
    │
    ▼
④ Risk Guardian: Fee Post-Trade Verification (Section 6.2)
```

### 4.2 코드 변경 (개발 시)

```
⑥ QA: task_plan.md 확인 (TODO 항목 선택)
    │
    ▼
⑥ QA: task_plan.md IN PROGRESS 업데이트
    │
    ▼
① Architect: 설계 리뷰 (transition.py 영향 확인)
    │
    ▼
②③④⑤: 해당 소유 파일 구현
    │
    ▼
⑥ QA: Gate 9개 검증 + Evidence 생성
    │ ALL PASS
    ▼
⑥ QA: task_plan.md DONE + Evidence 링크
    │
    ▼
① Architect: 최종 리뷰 (의존성 방향, SSOT 일관성)
```

### 4.3 거부권(Veto) 우선순위

| 순위 | 역할 | 사유 | 결과 |
|------|------|------|------|
| 1 | ④ Risk Guardian | Emergency HALT | 즉시 중단, 오버라이드 불가 |
| 2 | ① Architect | SSOT 위반 / ADR 누락 | 코드 거부, Rollback |
| 3 | ⑥ QA | Gate FAIL | Phase 진행 차단 |
| 4 | ② Strategy | Liquidation Distance 미달 | 주문 REJECT |

---

## 5. Claude Code TeamCreate 구현

### 5.1 팀 생성

```python
TeamCreate(
    team_name="cbgb-firm",
    description="CBGB 1인 트레이딩 개발 업체 (6인 구조)"
)
```

### 5.2 Agent 공통 프롬프트 규칙

모든 Agent spawn prompt에 **아래 규칙을 포함**한다:

```
공통 규칙 (모든 Agent 필수):
- 작업 종료 시 Daily Log 작성 필수: docs/daily/YYYY-MM-DD/{agent-name}.md
- Daily Log 템플릿: Section 9.3 참조 (Planned/Done/Blocked/Decision/Next)
- Done 섹션: 수정한 파일명, 함수명, 변경 내용 기재 (추상적 서술 금지)
- Daily Log 미작성 시 DONE 인정 불가 (R1, R6)
- Bash 도구 사용 금지 (Grep/Read/Glob만 사용) — 팀 리드가 직접 실행
```

### 5.3 Agent 생성 (6명)

```python
# ① Chief Architect (Team Lead)
Task(
    subagent_type="general-purpose",
    team_name="cbgb-firm",
    name="chief-architect",
    prompt="""
    역할: 총괄 설계자 / Team Lead
    시장: Linear USDT-Margined Only (BTC 마진 절대 금지, ADR-0002)
    소유 파일: src/domain/, src/application/transition.py, src/application/event_router.py
    핵심 규칙:
    - transition.py는 pure function (I/O 금지)
    - event_router.py는 thin wrapper (State enum 참조 금지)
    - FLOW.md 수정 시 ADR 필수
    - Domain 모델 변경 시 ADR 필수
    - BTC 단위 계산(max_loss_btc, Inverse 공식) 코드 발견 시 즉시 거부
    참조: FLOW.md Section 4, 10, 10.1, ADR-0002
    """
)

# ② Strategy Engine Developer
Task(
    subagent_type="general-purpose",
    team_name="cbgb-firm",
    name="strategy-developer",
    prompt="""
    역할: 전략 엔진 개발자
    시장: Linear USDT-Margined Only (BTC 마진 절대 금지, ADR-0002)
    소유 파일: signal_generator.py, sizing.py, entry_*.py, market_regime.py,
              atr_calculator.py, liquidation_gate.py, tick_engine.py, src/analysis/
    핵심 규칙:
    - Linear USDT Sizing: qty = max_loss_usdt / (price × stop_pct) (ADR-0002)
    - Sizing에 leverage 넣지 않음 (Section 3.5)
    - stop_distance = clamp(grid_spacing * 1.5, 0.02, 0.06)
    - Liquidation Distance Gate: stop × multiplier[stage]
    - 단위: 모든 계산은 USDT 기준
    - ❌ 절대 금지: max_loss_btc, BTC 단위 Sizing, Inverse 공식
    참조: FLOW.md Section 2 Tick [4][5][6], Section 3.3-3.6, Section 7, ADR-0002
    """
)

# ③ Execution Engine Developer
Task(
    subagent_type="general-purpose",
    team_name="cbgb-firm",
    name="execution-developer",
    prompt="""
    역할: 실행 엔진 개발자
    시장: Linear USDT-Margined Only (BTC 마진 절대 금지, ADR-0002)
    소유 파일: event_handler.py, event_processor.py, order_executor.py,
              stop_manager.py, exit_manager.py, position_manager.py,
              orchestrator.py, src/infrastructure/exchange/, src/adapter/
    핵심 규칙:
    - API 고정값: category="linear", symbol="BTCUSDT" (변경 불가)
    - PARTIAL_FILL → 즉시 IN_POSITION + Stop 설치
    - Stop 갱신: Amend 우선, 20% threshold, 2초 debounce
    - WS Reconcile: 연속 3회 불일치 → REST 덮어쓰기
    - Dedup: execution_id + order_id + exec_time
    - Idempotent: client_order_id ≤ 36자
    - ❌ 절대 금지: category="inverse", symbol="BTCUSD", settleCoin="BTC"
    참조: FLOW.md Section 1, 2.5, 2.6, 2.7, 4.1, 4.5, 8, ADR-0002
    """
)

# ④ Risk & Safety Guardian
Task(
    subagent_type="general-purpose",
    team_name="cbgb-firm",
    name="risk-guardian",
    prompt="""
    역할: 리스크 수호자
    시장: Linear USDT-Margined Only (BTC 마진 절대 금지, ADR-0002)
    소유 파일: emergency*.py, session_risk*.py, fee_verification.py,
              ws_health.py, metrics_tracker.py, src/infrastructure/safety/
    핵심 규칙:
    - Emergency Check는 Signal보다 먼저 (Section 5)
    - 4개 Kill Switch: Daily -5%, Weekly -12.5%, Streak 3/5, Anomaly
    - COOLDOWN 해제: 30분 경과 AND 5분 연속 안정
    - Fee spike: ratio > 1.5, 2회 연속 → HALT 30분
    - 모든 PnL/손실 계산 단위: USDT (BTC 단위 계산 금지)
    참조: FLOW.md Section 5, 5.1, 6.2, 7.6, 9, ADR-0002
    """
)

# ⑤ Operations & Infrastructure
Task(
    subagent_type="general-purpose",
    team_name="cbgb-firm",
    name="ops-infra",
    prompt="""
    역할: 운영/인프라 담당
    시장: Linear USDT-Margined Only (BTC 마진 절대 금지, ADR-0002)
    소유 파일: src/infrastructure/logging/, notification/, storage/,
              src/dashboard/, docker/, scripts/
    핵심 규칙:
    - System Uptime 99.5% 목표
    - Docker 자동 재시작 필수
    - Telegram 알림 (Emergency, HALT, 체결)
    - 로그 보존 최소 30일
    - 환경설정에 category/symbol 하드코딩 확인 (linear/BTCUSDT)
    참조: FLOW.md Section 2 (Tick 주기), 2.6.5 (Network Failure), ADR-0002
    """
)

# ⑥ QA & Compliance
Task(
    subagent_type="general-purpose",
    team_name="cbgb-firm",
    name="qa-compliance",
    prompt="""
    역할: 품질/규정 담당
    시장: Linear USDT-Margined Only (BTC 마진 절대 금지, ADR-0002)
    소유 파일: tests/, scripts/verify_*.sh, docs/evidence/, docs/plans/task_plan.md
    핵심 규칙:
    - Placeholder 테스트 0개 (assert True, pass #TODO 금지)
    - 9개 Gate 전부 PASS 필수
    - Evidence Artifacts 없으면 DONE 무효
    - task_plan.md Section 2.1/2.2 동기화 필수
    - Document-First: 문서 업데이트 → 코드 구현 순서
    - Inverse 잔존 코드 스캔: grep "inverse\|BTCUSD[^T]" src/ → 0건 필수
    참조: CLAUDE.md Section 5.0-5.7, FLOW.md Section 10.1, ADR-0002
    """
)
```

### 5.4 Agent 간 통신 순서

```
⑥ QA: task_plan.md에서 TODO 확인 → IN PROGRESS 업데이트
    ↓
① Architect: SSOT 영향 분석 → 설계 승인
    ↓
②③④⑤: 병렬 구현 (소유 파일 기준)
    ↓
⑥ QA: Gate 9개 검증 → Evidence 생성
    ↓
① Architect: 최종 리뷰 → DONE
```

---

## 6. 치명적 실패 시나리오 총괄

| Agent | 실패 패턴 | FLOW.md 위반 | 결과 |
|-------|-----------|-------------|------|
| ① Architect | transition()에 I/O 허용 | Section 4.2 | 테스트 불가, tick 2초 실패 |
| ② Strategy | USDT/BTC 단위 혼용 Sizing | Section 3.4 | 계약 수 100배 과대, 즉시 청산 |
| ② Strategy | max_loss_btc 변수 사용 (Inverse 잔존) | ADR-0002 위반 | BTC 변동 시 Loss Budget 왜곡, 과대 포지션 |
| ③ Execution | PARTIAL_FILL에서 Stop 미설치 | Section 2.5 | 포지션 노출, 청산 |
| ③ Execution | category="inverse" 또는 symbol="BTCUSD" 사용 | ADR-0002 위반 | API 거절, 주문 전체 실패, 포지션 노출 |
| ④ Risk | Emergency를 Signal 이후 실행 | Section 5 | 급락 중 진입, 3연패 |
| ④ Risk | PnL을 BTC 단위로 계산 | ADR-0002 위반 | Kill Switch 기준 왜곡, 보호 실패 |
| ⑤ Ops | 자동 재시작 없음 | Section 2.6.5 | VPS 재부팅 시 청산 |
| ⑥ QA | assert True 방치 | Gate 1 | stop_status=MISSING 미탐지 |
| ⑥ QA | Inverse 잔존 코드 미탐지 | ADR-0002 위반 | 단위 불일치 버그 운영 투입 |

---

## 7. 팀 성공 기준

| 기준 | 목표 | 실패 판정 |
|------|------|-----------|
| 청산 발생 | **0회** | 1회 = 팀 재편 |
| System Uptime | **99.5%** | 99% 미만 = ⑤ 경고 |
| Win Rate | **60%+** | 50% 미만 3주 = ② 재검토 |
| Gate 통과율 | **100%** | 1개 FAIL = Phase 차단 |
| SSOT 불일치 | **0건** | 3건 = ⑥ 경고 |
| Emergency 거짓 음성 | **0건** | 1건 = ④ 재검토 |

---

## 8. 미해결 이슈

### 8.1 FLOW.md Section 3 동기화 필요 (Inverse → Linear)

**현황**:
- **코드**: 100% Linear USDT (ADR-0002, 2026-01-25 완료)
- **CLAUDE.md**: Linear USDT 명시 (정확)
- **account_builder_policy.md**: Linear USDT 명시 (정확)
- **FLOW.md Section 3**: 여전히 Inverse (BTC-Denominated) 기술 (미동기화)

**영향 범위** (FLOW.md 내 Inverse 잔존 내용):
- Section 3.1: "BTC-Denominated + Position Mode" → Linear USDT로 수정 필요
- Section 3.2: Inverse PnL 공식 (`contracts × (1/entry - 1/exit)`) → Linear 공식으로 수정 필요
- Section 3.4: Inverse Sizing 공식 → 현재 코드의 `qty = loss_usdt / (price × stop_pct)`로 수정 필요
- Section 3.6: Margin 계산 (BTC 기반) → USDT 기반으로 수정 필요
- Section 4.3: "USD-based Calculation 금지" → Linear에서는 USDT 계산이 정상
- Section 4.5: `category="inverse"` → `category="linear"` 수정 필요

**조치**: FLOW.md 수정은 ADR 필수 (헌법 문서). ADR-0002 후속으로 FLOW.md Section 3 전체 Linear 동기화 ADR 작성 필요.

**우선순위**: 높음 — FLOW.md(헌법)와 코드가 불일치하면 FLOW.md의 헌법 지위가 무력화됨

### 8.2 Quant Researcher 역할 부재

FLOW.md에 전략 개발/백테스트 관련 섹션이 없어, ② Strategy Developer의 백테스트 업무는 FLOW.md 근거가 부족하다. 향후 FLOW.md에 Strategy Development 섹션 추가 검토 필요 (ADR 필수).

---

## 9. Daily Log 시스템 (일일 업무 기록)

### 9.1 왜 Daily Log가 필수인가

멀티에이전트의 최대 리스크는 **"각자 맞다고 생각하는 것"** 이다.

- `task_plan.md`는 **상태** (DONE / IN PROGRESS / TODO)
- Daily Log는 **맥락** (왜 그렇게 됐는지, 중간에 무슨 일이 있었는지)

Agent는 이전 맥락을 축약해서 기억한다. Daily Log를 `docs/`에 남기면 다음날 Agent가 문서로 context를 복원한다.

### 9.2 디렉토리 구조 (고정)

```
docs/daily/
├── TEMPLATE.md                     # 템플릿 (복사용)
├── 2026-02-08/                     # 날짜별 폴더
│   ├── chief-architect.md          # ① 총괄 설계자
│   ├── strategy-dev.md             # ② 전략 엔진
│   ├── execution-dev.md            # ③ 실행 엔진
│   ├── risk-guardian.md            # ④ 리스크 수호자
│   ├── ops-infra.md                # ⑤ 운영/인프라
│   └── qa-compliance.md            # ⑥ 품질/규정
└── 2026-02-09/
    └── ...
```

- 날짜 단위 폴더 고정 (ISO 8601: `YYYY-MM-DD`)
- Agent 1명 = 파일 1개
- 파일명 = Agent name (TeamCreate name과 동일)

### 9.3 템플릿 (상한선 — 절대 늘리지 마라)

```markdown
# Daily Log — <agent-name>
Date: YYYY-MM-DD

## 1. Planned (아침 기준)
- [ ] task_plan.md 확인: Phase-XX / Task-YY
- [ ] <구체적 작업 1>
- [ ] <구체적 작업 2>

## 2. Done (팩트만, 파일/함수/커맨드 단위)
- (없음)

## 3. Blocked / Issue
- (없음)

## 4. Decision / Change
- ADR 필요 여부: NO

## 5. Next Action (내일)
- <다음 액션 1~3개>
```

### 9.4 강제 규칙

| 규칙 | 내용 | 위반 시 |
|------|------|---------|
| R1 | Daily Log 없으면 DONE 인정 안 함 | ⑥ QA가 task_plan DONE 찍기 전 확인 |
| R2 | ① Architect는 Issue / Decision 섹션만 읽음 | 나머지는 ⑥ QA 책임 |
| R3 | Blocked는 24시간 이상 방치 금지 | 다음날 잔존 시 자동 Architect Review 대상 |
| R4 | 감정 표현 금지 | "검토함", "고민함", "열심히 했다" 금지 |
| R5 | 파일명/함수명/커맨드 결과 필수 | 추상적 서술 금지 |
| R6 | **모든 작업 종료 시 Daily Log 작성 필수** | 미작성 시 다음 작업 진행 차단 |
| R7 | 팀 리드는 Daily Log 작성 지시 없이도 Agent가 자발적 작성 | Agent prompt에 End-of-Session 규칙 포함 |

### 9.5 End-of-Session Daily Report (필수)

**강제 규칙**: 모든 Agent는 일일 작업 종료 시 해당 날짜의 Daily Log를 **반드시** 작성한다.

#### 작성 시점
- Agent가 할당된 작업을 모두 완료하고 idle 상태가 되기 **직전**
- 팀 리드의 shutdown_request를 받기 **직전**
- 컨텍스트 소진으로 세션이 종료되기 **직전**

#### 작성 내용
- Section 1 (Planned): 오늘 할당받은 작업 목록 + 체크 표시
- Section 2 (Done): **실제 수정한 파일명, 함수명, 변경 내용** (팩트 only)
- Section 3 (Blocked): 해결 못한 이슈 (없으면 "없음")
- Section 4 (Decision): ADR 필요 여부 + 결정 사항
- Section 5 (Next Action): 다음 세션에서 해야 할 작업

#### 검증
```bash
# QA Agent 검증: 오늘 날짜 Daily Log 6개 존재 확인
ls docs/daily/$(date +%Y-%m-%d)/*.md 2>/dev/null | wc -l
# → 6 (모든 Agent 작성 완료)

# 각 파일에 "Done (팩트만)" 이후 실제 내용 존재 확인
for f in docs/daily/$(date +%Y-%m-%d)/*.md; do
  grep -A1 "## 2. Done" "$f" | grep -v "팀 구성 단계" | grep -v "^--$" | grep -c "."
done
# → 각 파일 1 이상 (빈 템플릿 금지)
```

#### 위반 시
- Daily Log 미작성 Agent → **다음 세션 작업 할당 차단**
- 빈 템플릿("팀 구성 단계, 구현 작업 없음") 그대로 제출 → **DONE 무효**
- 팀 리드가 대신 작성 금지 → **각 Agent 본인 책임**

### 9.6 task_plan.md 연결

task_plan.md Progress Table에 Daily Log 링크 컬럼을 추가한다:

```
| Phase | Task | Status | Evidence | Daily Log |
|-------|------|--------|----------|-----------|
| 11b | Stop Amend | DONE | docs/evidence/phase_11b/ | docs/daily/2026-02-08/execution-dev.md |
```

### 9.7 읽기 책임

| 역할 | 읽는 범위 | 목적 |
|------|-----------|------|
| ① Architect | 전원의 Issue / Decision 섹션 | 의사결정 충돌 탐지 |
| ⑥ QA | 전원의 Done / Blocked 섹션 | Evidence 일관성 검증 |
| 나머지 Agent | 자신의 로그 + 의존 Agent의 Done | Input 확인 |

---

## 10. Agent Output Contract (에이전트 간 업무 계약)

### 10.1 왜 필요한가

역할 설명서 ≠ 업무 계약서. "무엇을 만들어야 하는지"만 있고 **"무엇을 넘겨줘야 하는지"** 가 없으면, 누구도 틀리지 않게 실패한다.

### 10.2 Agent별 Output Contract

#### ② Strategy → ③ Execution (Signal + Sizing 결과)

```python
@dataclass
class SignalDecision:
    direction: Literal["LONG", "SHORT", "NONE"]
    signal_id: str                    # f"{strategy[:4]}_{hash[:10]}_{side[:1]}"
    timestamp: float

@dataclass
class SizingResult:
    contracts: int                    # 최종 계약 수 (contract_size=0.001 BTC)
    qty: float                        # contracts × contract_size
    stop_distance_pct: float          # clamp(grid_spacing × 1.5, 0.02, 0.06)
    stop_price: float                 # entry ± (entry × stop_distance_pct)
    max_loss_usdt: float              # 이 주문의 최대 손실 (USDT)
    entry_price: float                # 예상 진입가
    liquidation_distance_pct: float   # Liquidation Gate 통과 증거
    rejection_reason: str | None      # Risk Gate 거절 시 사유 (enum)
```

**검증 규칙**:
- `contracts > 0` (0이면 진입 금지)
- `max_loss_usdt > 0` (USDT 단위 필수, BTC 단위 금지)
- `stop_distance_pct ∈ [0.02, 0.06]`
- `rejection_reason is None` 이어야 주문 진행

#### ④ Risk → ③ Execution (Emergency 판정)

```python
@dataclass
class EmergencyVerdict:
    can_trade: bool                   # False면 진입 차단
    halt_reason: str | None           # HALT 사유
    cooldown_until: float | None      # COOLDOWN 해제 시각 (UTC)
    kill_switch_triggered: str | None  # daily_loss | weekly_loss | streak | anomaly
```

**검증 규칙**:
- `can_trade == False` → 모든 pending 취소, 진입 차단, Stop 유지
- `kill_switch_triggered is not None` → 즉시 HALT, 오버라이드 불가

#### ③ Execution → ④ Risk (체결 결과)

```python
@dataclass
class TradeResult:
    order_id: str
    side: Literal["Buy", "Sell"]
    qty: float
    entry_price: float
    fee_usdt: float                   # 수수료 (USDT)
    slippage_usdt: float              # 슬리피지 (USDT)
    realized_pnl_usdt: float | None   # 청산 시에만 (USDT)
    timestamp: float
```

**검증 규칙**:
- `fee_usdt >= 0` (USDT 단위)
- `realized_pnl_usdt`는 청산 시에만 존재

#### ⑤ Ops → ④ Risk (인프라 상태)

```python
@dataclass
class InfraStatus:
    ws_connected: bool
    ws_latency_ms: float
    rest_error_rate_pct: float        # 최근 5분 기준
    rest_budget_remaining: int        # 90회/분 중 남은 횟수
    disk_healthy: bool
    last_heartbeat: float             # UTC timestamp
```

**검증 규칙**:
- `ws_latency_ms >= 5000` → Risk에 보고 → HALT 판단
- `rest_error_rate_pct >= 50` → DEGRADED 모드
- `rest_budget_remaining <= 10` → 80% 경고

### 10.3 Contract 위반 시

| 위반 | 발견자 | 조치 |
|------|--------|------|
| Output 필드 누락 | ⑥ QA | 해당 Agent에 즉시 반환, DONE 무효 |
| 단위 오류 (BTC↔USDT) | ⑥ QA | 즉시 수정, 코드 리뷰 거부 |
| Contract 스키마 변경 | ① Architect | ADR 필수 |

---

## 11. Architect Auto-Check (머신 체크 가능 기준)

### 11.1 자동 검증 항목 (grep/스크립트로 검출 가능)

```bash
# AC-1: transition.py I/O import 금지
grep -nE "^(import|from).*(requests|aiohttp|httpx|socket|os\.path|open\(|logging)" \
  src/application/transition.py
# → 출력: 비어있음

# AC-2: Domain → Infrastructure 역방향 import 금지
grep -rn "from.*infrastructure\|import.*infrastructure" src/domain/
# → 출력: 비어있음

# AC-3: Application → Infrastructure 직접 import 금지 (transition.py만)
grep -nE "from.*infrastructure\|import.*infrastructure" src/application/transition.py
# → 출력: 비어있음

# AC-4: 파일 길이 제한 (단일 파일 500줄 초과 시 경고)
wc -l src/application/*.py | sort -rn | head -5
# → 500줄 초과 파일 식별

# AC-5: Inverse 잔존 코드 (Linear 프로젝트 전체)
grep -rInE 'category\s*=\s*"inverse"|symbol\s*=\s*"BTCUSD[^T]"|max_loss_btc|settleCoin.*BTC' src/
# → 출력: 비어있음
```

### 11.2 수동 판단 항목 (Architect만 판정 가능)

| 항목 | 판단 기준 | 대체 불가 사유 |
|------|-----------|---------------|
| 책임 분리 적절성 | 단일 파일이 2개 Agent 영역을 침범하는가 | 소유권 경계는 도메인 지식 필요 |
| Intent 패턴 준수 | transition() 반환에 모든 부수효과가 Intent로 표현되는가 | 누락 여부는 비즈니스 로직 이해 필요 |
| 상태 전이 완전성 | 모든 State × Event 조합이 처리되는가 | 경우의 수 검토는 도메인 판단 |

---

## 12. Ops ↔ Risk Failure Budget (인프라-리스크 연결)

### 12.1 문제

Ops가 "서버는 살아있음"을 보장해도, Risk가 "돈은 죽음"을 막지 못하면 의미 없다. 두 역할의 판단 기준이 연결되어야 한다.

### 12.2 Failure Budget 정의

| 인프라 지표 | 임계값 | Ops 조치 | Risk 조치 |
|-------------|--------|----------|-----------|
| WS latency | ≥ 3초 (3회 연속) | 경고 로그 + Telegram 알림 | — |
| WS latency | ≥ 5초 (1회) | REST fallback 전환 | HALT 판단 (Section 5) |
| WS disconnect | 10초 이상 | 자동 재연결 시도 | DEGRADED 모드 진입 |
| REST error rate | ≥ 30% (5분 기준) | 경고 로그 | DEGRADED 모드 진입 |
| REST error rate | ≥ 50% (5분 기준) | Telegram 긴급 알림 | HALT |
| REST budget | ≤ 10회/분 | Tick 주기 확대 (2초→5초) | — |
| WS + REST 동시 실패 | 30초 이상 | Telegram 긴급 알림 | 즉시 HALT (Section 2.6.5) |
| Disk I/O stall | 5초 이상 | 로그 버퍼링 | 거래 비활성화 |

### 12.3 에스컬레이션 체인

```
⑤ Ops 감지
    │
    ├── 경고 레벨 (Ops 자체 처리)
    │   └── WS latency 3초, REST budget 경고
    │
    ├── 위험 레벨 (→ ④ Risk에 보고)
    │   └── WS latency 5초, REST error 30%+
    │
    └── 긴급 레벨 (→ ④ Risk HALT + ① Architect 통보)
        └── 동시 실패, Disk stall
```

### 12.4 검증

```bash
# Ops → Risk 연결 코드 존재 확인
grep -rn "halt\|HALT\|degraded\|DEGRADED" src/infrastructure/ | wc -l
# → 0이 아님 (연결 코드 존재)

# InfraStatus → EmergencyChecker 참조 확인
grep -rn "InfraStatus\|ws_latency\|rest_error_rate" src/application/emergency*.py
# → 참조 존재 확인
```
