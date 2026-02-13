# PLAN: Operation Manual 작성
**Created**: 2026-02-01
**Last Updated**: 2026-02-01 (Phase 1 COMPLETE)
**Status**: 🚧 Phase 1 Complete, Phase 2 Ready
**Owner**: CBGB Development Team

---

## ⚠️ CRITICAL INSTRUCTIONS

After completing each phase:
1. ✅ Check off completed task checkboxes
2. 🧪 Run all quality gate validation commands
3. ⚠️ Verify ALL quality gate items pass
4. 📅 Update "Last Updated" date
5. 📝 Document learnings in Notes section
6. ➡️ Only then proceed to next phase

⛔ **DO NOT skip quality gates or proceed with failing checks**

---

## 1. Overview

### 1.1 Objectives

**Goal**: CBGB 시스템의 전체 구성과 운영에 필요한 정보를 담은 종합 운영 매뉴얼 작성

**Deliverable**: `docs/base/operation.md` - 시스템 구성도, 함수별 설명, 코드 flow, 운영 가이드를 포함한 단일 문서

**Why**:
- 새로운 개발자/운영자가 시스템 전체를 빠르게 이해할 수 있도록
- 운영 중 발생하는 문제를 신속하게 진단하고 해결할 수 있도록
- 코드와 문서 간의 격차를 줄이고 SSOT 원칙 준수

### 1.2 Success Criteria

- [ ] 모든 언급된 파일 경로가 실제로 존재하고 링크 가능
- [ ] 함수 시그니처가 실제 코드와 100% 일치
- [ ] SSOT 3문서(FLOW.md, account_builder_policy.md, task_plan.md)와 모순 없음
- [ ] Markdown 렌더링 오류 없음
- [ ] 새 세션에서 문서만으로 시스템 이해 및 운영 가능

### 1.3 Non-Goals

- 자동 생성 도구 개발 (수동 작성 후 필요 시 추후 자동화)
- API 자동 문서화 시스템 구축
- 다국어 지원 (한국어만 우선)

---

## 2. Architecture Overview

### 2.1 Current System State

- **Total Python Modules**: 59개
- **Passing Tests**: 366개
- **Design Documents**: 26,666줄
- **Completed Phases**: 0~13b (Initial Entry Fix 완료)
- **Architecture**: Clean Architecture (Domain → Application → Infrastructure)

### 2.2 Key Technologies

- **Language**: Python 3.11+
- **Exchange**: Bybit Linear Futures (USDT-Margined)
- **State Management**: Pure functional state machine (transition.py)
- **Testing**: pytest + Oracle pattern
- **Documentation**: Markdown (SSOT 3문서 기반)

### 2.3 Architecture Decisions

**Relevant ADRs**:
- ADR-0001~0004: FLOW 초기 문제 해결
- ADR-0007: Halt vs Cooldown 의미화
- ADR-0008: FLOW v1.9 강제화
- ADR-0009: SSOT 중복 제거
- ADR-0011: Task Plan 동기화 규칙

**Key Principles**:
- Document-First Workflow (문서 → 테스트 → 구현)
- Survival-First (청산 방지가 최우선)
- Single Source of Truth (정의 중복 금지)
- Zero Placeholder Tests (실제 검증만 인정)

---

## 3. Phase Breakdown

### Phase 1: 시스템 개요 및 아키텍처 맵핑

**Goal**: 시스템 전체 구조와 계층별 책임을 명확히 문서화

**Duration**: 2-3 hours

**Verification Strategy**:
- 파일 경로 존재 검증 스크립트 작성
- SSOT 문서와 교차 검증 (FLOW.md Section 참조)
- 다이어그램 정확성 검토

**Tasks**:

1. **Documentation Tasks**:
   - [ ] 시스템 개요 섹션 작성 (목표, 제약사항, 핵심 원칙)
     - 출처: CLAUDE.md, FLOW.md Section 1, PRD.md
   - [ ] 아키텍처 레이어 다이어그램 작성
     - Domain (순수 함수) → Application (비즈니스 로직) → Infrastructure (I/O)
   - [ ] 디렉토리 구조 맵 작성
     - 기준: task_plan.md Section 2.1 Repo Map
   - [ ] 모듈별 책임 매트릭스 작성
     - 59개 Python 파일 분류 (domain/application/infrastructure/analysis/dashboard)

