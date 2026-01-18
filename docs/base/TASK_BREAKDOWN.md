# TASK_BREAKDOWN.md — Account Builder Edition

## 0. 이 문서의 목적

이 문서는 기능 나열이 아니다.

> **작은 시드로 계좌를 ‘점프’시키는 시스템을  
어떤 순서로, 어떤 실패를 허용하며 구현할 것인지**를 정의한다.

- 완성도보다 **순서**
- 안정성보다 **비대칭 수익**
- 성공률보다 **성공 시 임팩트**

---

## 1. 전체 개발 원칙 (Non-Negotiables)

1. **청산 방지 > 모든 것**
2. 실패는 허용하되, **이유 없는 실패는 금지**
3. 모든 판단은 **로그로 추적 가능**
4. 각 단계는 **독립적으로 검증 가능**해야 함
5. 계좌 점프가 발생하지 않으면 **다음 단계로 가지 않음**

---

## 2. 단계 개요 (Phased Roadmap)

| Phase | 목표 | 성공 기준 |
|---|---|---|
| P0 | 구조 구축 | 모든 컴포넌트 연결 |
| P1 | 신호 검증 | 의미 있는 기회 포착 |
| P2 | 공격 실행 | 비대칭 수익 발생 |
| P3 | 계좌 점프 | 계좌 레벨 상향 |
| P4 | 사후 정리 | 재시작 또는 종료 |

---

## 3. Phase 0 — 시스템 뼈대 구축 (Foundation)

### 목표
- **돈을 벌기 전**, 돈을 잃지 않는 이유를 없앤다.
- **EV_FRAMEWORK가 실제로 게이트 역할을 하는지 증명**

### 작업 항목
- [ ] 상태 머신(State Machine) 구현
- [ ] Strategy / **EV_FRAMEWORK** / Risk / Position / Execution 인터페이스 연결
- [ ] **EV_FRAMEWORK가 Strategy 신호를 차단할 수 있는지 검증**
- [ ] 모든 의사결정 로그 설계
- [ ] 실거래 전 Dry-run 모드 구축

### 완료 기준
- 실거래 없이도 모든 상태 전환이 로그로 재현 가능
- **EV_FRAMEWORK REJECT 시 ENTRY로 진입하지 않음 확인**
- 비정상 입력에도 시스템이 중단되지 않음

---

## 4. Phase 1 — 기회 탐지 검증 (Signal Validation)

### 목표
- **자주가 아니라, 제대로 오는 기회**를 잡는다.
- **EV 기준을 통과하는 신호만 살아남는다.**

### 작업 항목
- [ ] 방향성 필터(EMA200 등) 작동 검증
- [ ] 변동성 확장 감지 로직 검증
- [ ] **EV_FRAMEWORK 검증: +300% 가능성 판정**
- [ ] **EV 통과/차단 로그 기록 및 분석**
- [ ] 진입 "하지 않음" 조건 로그 확인
- [ ] 신호 발생 빈도 계측

### 실패 허용
- 수익 ❌
- 손실 ⭕ (소액)

### 완료 기준
- "왜 진입하지 않았는지" 설명 가능
- **EV 기준 미달 신호는 ENTRY로 절대 가지 않음**
- **EV 통과/차단 로그가 명확히 남음**
- 주 1~3회 수준의 **의미 있는 신호** 확인 (EV 통과 기준)

---

## 5. Phase 2 — 공격 실행 (Asymmetric Bet)

### 목표
- **질 때는 작게, 맞을 때는 크게**

### 작업 항목
- [ ] 초기 소형 진입
- [ ] 방향 유지 시 포지션 확장
- [ ] 수익 구간에서 사이징 증가 확인
- [ ] 손실 시 빠른 정리

### 실패 허용
- 계좌 손실 ⭕
- 연속 실패 ⭕
- 계좌 축소 ⭕  

### 금지
- 청산 ❌
- 규칙 외 확장 ❌

### 완료 기준
- 손실 대비 수익 비율(R:R) ≥ 1:5
- 단일 트레이드로 **여러 실패 상쇄**

---

## 6. Phase 3 — 계좌 점프 판정 (Account Jump)

### 목표
- 이 시스템이 **존재할 이유가 있는지 판단**

### 작업 항목
- [ ] 계좌 기준 수익률 측정
- [ ] 실패 횟수 대비 회복력 확인
- [ ] 수수료/슬리피지 영향 분석

### 성공 기준 (예시)
- 계좌 2~3배 성장
- 혹은 단일 트레이드로 “다음 자본 단계” 도달

