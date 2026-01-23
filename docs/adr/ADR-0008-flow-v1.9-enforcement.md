# ADR-0008: FLOW v1.8 → v1.9 — 헌법 강제력 확보 및 내부 정합성 개선

**Date**: 2026-01-23
**Status**: Accepted
**Related**: FLOW.md v1.8, CLAUDE.md Section 6

---

## Context (왜 바꾸는가?)

### 발견된 문제

#### 1. 문서 내부 일관성 파괴 (SSOT 위반)
FLOW.md가 "헌법" 지위를 주장하지만, 내부에서 동일 규칙이 2곳에 중복 정의됨:
- **DEGRADED Mode**: Section 2.5 (line 400-454) + Section 2.6 (line 674-728)
- **Stop Loss 갱신 규칙**: Section 2.5 (line 478-548) + Section 4.5 (line 1356-1383)

**실거래 리스크**: 구현자가 한쪽만 읽거나, 양쪽이 불일치하면 로직 분기 → 장애 재현 불가

#### 2. 실행 불가능한 수치 모순 (REST Budget)
- **현재**: Tick 목표 주기 1초 × 3 REST/tick = 180 calls/min
- **Budget**: 90 calls/min (Bybit 120의 75%)
- **결과**: 30초 만에 Budget 소진 → HALT loop

**실거래 리스크**: 문서대로 구현하면 Rate limit 초과 → 운영 불가

#### 3. 헌법 강제력 부재 (불변 조건 미정의)
상태(6개) + 서브상태(stop_status, entry_working)를 사용하지만, 각 상태에서 반드시 참이어야 하는 **불변 조건(invariant)**이 코드 검증 가능한 형태로 명시되지 않음.

**예시**:
- "IN_POSITION이면 Stop 필수"를 말로는 강조하지만, `stop_order_id != None`인지 `stop_status == ACTIVE`인지 불명확
- ENTRY_PENDING에서 부분체결 시 IN_POSITION 전환 규칙이 있지만, "ENTRY_PENDING 건너뛰기 금지" 개념과 충돌

**실거래 리스크**: 구현자가 각자 해석 → 테스트가 헌법 위반을 탐지 못함 → 상태 불일치

#### 4. 이벤트 처리 계약 부재 (WS 품질)
"WS primary"는 명시했지만, 실거래 필연인 **중복/역순/지연 이벤트** 처리 규칙이 없음:
- Deduplication key 정의 없음
- Out-of-order 방어 규칙 없음
- REST reconcile override 우선순위 모호

**실거래 리스크**: 유령체결/유령취소 발생 → stop_status/position.qty 틀어짐 → "Stop 없는 IN_POSITION" 최악 케이스

#### 5. Complete Failure 시나리오 누락
현재 FLOW는 "정상 동작"만 정의하고, 아래 완전 실패 케이스 누락:
- **Network Partition**: WS + REST 모두 불통
- **Order Rejection Loop**: 영구적 거절 사유 반복 (margin 부족, invalid param)
- **Position Size Overflow**: 부분체결 누적으로 원래 sizing 결과 초과

**실거래 리스크**: 무한 재시도 → Rate limit 소진, 또는 교착 상태 → 복구 불가

---

### 발견 경위
- **내부 리뷰 1**: SSOT 중복, REST Budget 모순, Complete Failure 누락 발견
- **내부 리뷰 2**: 불변 조건 부재, 이벤트 계약 부재로 "헌법 강제력 0" 판정
- **판정**: FAIL (문서 방향은 통과권이지만, 내부 충돌 + 코드 검증 불가 → 헌법 지위 불인정)

---

## Decision (무엇을 바꾸는가?)

### 1. SSOT 중복 제거 (편집, ADR 불필요)
- DEGRADED Mode: Section 2.5 삭제 → Section 2.6 링크로 교체
- Stop Loss 갱신: Section 4.5 축약 → Section 2.5 링크로 교체

**내용 변경**: 없음 (구조 정리만)

---

### 2. REST Budget 정렬 (정의 변경, ADR 필요)

#### Before
```markdown
**Tick 주기**: 목표 1초 간격
**REST Budget**: 90회/분
```

#### After
```markdown
**Tick 주기**: 목표 2초 간격 (REST Budget 90회/분 준수)
**실제 주기**: API latency + rate limit 고려하여 1~3초 사이 동적 조정
```