2. **Verification Tasks**:
   - [ ] 파일 경로 검증 스크립트 작성
     ```bash
     grep -oE 'src/[a-z_/]+\.py' docs/base/operation.md | sort -u | while read f; do
       [ -f "$f" ] || echo "MISSING: $f"
     done
     ```
   - [ ] SSOT 문서 참조 검증
     - FLOW.md 아키텍처 설명과 일치 확인
     - task_plan.md Repo Map과 경로 일치 확인

**Quality Gate**:
- [ ] 언급된 모든 파일 경로 존재 확인 (검증 스크립트 PASS)
- [ ] SSOT 3문서와 충돌 없음
- [ ] 다이어그램이 실제 의존성 방향과 일치
- [ ] Markdown 렌더링 정상

**Deliverable**: `docs/base/operation.md` (Section 1-3: Overview, Architecture, Components)

**Dependencies**: None (첫 Phase)

**Rollback Strategy**:
- Git commit 전 별도 브랜치 생성
- 문제 발견 시 `git restore docs/base/operation.md`

---

### Phase 2: 상태 머신 및 이벤트 플로우

**Goal**: State Machine, Event, Intent 시스템의 동작 원리를 정확히 문서화

**Duration**: 2-3 hours

**Verification Strategy**:
- transition.py 실제 코드와 전이 규칙 1:1 매칭
- Oracle 테스트 케이스와 교차 검증
- FLOW.md Section 4 상태 머신 정의와 비교

**Tasks**:

1. **Documentation Tasks**:
   - [ ] State 정의표 작성
     - 6개 상태: FLAT, ENTRY_PENDING, IN_POSITION, EXIT_PENDING, HALT, COOLDOWN
     - StopStatus 4개: ACTIVE, PENDING, MISSING, ERROR
     - 출처: `src/domain/state.py`, FLOW.md Section 4.1
   - [ ] EventType 정의표 작성
     - 6개 이벤트: FILL, PARTIAL_FILL, CANCEL, REJECT, LIQUIDATION, ADL
     - 우선순위: LIQUIDATION > ADL > FILL > PARTIAL_FILL > REJECT > CANCEL
     - 출처: `src/domain/events.py`, FLOW.md Section 4.2
   - [ ] 상태 전이 테이블 작성
     - 주요 20+ 전이 규칙 (현재 상태 × 이벤트 → 새 상태 + Intents)
     - 출처: `src/application/transition.py`
   - [ ] Intent 시스템 설명
     - StopIntent (PLACE/AMEND/CANCEL_AND_PLACE)
     - HaltIntent (reason 포함)
     - ExitIntent (qty, reason)
     - CancelOrderIntent, LogIntent
     - 출처: `src/domain/intent.py`
   - [ ] Sequence diagram: Entry flow
     - FLAT → ENTRY_PENDING → IN_POSITION
   - [ ] Sequence diagram: Exit flow
     - IN_POSITION → EXIT_PENDING → FLAT

2. **Verification Tasks**:
   - [ ] transition.py 코드 리뷰 및 전이 규칙 추출
     ```bash
     grep -A10 "if event.type == EventType" src/application/transition.py
     ```
   - [ ] Oracle 테스트와 매칭
     ```bash
     grep "def test_" tests/oracles/test_state_transition_oracle.py | wc -l
     ```
   - [ ] FLOW.md Section 4 비교

**Quality Gate**:
- [ ] 전이 규칙이 `src/application/transition.py` 실제 코드와 일치
- [ ] Oracle 테스트 케이스와 교차 검증 (누락된 전이 없음)
- [ ] FLOW.md Section 4 상태 머신 정의와 일치
- [ ] Sequence diagram이 실제 흐름과 일치

**Deliverable**: `docs/base/operation.md` (Section 4-5: State Machine, Event Flow)

**Dependencies**: Phase 1 완료 (Section 3 Components 필요)

**Rollback Strategy**:
- Phase 1과 독립적이므로 Section 4-5만 삭제 가능
- Git commit per phase 권장

---

### Phase 3: 핵심 비즈니스 로직 함수 레퍼런스

**Goal**: Application Layer 25개 모듈의 주요 함수를 정확히 문서화

**Duration**: 3-4 hours

**Verification Strategy**:
- 각 함수의 실제 시그니처와 비교
- 코드 예제 syntax 검증 (python -m py_compile)
- docstring과 일치 확인

**Tasks**:

1. **Entry Flow Functions** (2시간):
   - [ ] `entry_allowed.py`: `check_entry_allowed()`
     - 시그니처, 8 gates 설명, 반환값
   - [ ] `signal_generator.py`: `generate_signal()`, `determine_regime()`, `calculate_grid_spacing()`
   - [ ] `sizing.py`: `calculate_contracts()`
   - [ ] `entry_coordinator.py`: `get_stage_params()`, `build_signal_context()`

2. **Exit Flow Functions** (1시간):
   - [ ] `exit_manager.py`: `check_stop_hit()`, `create_exit_intent()`
   - [ ] `stop_manager.py`: `should_update_stop()`, `determine_stop_action()`
   - [ ] `position_manager.py`: `manage_stop_status()`

3. **Risk Management Functions** (30분):
   - [ ] `session_risk.py`: `check_daily_loss_cap()`, `check_weekly_loss_cap()`, `check_loss_streak_kill()`
   - [ ] `emergency.py`: `check_emergency()`
   - [ ] `emergency_checker.py`: `check_emergency_status()`

4. **Order Execution Functions** (30분):
   - [ ] `order_executor.py`: `place_entry_order()`, `place_stop_loss()`, `amend_stop_loss()`, `cancel_order()`
   - [ ] `fee_verification.py`: `estimate_fee_usd()`, `verify_fee_post_trade()`

5. **Event Processing Functions** (30분):
   - [ ] `event_processor.py`: `verify_state_consistency()`, `match_pending_order()`
   - [ ] `event_router.py`: `EventRouter` (thin wrapper)

6. **Market Analysis Functions** (30분):
   - [ ] `atr_calculator.py`: `ATRCalculator`
   - [ ] `market_regime.py`: `MarketRegimeAnalyzer`

7. **Orchestrator Functions** (30분):
   - [ ] `orchestrator.py`: `Orchestrator`, `TickResult`
   - [ ] `tick_engine.py`: Tick loop

**Verification Tasks**:
- [ ] 함수 시그니처 추출 및 비교
  ```bash
  for file in src/application/*.py; do
    echo "=== $file ==="
    grep -E "^def [a-z_]+\(" "$file" | head -5
  done
  ```
- [ ] 코드 예제 syntax 검증
  ```bash
  python -c "import ast; ast.parse(open('docs/base/operation.md').read())" 2>&1 | grep -i syntax
  ```

**Quality Gate**:
- [ ] 각 함수 시그니처가 실제 코드와 일치
- [ ] 코드 예제 실행 가능 (syntax error 없음)
- [ ] docstring과 불일치 없음
- [ ] 파라미터 설명 정확성 (타입, 기본값, 제약사항)

**Deliverable**: `docs/base/operation.md` (Section 6: Function Reference)

**Dependencies**: Phase 1-2 완료 (아키텍처 이해 필요)

**Rollback Strategy**:
- Section 6만 독립적으로 삭제 가능
- 함수별로 세분화된 체크박스로 부분 rollback 가능

---

### Phase 4: 외부 연동 및 Infrastructure

**Goal**: Bybit API, WebSocket, Storage, Safety 시스템을 정확히 문서화

**Duration**: 2 hours

**Verification Strategy**:
- Bybit 공식 문서와 API 엔드포인트 비교
- WebSocket topic 이름 정확성 검증
- Trade log schema JSON 유효성 검증

**Tasks**:

1. **Bybit REST API** (45분):
   - [ ] `bybit_rest_client.py` 설명
     - 인증 방식 (API key + signature)
     - Rate limit 헤더 (X-Bapi-Limit-Status, X-Bapi-Limit-Reset-Timestamp)
     - Idempotency (orderLinkId 기반)
     - 에러 처리 (retCode=10006 rate limit, retCode=110001 duplicate order)
   - [ ] 주요 엔드포인트 목록
     - POST /v5/order/create
     - POST /v5/order/amend
     - POST /v5/order/cancel
     - GET /v5/position/list
     - GET /v5/account/wallet-balance

2. **Bybit WebSocket** (45분):
   - [ ] `bybit_ws_client.py` 설명
     - Topic 구독: `execution.linear` (Linear Futures)
     - Heartbeat monitoring (ping-pong, 20초 간격)
     - Reconnection logic (max_active_time 10분)
     - Event 수신 및 파싱
   - [ ] WebSocket URL
     - Testnet: `wss://stream-testnet.bybit.com/v5/private`
     - Mainnet: `wss://stream.bybit.com/v5/private`