> ⚠️ 이 기준을 못 넘으면  
> **전략 실패로 간주하고 종료**

---

## 7. Phase 4 — 종료 또는 재시작 (Post-Mortem)

### 선택지 A: 성공
- 계좌 레벨 상향
- Risk Model 재조정
- “Builder → Preserver” 전환 고려

### 선택지 B: 실패
- 계좌 리셋
- 로그 기반 원인 분석
- 전략 수정 후 P1 재진입

> **실패 자체는 문제가 아니다.  
아무것도 배우지 못한 실패만이 문제다.**

---

## 8. Risk Priority 기반 재정렬 (v2 추가)

### 8.1 문제: 기능 순서 vs 리스크 순서

**현재 구조** (Phase 0 → Phase 4):
- 기능 단위 분해
- "완성도" 순서

**실전 문제**:
- Phase 0 완료해도 청산 위험 존재 가능
- 어떤 작업이 "청산 방지"에 직결되는지 불명확

**필요한 것**:
> **리스크 우선순위 (P0/P1/P2) 기준으로 재정렬**

### 8.2 Risk Priority 정의

| Priority | 의미 | 실패 시 영향 | 허용 품질 |
|----------|------|------------|----------|
| **P0** | 청산 방지 | 계좌 파산 | 100% 완벽 |
| **P1** | 핵심 기능 | 시스템 무의미 | 90% 이상 |
| **P2** | 최적화 | 성능 저하 | 80% 이상 |

**철학**:
- P0 없으면 → 시작 금지
- P1 없으면 → 수익 불가
- P2 없으면 → 느리지만 작동

### 8.3 작업 항목 Risk Priority 분류

#### P0: 청산 방지 (Must Have - 100%)

**목적**: 이것들이 없으면 계좌가 파산함

| 작업 | 이유 | 위치 (원래 Phase) |
|------|------|------------------|
| **Liquidation 거리 모니터링** | 청산가 1.5 ATR 이내 → 긴급 청산 | P0 |
| **Risk Manager 레버리지 제한** | 레버리지 > 5x 금지 | P0 |
| **Execution Event: LIQUIDATION_WARNING** | 청산 경고 → State.EXIT_FAILURE | P0 |
| **Emergency Exit 로직** | 긴급 상황 Market 청산 | P0 |
| **Position Size 청산가 계산** | 진입 전 청산가 거리 3 ATR 확인 | P0 |
| **Drawdown 한도 (-50%)** | -50% 도달 시 TERMINATED | P0 |
| **State Machine: TERMINATED 상태** | 종료 조건 명확 | P0 |

**완료 기준**:
- [ ] 모든 진입 시 청산가 거리 ≥ 3 ATR 보장
- [ ] Liquidation 거리 < 1.5 ATR 시 자동 청산
- [ ] 레버리지 > 5x 진입 절대 불가
- [ ] Drawdown -50% 도달 시 시스템 종료

#### P1: 핵심 기능 (Core - 90%)

**목적**: 이것들이 없으면 수익 불가 (Account Builder 무의미)

| 작업 | 이유 | 위치 (원래 Phase) |
|------|------|------------------|
| **EV Full Validator (+300% 검증)** | +300% 미달 → 진입 금지 | P1 |
| **EV Pre-filter (빠른 Gate)** | 명백한 불가 조기 차단 | P1 |
| **State Machine 기본 흐름** | IDLE → MONITORING → ENTRY → EXIT | P0 |
| **Expansion 재검증 (Marginal EV)** | Expansion = 두 번째 진입 | P1 |
| **Exit 조건 (손절/익절)** | 손실 > -25% 청산, 수익 > +300% 익절 | P1 |
| **Strategy: 방향성 필터** | EMA200 4H 기준 Long만 | P1 |
| **Strategy: 변동성 확장 감지** | ATR 확장 없으면 진입 금지 | P1 |
| **Decision Log (StateDecisionLog)** | 모든 전환 이유 기록 | P1 |
| **Decision Log (EVDecisionLog)** | EV 통과/차단 이유 기록 | P1 |

**완료 기준**:
- [ ] EV 통과하지 않으면 ENTRY 절대 불가
- [ ] Expansion 시 Marginal EV < 0 → 차단
- [ ] 모든 State 전환 로그 기록
- [ ] +300% 트레이드 1회 이상 발생

#### P2: 최적화 (Optimization - 80%)

**목적**: 이것들이 없어도 작동하지만 느리거나 비효율