**근거**:
- 60초 / 2초 = 30 tick/분
- 30 tick × 3 REST = 90 calls/분
- Budget 90과 일치 (Bybit 120의 75%)

**Trade-off**:
- 신호 반응 속도 감소 (1초 → 2초)
- 수용 가능: Rate limit 준수 > 신호 속도

---

### 3. State Invariants 표 추가 (불변 규칙 추가, ADR 필요)

**위치**: Section 1 끝 (line 117 이후)

**내용**: 6개 상태별 불변 조건을 코드 assert 가능한 형태로 명문화

| State | position.qty | stop_order_id | stop_status | entry_allowed | Invariant |
|-------|--------------|---------------|-------------|---------------|-----------|
| FLAT | == 0 | None | N/A | True (gate 통과 시) | 포지션 없음 |
| ENTRY_PENDING | >= 0 | None (또는 부분체결 시 존재) | N/A (또는 PENDING) | False | 부분체결 시 qty > 0 + entry_working=True |
| IN_POSITION | > 0 | != None | ACTIVE/PENDING | False | Stop 필수, MISSING은 복구 중 |
| EXIT_PENDING | > 0 | != None (exit) | N/A | False | 청산 대기 |
| HALT | any | any | any | False (Manual only) | 수동 복구만 |
| COOLDOWN | any | any | any | False (Auto after timeout) | 자동 해제 가능 |

**강제 규칙**:
- IN_POSITION에서 stop_status == MISSING 허용 시간: 최대 10초
- stop_status == ERROR 진입 즉시: HALT
- ENTRY_PENDING 부분체결 시: 즉시 IN_POSITION + Stop 설치

**목적**:
- oracle 테스트가 위 invariant를 자동 검증 가능
- 구현자 해석 여지 제거

---

### 4. COOLDOWN 해제 조건 명확화 (모드 의미 변경, ADR 필요)

#### Before (모호)
```markdown
COOLDOWN: 일시적 차단 (자동 해제 가능)
```
Section 5에서 "5분 연속 안정" 언급하지만, 정확한 조건 불명확

#### After (명확)
```markdown
**COOLDOWN 해제 조건 (SSOT)**:
- 30분 경과 (최소 대기) AND
- 5분 연속 안정 (emergency 조건 해소)

예시:
- price_drop 복구: drop < -5% 연속 5분 + 30분 경과
- latency 복구: latency < 2.0s 연속 5분 + 30분 경과
```

**목적**: "auto release" 조건을 코드로 구현 가능하게 정의

---

### 5. WS 이벤트 계약 추가 (이벤트 의미 변경, ADR 필요)

**위치**: Section 2.5 끝 (line 560 이후)

**내용**: 3개 계약 추가

#### (1) Deduplication
```python
dedup_key = f"{execution_id}_{order_id}_{exec_time}"
if dedup_key in processed_events:
    return  # 중복 무시
```

#### (2) Ordering
```python
if event.seq <= last_processed_seq[order_id]:
    return  # out-of-order 무시
```

#### (3) REST Reconcile Override
```python
if mismatch_count >= 3:
    state = rest_state  # REST = Source of Truth
```

**목적**: 유령체결/유령취소 방지 → 상태머신 정합성 보장

---

### 6. Complete Failure 시나리오 3종 추가 (상태 전이 규칙 변경, ADR 필요)

#### (1) Complete Network Failure (WS + REST)
**진입**: DEGRADED 상태에서 REST timeout 연속 3회
**동작**: IN_POSITION → 즉시 HALT (Stop 확인 불가)

#### (2) Order Rejection Circuit Breaker
**진입**: 연속 거절 3회 + 영구적 사유 (margin 부족 등)
**동작**: HALT (영구 사유) 또는 COOLDOWN 5분 (일시 사유)

#### (3) Position Size Overflow
**진입**: 부분체결 누적 > original_max_contracts × 1.1
**동작**: 초과분 즉시 청산 주문 (reduceOnly)

**목적**: 무한 재시도/교착 상태 방지 → 복구 가능성 확보

---

## Consequences (실거래 영향)

### Positive
1. **불변 조건 명문화** → oracle 테스트가 헌법 위반 자동 탐지 → 상태 불일치 사전 방지
2. **이벤트 계약** → 유령체결/유령취소 방지 → stop_status 정합성 보장
3. **Complete Failure 시나리오** → 무한 재시도/교착 차단 → 복구 가능성 확보
4. **REST Budget 정렬** → Rate limit 준수 → HALT loop 방지