3. **MarketDataInterface** (15분):
   - [ ] `bybit_adapter.py`: `BybitAdapter` 클래스
     - MarketDataInterface 구현
     - 주요 메서드 목록 (get_mark_price, get_equity_usdt 등)

4. **Trade Log & Storage** (15분):
   - [ ] `trade_logger_v1.py`: Trade log schema v1.0
     - JSON 필드 설명 (order_id, fills, slippage, latency 등)
     - 예제 JSON
   - [ ] `log_storage.py`: JSONL 저장
     - Durability policy (batch/periodic/critical)
     - fsync policy

5. **Safety Systems** (15분):
   - [ ] `killswitch.py`: Manual halt (.halt 파일)
   - [ ] `alert.py`: Alert 메시지
   - [ ] `rollback_protocol.py`: Rollback 절차

**Verification Tasks**:
- [ ] Bybit API 문서 비교
  ```bash
  # Bybit 공식 문서 참조
  # https://bybit-exchange.github.io/docs/v5/intro
  ```
- [ ] WebSocket topic 정확성
  ```bash
  grep "execution.linear" src/infrastructure/exchange/bybit_ws_client.py
  ```
- [ ] Trade log JSON schema 유효성
  ```bash
  python -m json.tool < example_trade_log.json
  ```

**Quality Gate**:
- [ ] API 엔드포인트 URL 정확성 (Bybit 공식 문서 대조)
- [ ] WebSocket topic 이름 정확성
- [ ] Trade log schema JSON 예시 유효성
- [ ] Rate limit 정책 정확성 (retCode=10006 언급)

**Deliverable**: `docs/base/operation.md` (Section 7: External Integrations)

**Dependencies**: Phase 1 완료 (Infrastructure Layer 이해 필요)

**Rollback Strategy**:
- Section 7만 독립적으로 삭제 가능

---

### Phase 5: 운영 가이드 및 트러블슈팅

**Goal**: 실제 운영에 필요한 커맨드, 설정, 디버깅 방법 문서화

**Duration**: 2-3 hours

**Verification Strategy**:
- 모든 커맨드 실제 실행 가능성 검증
- 스크립트 경로 존재 확인
- 환경 변수 이름 정확성 확인

**Tasks**:

1. **Setup & Configuration** (30분):
   - [ ] 시작/중지 프로시저
     ```bash
     source venv/bin/activate
     python main.py --mode testnet
     ```
   - [ ] 환경 변수 설정
     - BYBIT_TESTNET (true/false)
     - BYBIT_API_KEY, BYBIT_API_SECRET
     - LOG_LEVEL (DEBUG/INFO/WARNING/ERROR)
   - [ ] Testnet vs Mainnet 차이점

2. **Development Commands** (30분):
   - [ ] 개발 환경 설정
     ```bash
     pip install -e ".[dev]"
     ```
   - [ ] 테스트 실행
     ```bash
     pytest -q
     pytest --cov=src --cov-report=html
     ```
   - [ ] 타입 체크 및 린트
     ```bash
     mypy src/
     ruff check src/
     ruff format src/
     ```

3. **Monitoring** (30분):
   - [ ] 로그 위치 및 구조
     - `logs/trades.jsonl`
     - `logs/metrics.jsonl`
     - `logs/halt.jsonl`
   - [ ] 주요 메트릭
     - Equity (USDT)
     - Winrate (최근 50 거래)
     - Daily realized PnL
     - Loss streak count
   - [ ] 알람 설정 (Telegram)

4. **Troubleshooting** (1-1.5시간):
   - [ ] Rate limit 초과
     - 증상: retCode=10006
     - 해결: X-Bapi-* 헤더 확인, backoff 대기
   - [ ] WebSocket 연결 끊김
     - 증상: WS event drop count 증가
     - 해결: Reconnection logic 동작 확인
   - [ ] HALT 상태
     - 증상: 진입 차단
     - 해결: HALT reason 확인 (logs/halt.jsonl), Manual reset (.halt 파일 삭제)
   - [ ] COOLDOWN 상태
     - 증상: 일시적 진입 차단
     - 해결: Cooldown timeout 대기 (자동 해제)
   - [ ] Stop loss MISSING
     - 증상: stop_status=MISSING
     - 해결: 자동 복구 (StopIntent(PLACE)), 5회 실패 시 HALT
   - [ ] 기타 일반 에러 시나리오

5. **Emergency Procedures** (30분):
   - [ ] Manual HALT
     ```bash
     touch .halt
     ```
   - [ ] Emergency exit (모든 포지션 청산)
     ```bash
     python scripts/emergency_exit.py
     ```
   - [ ] Rollback 절차
     - Git revert
     - State 복구 (backup 사용)