| 작업 | 이유 | 위치 (원래 Phase) |
|------|------|------------------|
| **동적 EV 임계값 (Volatility Regime)** | 변동성 수축 시 +210% 완화 | P2 |
| **DecisionOutcome (사후 평가)** | Hindsight 기반 학습 | P2 |
| **Slippage 임계값 최적화** | 0.15% → 동적 조정 | P2 |
| **Cooldown Duration 동적 조정** | 3연패 → 24h, 단일 -20% → 12h | P2 |
| **Feature Engine 캐싱** | EMA/ATR 중복 계산 방지 | P2 |
| **Execution Retry 정책 최적화** | TIMEOUT 재시도 2회 → 동적 | P2 |
| **Tail Profit 분포 분석** | 상위 10% 승리 패턴 학습 | P2 |

**완료 기준**:
- [ ] 변동성 수축 시 진입 기회 확보
- [ ] DecisionOutcome 로그 100개 이상 수집
- [ ] Feature 계산 시간 < 10ms (캐싱 적용)

### 8.4 구현 순서 (Risk Priority 우선)

#### 단계 1: P0 완료 (청산 방지)
```text
1주차:
- Liquidation Monitor 구현
- Risk Manager 레버리지 제한
- Emergency Exit 로직
- Position Size 청산가 계산

테스트:
- 레버리지 > 5x 진입 시도 → 차단 확인
- 청산가 < 1.5 ATR → 긴급 청산 확인
```

#### 단계 2: P1 완료 (핵심 기능)
```text
2~3주차:
- State Machine 기본 흐름
- EV Pre-filter + Full Validator
- Strategy 방향성 필터
- Expansion 재검증
- Decision Log 구조

테스트:
- EV 미달 신호 → ENTRY 차단 확인
- +300% 트레이드 1회 발생 확인
- 모든 State 전환 로그 확인
```

#### 단계 3: P2 완료 (최적화)
```text
4주차 이후:
- 동적 EV 임계값
- DecisionOutcome 학습
- 성능 최적화

테스트:
- 변동성 수축 시 진입 기회 존재
- DecisionOutcome 기반 임계값 조정
```

### 8.5 각 Priority별 검증 체크리스트

#### P0 검증 (청산 방지)
- [ ] 레버리지 > 5x 진입 시도 → 차단됨
- [ ] 청산가 거리 < 3 ATR 진입 시도 → 차단됨
- [ ] 포지션 보유 중 청산가 < 1.5 ATR → 자동 청산됨
- [ ] Drawdown -50% 도달 → TERMINATED 전환됨
- [ ] LIQUIDATION_WARNING Event → EXIT_FAILURE 전환됨

#### P1 검증 (핵심 기능)
- [ ] EV Pre-filter 차단 → ENTRY 진입 안 됨
- [ ] EV Full Validator 차단 → ENTRY 진입 안 됨
- [ ] Strategy 조건 미충족 → TradeIntent 생성 안 됨
- [ ] Expansion Marginal EV < 0 → 확장 차단됨
- [ ] StateDecisionLog 기록 → 모든 전환 추적 가능
- [ ] EVDecisionLog 기록 → PASS/FAIL 이유 명확

#### P2 검증 (최적화)
- [ ] 변동성 수축 시 임계값 +210% 완화됨
- [ ] DecisionOutcome 100개 이상 수집됨
- [ ] Feature 계산 시간 < 10ms
- [ ] Slippage 임계값 동적 조정됨

### 8.6 Risk Priority vs Phase 매핑

| Phase (기능 순서) | P0 작업 | P1 작업 | P2 작업 |
|------------------|---------|---------|---------|
| Phase 0 (Foundation) | Liquidation Monitor, Risk Manager, Emergency Exit | State Machine 기본 | - |
| Phase 1 (Signal) | - | EV Pre/Full, Strategy, Decision Log | - |
| Phase 2 (Asymmetric Bet) | Position Size 청산가 | Expansion 재검증, Exit 조건 | 동적 임계값 |
| Phase 3 (Account Jump) | Drawdown 한도 | - | DecisionOutcome, Tail 분석 |
| Phase 4 (Post-Mortem) | - | - | 성능 최적화 |

**핵심 인사이트**:
> **Phase 0를 완료해도 P0가 빠지면 청산됨.
> Phase는 기능 완성도, Priority는 생존 보장.**

---

## 9. 이 문서의 마지막 선언

이 시스템은:

- 안전하게 오래 살기 위해 존재하지 않는다
- 자주 이기기 위해 존재하지 않는다

> **이 시스템은  
작은 계좌가  
다음 단계로 이동할 수 있는지  
시험하기 위해 존재한다.**

계좌가 점프하지 않으면,
이 시스템은 **의미 없다**.