### Negative
1. **Tick 주기 2초** → 신호 반응 속도 감소 (1초 → 2초)
   - **수용 가능**: Rate limit 준수가 생존성 우선
   - **완화**: 동적 조정(1~3초)으로 latency 낮을 때 1초 가능

2. **불변 조건 강제** → 기존 코드가 위반 시 oracle 테스트 실패
   - **필요한 조치**: 코드 수정 + oracle 테스트 작성

3. **이벤트 dedup/ordering** → 구현 복잡도 증가
   - **필요한 조치**: WS 핸들러에 dedup 로직 추가 (~100 lines)

### Risks
1. **기존 코드가 1초 tick 가정**
   - **영향**: Tick loop 주기 변경 필요
   - **완화**: 설정 파일로 주기 조정 가능 (하드코딩 금지)

2. **불변 조건 위반 코드 존재 가능**
   - **영향**: oracle 테스트 실패 → 수정 필요
   - **완화**: RED → GREEN 증거로 점진 수정

3. **WS dedup 미구현**
   - **영향**: 유령체결 계속 발생 가능
   - **완화**: Phase 3 (코드 검증)에서 즉시 구현 (critical)

---

## Alternatives (대안)

### Alt 1: REST Budget 증가 (90 → 180)
**장점**: Tick 주기 1초 유지 → 신호 속도 유지
**단점**: Bybit rate limit 75% 원칙 위반 (120의 150%) → 초과 리스크
**거부 이유**: Rate limit 초과 > 신호 속도 (생존성 우선)

---

### Alt 2: 불변 조건을 코드 주석으로만
**장점**: 문서 간결
**단점**: 테스트 불가 → 구현자 각자 해석 → 상태 불일치
**거부 이유**: 헌법은 검증 가능해야 함 (oracle 테스트 필수)

---

### Alt 3: WS 이벤트 계약을 "권장"으로만
**장점**: 구현 강제 안 함 → 초기 부담 감소
**단점**: 유령체결/유령취소 방치 → 상태머신 붕괴
**거부 이유**: 이벤트 품질 = 생존성 (optional 불가)

---

### Alt 4: Complete Failure 시나리오를 별도 문서로
**장점**: FLOW.md 간결 유지
**단점**: 헌법과 예외 처리가 분리 → SSOT 위반
**거부 이유**: Complete Failure는 정상 흐름의 일부 (같은 문서에 있어야 함)

---

## Implementation Plan

### Phase 1: 문서 수정 (2시간 45분)
1. **SSOT 중복 제거** (30분)
   - Section 2.5 DEGRADED 삭제 → Section 2.6 링크
   - Section 4.5 Stop 갱신 축약 → Section 2.5 링크

2. **REST Budget 정렬** (15분)
   - Section 2 (line 121): "목표 2초 간격" 수정
   - 계산 검증: 60/2 × 3 = 90

3. **State Invariants 표 추가** (45분)
   - Section 1 끝: 표 6행 작성
   - 강제 규칙 3개 추가
   - 테스트 요구사항 명시

4. **COOLDOWN 정의 명확화** (15분)
   - Section 1: 링크 추가
   - Section 5: 해제 조건 SSOT 작성

5. **WS 이벤트 계약 추가** (30분)
   - Section 2.7 신규 작성
   - dedup/ordering/REST override 3개

6. **Complete Failure 시나리오 추가** (45분)
   - Section 2.6.5: Network Failure
   - Section 7.6: Rejection Circuit Breaker
   - Section 2.5.3: Position Size Overflow

7. **Code Enforcement 요구사항 추가** (30분)
   - Section 10.1: 검증 명령 5개
   - Evidence Artifacts 요구사항

8. **변경 이력 업데이트** (5분)
   - v1.9 항목 추가
   - 참조: ADR-0008

---

### Phase 2: 코드 구현 (별도 세션, 6시간 예상)
1. **transition() SSOT 확립** (2시간)
2. **WS dedup/ordering 구현** (2시간)
3. **stop_status 강제 루프** (1시간)
4. **Oracle 테스트 작성** (1시간)

---

### Phase 3: 검증 및 증거 (1시간)
1. **문서 Gate 1~7 검증**
2. **코드 Gate 8~11 검증**
3. **Evidence Artifacts 생성**