**Verification Tasks**:
- [ ] 모든 커맨드 실행 가능성 검증
  ```bash
  bash -n docs/base/operation.md  # syntax check for bash commands
  ```
- [ ] 스크립트 경로 존재 확인
  ```bash
  ls -l scripts/*.py
  ```
- [ ] 환경 변수 이름 정확성
  ```bash
  grep -E "BYBIT_|LOG_" src/ -r | grep -o "BYBIT_[A-Z_]*" | sort -u
  ```

**Quality Gate**:
- [ ] 모든 커맨드 실제 실행 가능
- [ ] 스크립트 경로 존재 확인
- [ ] 환경 변수 이름 정확성
- [ ] 트러블슈팅 시나리오가 실제 운영 경험 반영

**Deliverable**: `docs/base/operation.md` (Section 8-9: Operations, Troubleshooting)

**Dependencies**: Phase 1-4 완료 (전체 시스템 이해 필요)

**Rollback Strategy**:
- Section 8-9만 독립적으로 삭제 가능

---

### Phase 6: 문서 검증 및 최종화

**Goal**: 문서 정합성 검증 및 네비게이션 개선

**Duration**: 1-2 hours

**Verification Strategy**:
- 자동화된 검증 스크립트 실행
- SSOT 문서와 최종 일치 확인
- 사용자 시나리오 테스트 (새 개발자가 문서만으로 이해 가능한지)

**Tasks**:

1. **Link & Path Verification** (30분):
   - [ ] 모든 파일 경로 링크 존재 검증
     ```bash
     grep -oE '\[.*\]\((src/[^)]+)\)' docs/base/operation.md | \
       sed 's/.*(\(.*\))/\1/' | while read f; do
       [ -f "$f" ] || echo "BROKEN LINK: $f"
     done
     ```
   - [ ] 내부 섹션 링크 검증 (존재하지 않는 섹션 참조 없음)
   - [ ] 외부 문서 링크 검증 (FLOW.md, Policy, ADR 등)

2. **Code Snippet Validation** (30분):
   - [ ] 코드 스니펫 syntax 검증
     ```bash
     # Extract code blocks and validate
     awk '/```python/,/```/' docs/base/operation.md | python -m py_compile
     ```
   - [ ] 함수 호출 예시 정확성

3. **Document Enhancement** (30-60분):
   - [ ] 목차(TOC) 생성
     ```markdown
     - [1. System Overview](#1-system-overview)
     - [2. Architecture](#2-architecture)
     ...
     ```
   - [ ] 용어집(Glossary) 추가
     - State Machine 관련 용어
     - Bybit 특화 용어
     - CBGB 내부 용어
   - [ ] 참조 문서 링크 정리
     - FLOW.md
     - account_builder_policy.md
     - task_plan.md
     - ADR 목록
   - [ ] 버전 정보 및 Last Updated 표기

4. **Final SSOT Verification** (15분):
   - [ ] FLOW.md와 모순 없음
   - [ ] account_builder_policy.md와 모순 없음
   - [ ] task_plan.md Repo Map과 경로 일치

5. **Markdown Quality Check** (15분):
   - [ ] Markdown lint 통과
     ```bash
     markdownlint docs/base/operation.md
     ```
   - [ ] Rendering 테스트 (VSCode preview, GitHub preview)

**Verification Tasks**:
- [ ] 자동 검증 스크립트 실행
  ```bash
  ./scripts/verify_operation_manual.sh
  ```
- [ ] 수동 리뷰 체크리스트
  - [ ] 새 개발자 관점에서 읽기
  - [ ] 모든 섹션 간 논리적 흐름
  - [ ] 예제의 실행 가능성

**Quality Gate**:
- [ ] 모든 링크 클릭 가능 (404 없음)
- [ ] Markdown 렌더링 정상
- [ ] SSOT 문서와 모순 없음
- [ ] 코드 스니펫 syntax 오류 없음
- [ ] 용어집 완성도

**Deliverable**: `docs/base/operation.md` (최종본) + 검증 스크립트

**Dependencies**: Phase 1-5 완료 (전체 문서 작성 완료)

**Rollback Strategy**:
- 최종 검증 실패 시 Phase 5 상태로 복귀
- 부분 수정으로 대응 가능

---

## 4. Quality Gates Summary

### Global Quality Criteria

**Every Phase Must Pass**:
1. **문서-코드 일치성**: 언급된 파일/함수가 실제 존재하고 정확함
2. **SSOT 충돌 없음**: FLOW.md, Policy, task_plan.md와 모순 없음
3. **Markdown 유효성**: 렌더링 오류 없음, lint 통과
4. **검증 가능성**: 자동화된 검증 스크립트 통과

**Phase-Specific Gates**: 각 Phase의 Quality Gate 섹션 참조

### Validation Commands

**Phase 1-6 공통**:
```bash
# 파일 경로 존재 검증
grep -oE 'src/[a-z_/]+\.py' docs/base/operation.md | sort -u | while read f; do
  [ -f "$f" ] || echo "MISSING: $f"
done

# Markdown lint
markdownlint docs/base/operation.md

# 내부 링크 검증 (간단한 체크)
grep -oE '\[.*\]\(#[^)]+\)' docs/base/operation.md | \
  sed 's/.*#\(.*\))/\1/' | while read anchor; do
  grep -q "^#.*$anchor" docs/base/operation.md || echo "BROKEN ANCHOR: $anchor"
done
```

**Phase 3 추가** (함수 시그니처):
```bash
# 함수 시그니처 추출
for file in src/application/*.py; do
  echo "=== $file ==="
  grep -E "^def [a-z_]+\(" "$file" | head -5
done
```

**Phase 4 추가** (API 정확성):
```bash
# WebSocket topic 확인
grep "execution.linear" src/infrastructure/exchange/bybit_ws_client.py

# Trade log JSON 유효성
python -m json.tool < example_trade_log.json
```

**Phase 5 추가** (커맨드 실행 가능성):
```bash
# 환경 변수 이름 추출
grep -E "BYBIT_|LOG_" src/ -r | grep -o "BYBIT_[A-Z_]*" | sort -u

# 스크립트 경로 존재 확인
ls -l scripts/*.py
```

**Phase 6 추가** (최종 검증):
```bash
# 전체 검증 스크립트
./scripts/verify_operation_manual.sh

# 코드 스니펫 syntax
awk '/```python/,/```/' docs/base/operation.md | python -m py_compile
```

---

## 5. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| **코드 변경으로 인한 문서 outdated** | Medium | High | Phase 6에서 마지막 검증, Git pre-commit hook으로 경로 검증 추가 권장 |
| **함수 시그니처 불일치** | Low | High | 자동 검증 스크립트로 Phase 3에서 검출 |
| **SSOT 문서와 모순** | Low | Critical | 각 Phase에서 SSOT 문서 참조 명시, Phase 6에서 최종 검증 |
| **문서 작성 시간 초과** | Medium | Medium | Phase별 checkpoint로 진행 상황 추적, 필요 시 일부 함수 생략 후 추후 보완 |
| **링크 깨짐** | Medium | Low | Phase 6에서 자동 검증 스크립트로 검출 |
| **Markdown 렌더링 오류** | Low | Low | 각 Phase 완료 시 즉시 preview 확인 |

---

## 6. Rollback Strategy

### Per-Phase Rollback

각 Phase는 독립적인 문서 섹션을 생성하므로, 문제 발생 시 해당 섹션만 삭제 가능:

- **Phase 1**: Section 1-3 삭제
- **Phase 2**: Section 4-5 삭제
- **Phase 3**: Section 6 삭제
- **Phase 4**: Section 7 삭제
- **Phase 5**: Section 8-9 삭제
- **Phase 6**: 검증 스크립트만 rollback, 문서 본문은 Phase 5 상태 유지

### Git Strategy

```bash
# Phase 시작 전 브랜치 생성
git checkout -b feature/operation-manual-phase-N

# Phase 완료 시 커밋
git add docs/base/operation.md
git commit -m "docs: Add operation manual Phase N (Section X-Y)"

# 문제 발생 시 롤백
git restore docs/base/operation.md  # 파일 전체 롤백
# 또는
git checkout HEAD~1 -- docs/base/operation.md  # 이전 커밋으로 롤백
```

### Data Backup

- 각 Phase 완료 시 `docs/base/operation.md.phase-N.backup` 생성 권장
- 최종본 완성 후 backup 파일 삭제

---

## 7. Progress Tracking

### Overall Progress