---

## Verification (완료 조건)

### 문서 수정 완료 (Phase 1)

#### Gate 1: SSOT 중복 제거
```bash
grep -n "^###.*DEGRADED.*Mode" docs/constitution/FLOW.md | wc -l
# → 1 (Section 2.6만)

grep -n "def update_stop_loss_if_needed" docs/constitution/FLOW.md | wc -l
# → 1 (Section 2.5만)
```

#### Gate 2: REST Budget 정렬
```bash
grep -n "목표.*2초" docs/constitution/FLOW.md
# → line 번호 출력

# 계산: 60/2 × 3 = 90 (일치)
```

#### Gate 3: 불변 조건 표 존재
```bash
grep -n "State Invariants" docs/constitution/FLOW.md
# → line 번호 출력

grep -A 20 "State Invariants" docs/constitution/FLOW.md | grep -E "FLAT|ENTRY_PENDING|IN_POSITION|EXIT_PENDING|HALT|COOLDOWN" | wc -l
# → 6 (6개 상태 모두)
```

#### Gate 4: COOLDOWN 해제 조건 SSOT
```bash
grep -n "COOLDOWN 해제 조건.*SSOT\|cooldown_auto_released" docs/constitution/FLOW.md
# → Section 5에만 출력
```

#### Gate 5: WS 이벤트 계약 존재
```bash
grep -n "Deduplication\|Ordering\|REST Reconcile Override" docs/constitution/FLOW.md | wc -l
# → 3 (Section 2.7)
```

#### Gate 6: Complete Failure 시나리오 3종
```bash
grep -n "Complete Network Failure\|Rejection Circuit Breaker\|Position Size Overflow" docs/constitution/FLOW.md | wc -l
# → 3
```

#### Gate 7: 변경 이력 업데이트
```bash
grep -n "v1.9.*2026-01-23.*ADR-0008" docs/constitution/FLOW.md
# → line 번호 출력
```

---

### 코드 검증 완료 (Phase 2, BLOCKING for PASS)

#### Gate 8: 상태머신 SSOT
```bash
find src -name "*.py" -exec grep -l "def transition" {} \; | wc -l
# → 1 (1개 파일만)

grep -n "State\." src/application/event_router.py
# → 비어있음 (thin wrapper)
```

#### Gate 9: 이벤트 dedup/ordering
```bash
grep -rn "dedup_key" src/ | wc -l
# → 1 이상

grep -rn "last_processed_seq" src/ | wc -l
# → 1 이상
```

#### Gate 10: stop_status 강제 루프
```bash
grep -rn "if state == IN_POSITION.*stop_status" src/ | wc -l
# → 1 이상

grep -rn "stop_recovery_fail_count >= 3" src/ | wc -l
# → 1 이상
```

#### Gate 11: Oracle 테스트 존재 + 통과
```bash
test -f tests/oracles/test_state_transition_oracle.py && echo "OK" || echo "FAIL"
# → OK

grep -n "test_partial_fill\|test_degraded_halt\|test_rest_budget\|test_stop_recovery\|test_event_dedup\|test_size_overflow" tests/oracles/*.py | wc -l
# → 6 이상

pytest tests/oracles/ -v
# → 모든 테스트 PASS
```

#### Gate 12: Evidence Artifacts
```bash
test -d docs/evidence/flow_v1.9 && echo "OK" || echo "FAIL"
# → OK

ls docs/evidence/flow_v1.9/ | grep -E "gate_verification.txt|oracle_pytest_output.txt|red_green_proof.md" | wc -l
# → 3
```

---

### PASS 조건
- Gate 1~7 모두 통과 (문서 일관성)
- Gate 8~12 모두 통과 (코드 강제)
- pytest tests/oracles/ 100% PASS
- Evidence Artifacts 존재

---

## References
- **FLOW.md v1.8** (현재 버전)
- **CLAUDE.md Section 6** (ADR 규칙)
- **Internal Review 1** (SSOT 중복, REST Budget 모순, Complete Failure 누락)
- **Internal Review 2** (불변 조건 부재, 이벤트 계약 부재, 강제력 0)

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-23 | Proposed | 내부 리뷰 2건 기반 문제 확인 |
| 2026-01-23 | **Accepted** | 프로젝트 오너 승인 (즉시) |

---

**Implementation Status**: Phase 1 진행 중 (문서 수정)