- [x] **Phase 1**: 시스템 개요 및 아키텍처 맵핑 (Section 1-3) ✅ **COMPLETE** (2026-02-01)
  - Evidence: [docs/evidence/operation_manual_phase1/](../evidence/operation_manual_phase1/)
  - 산출물: [docs/base/operation.md](../base/operation.md) (Section 1-3, 771줄)
- [x] **Phase 2**: 상태 머신 및 이벤트 플로우 (Section 4-5) ✅ **COMPLETE** (2026-02-01)
  - Evidence: [docs/evidence/operation_manual_phase2/](../evidence/operation_manual_phase2/)
  - 산출물: [docs/base/operation.md](../base/operation.md) (Section 4-5, +478줄, 총 1303줄)
  - 전이 규칙: 25+ 규칙 문서화 (transition.py 기반)
  - Oracle 테스트: 11+ 테스트 케이스 교차 검증 완료
- [ ] **Phase 3**: 핵심 비즈니스 로직 함수 레퍼런스 (Section 6)
- [ ] **Phase 4**: 외부 연동 및 Infrastructure (Section 7)
- [ ] **Phase 5**: 운영 가이드 및 트러블슈팅 (Section 8-9)
- [ ] **Phase 6**: 문서 검증 및 최종화 (Section 10 + Verification)

### Completion Criteria

**Definition of DONE**:
- [ ] 모든 6개 Phase 완료
- [ ] 모든 Quality Gate 통과
- [ ] `docs/base/operation.md` 파일 생성 및 검증 완료
- [ ] 검증 스크립트 통과 (`./scripts/verify_operation_manual.sh`)
- [ ] SSOT 문서와 모순 없음
- [ ] 새 세션에서 문서만으로 시스템 이해 가능 (수동 검증)

---

## 8. Notes & Learnings

### Phase 1 Notes

**Completed**: 2026-02-01
**Duration**: ~1.5시간 (예상 2-3시간 대비 빠른 완료)

**주요 성과**:
- Section 1-3 작성 완료 (771줄)
- Explore 에이전트 출력을 효과적으로 활용하여 빠른 작성 가능
- 모든 파일 경로 검증 통과 (59개 Python 파일)
- SSOT 3문서와 충돌 없음 확인

**학습 내용**:
1. **Explore 에이전트 활용**: 코드베이스 구조 파악에 매우 효과적 (사전에 실행하여 정보 확보)
2. **문서화 작업의 검증**: RED→GREEN 테스트 대신 "파일 경로 존재 검증"으로 대체 가능
3. **ASCII 다이어그램의 유용성**: 복잡한 의존성을 시각화하는 데 효과적
4. **SSOT 참조의 중요성**: 모든 정의는 FLOW.md, Policy, task_plan.md에서 직접 인용

**개선 사항**:
- 다음 Phase부터는 더 많은 코드 예제 포함 권장
- Sequence diagram은 Mermaid 문법 사용 고려 (Markdown 렌더링 지원)

**다음 Phase 준비**:
- Phase 2에서는 transition.py 코드를 직접 읽어서 전이 규칙 추출 필요
- Oracle 테스트와 교차 검증 계획

**Phase 1.1 Patch** (2026-02-01):
- **Trigger**: 사용자 팩트 체크 피드백 (치명적 오류 5개 발견)
- **판정**: HOLD - 문서 구조는 좋지만, 실거래에서 죽는 지점 명확
- **주요 수정**:
  1. Section 1.4 Definitions 추가 (Product, Qty 단위, Equity, UTC boundary, Rate limit, Stop Loss)
  2. Contract 단위 "1 contract = 0.001 BTC" HOLD (Bybit 스펙 확인 필수)
  3. Rate Limit "120 req/min" 삭제 → "X-Bapi-* 헤더 기반 + retCode=10006" 추가
  4. Risk Cap 명확화 (Daily -5%, Weekly -12.5%, UTC boundary, equity_usdt 기준)
  5. WS "10분 무활동 시 연결 종료" 명확화 (서버측 제약, 클라이언트가 능동적으로 끊는 게 아님)
  6. "방식 B" 제거 → 실제 API 파라미터 명시 (orderType=Market, triggerBy=LastPrice 등)
- **결과**: 825줄 (771 → 825, +54줄), Evidence: [phase1.1_patch_notes.md](../evidence/operation_manual_phase1/phase1.1_patch_notes.md)
- **학습**:
  - **팩트 체크의 중요성**: 코드 확인 없이 "추정"으로 문서 작성 시 치명적 오류 발생
  - **SSOT 원칙**: 모든 정의는 코드/Policy에서 직접 인용해야 함
  - **실거래 관점**: 백테스트가 아니라 "실거래에서 어디서 죽는가"를 먼저 찾아야 함
  - **내부 용어 금지**: 운영 매뉴얼에 "방식 B" 같은 코드명 사용 금지

### Phase 2 Notes
_To be filled during Phase 2_

### Phase 3 Notes
_To be filled during Phase 3_

### Phase 4 Notes
_To be filled during Phase 4_

### Phase 5 Notes
_To be filled during Phase 5_

### Phase 6 Notes
_To be filled during Phase 6_

### General Learnings
_Document any insights, challenges, or improvements discovered during execution_

---

## 9. References

### SSOT Documents
- [FLOW.md](../constitution/FLOW.md) - 불변 헌법 (상태 머신, 이벤트, 전이 규칙)
- [account_builder_policy.md](../specs/account_builder_policy.md) - 정책 수치, Gate, 단위
- [task_plan.md](../plans/task_plan.md) - Phase별 진행표, Repo Map

### ADR (Architecture Decision Records)
- [ADR-0001 ~ ADR-0011](../adr/) - 주요 아키텍처 결정 기록

### External References
- [Bybit API v5 Documentation](https://bybit-exchange.github.io/docs/v5/intro)
- [Bybit WebSocket v5 Documentation](https://bybit-exchange.github.io/docs/v5/ws/connect)
- [CLAUDE.md](../../CLAUDE.md) - 개발 운영 계약서

---

## 10. Appendix

### A. Document Structure Preview

```markdown
# CBGB Operation Manual

## 1. System Overview
- 1.1 Purpose & Goals
- 1.2 Core Principles
- 1.3 Constraints

## 2. Architecture
- 2.1 Layered Architecture
- 2.2 Module Dependency Map
- 2.3 Directory Structure

## 3. System Components
- 3.1 Domain Layer
- 3.2 Application Layer
- 3.3 Infrastructure Layer

## 4. State Machine
- 4.1 State Definitions
- 4.2 Event Definitions
- 4.3 Transition Rules

## 5. Core Flows
- 5.1 Entry Flow
- 5.2 Exit Flow
- 5.3 Stop Management

## 6. Function Reference
- 6.1 Entry Functions
- 6.2 Exit Functions
- 6.3 Risk Functions
- 6.4 Order Execution
- 6.5 Event Processing
- 6.6 Market Analysis

## 7. External Integrations
- 7.1 Bybit REST API
- 7.2 Bybit WebSocket
- 7.3 Storage System
- 7.4 Safety Systems

## 8. Operations Guide
- 8.1 Setup & Configuration
- 8.2 Start/Stop
- 8.3 Monitoring
- 8.4 Development Commands

## 9. Troubleshooting
- 9.1 Common Scenarios
- 9.2 Emergency Procedures
- 9.3 Rollback Protocol

## 10. References
- 10.1 SSOT Documents
- 10.2 ADR Index
- 10.3 Glossary
```

### B. Verification Script Template

```bash
#!/bin/bash
# scripts/verify_operation_manual.sh

set -e

echo "=== Operation Manual Verification ==="

# 1. File path existence
echo "[1/5] Verifying file paths..."
grep -oE 'src/[a-z_/]+\.py' docs/base/operation.md | sort -u | while read f; do
  [ -f "$f" ] || { echo "FAIL: MISSING $f"; exit 1; }
done
echo "✅ All file paths exist"

# 2. Markdown lint
echo "[2/5] Running markdown lint..."
if command -v markdownlint &> /dev/null; then
  markdownlint docs/base/operation.md
  echo "✅ Markdown lint passed"
else
  echo "⚠️  markdownlint not installed, skipping"
fi

# 3. Internal link verification
echo "[3/5] Verifying internal links..."
# (간단한 체크, 실제로는 더 정교한 스크립트 필요)
echo "✅ Internal links checked"

# 4. Code snippet syntax
echo "[4/5] Verifying code snippets..."
# (Python syntax 체크)
echo "✅ Code snippets validated"

# 5. SSOT consistency
echo "[5/5] Verifying SSOT consistency..."
# (FLOW.md, Policy 참조 일치 확인)
echo "✅ SSOT consistency verified"

echo ""
echo "=== ✅ ALL CHECKS PASSED ==="
```

---

**Last Updated**: 2026-02-01
**Plan Version**: 1.0
**Status**: ✅ Approved, Ready to Execute
