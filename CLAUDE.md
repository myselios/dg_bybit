# CLAUDE.md — CBGB (Controlled BTC Growth Bot) 개발 운영 계약서
Last Updated: 2026-01-18

이 문서는 Claude Code(claude.ai/code) 및 모든 구현자가 **이 레포에서 작업할 때 따라야 하는 운영 계약서**다.  
목적은 좋은 말이 아니라 **실거래에서 살아남는 구현**이다.

---

## 1) 프로젝트 개요 (Project Overview)

**CBGB (Controlled BTC Growth Bot)** — Bybit Inverse(코인마진드) Futures 기반 BTC 트레이딩 봇

### Core Objective
- **목표**: USD 가치 증가 ($100 → $1,000, BTC 수량 무관)
- **시장**: Bybit BTC Coin-Margined (Inverse) Futures only
- **전략**: Directional-filtered Grid Strategy
- **측정 기준**: USD Equity = (equity_btc × BTC_mark_price_usd)

### 절대 금지 (Critical Constraints)
- **청산(Liquidation) = 실패** (Drawdown ≠ 실패)
- **Martingale 금지**, 무제한 물타기 금지
- 레버리지/스테이지/손실예산/EV/수수료/위험정의는 **정책 문서(SSOT)만** 따른다 (이 파일에서 숫자 박지 않는다)

---

## 2) 🔴 응답/분석 관점 규칙 (Response Perspective Rules)

1. 역할: **클린 아키텍트 + 전문 퀀트 개발자 관점**으로만 판단한다.
2. 판단 기준: 백테스트가 아니라 **실거래 생존성**이 기준이다.
3. 팩트 우선: 코드·문서를 직접 확인한 후 판단한다. 확인 불가 시 **팩트 확인 불가**를 명시한다.
4. 추측 금지: 가정은 가정으로 분리 표기하며, 추측으로 결론을 내리지 않는다.
5. 객관성 유지: 미사여구/감정표현 배제, 증거 기반으로 설명한다.
6. 아부 금지: 칭찬/완곡/미화 금지.
7. 비판 우선: 실패 지점과 구조적 취약성부터 탐색한다.
8. 직설적 지적: 문제는 완화 없이 명확히 지적한다.
9. 건설적 비판 형식(필수):
   - 문제 지점
   - 왜 문제인지
   - 방치 시 결과
   - 개선 방향
10. 아키텍처 검증: 책임 분리, 의존성 방향, 경계 침범 여부 점검.
11. 리스크 관점: 손실 상한, 중단 조건, 복구 가능성 필수 검토.
12. 성장 지향: 단기 성과보다 장기 운영 안정성을 우선한다.

권장 출력 구조: **결론 → 치명적 문제 → 리스크 분석 → 개선 제안**

---

## 3) 언어 규칙 (Language Rules)

**중요: 모든 커뮤니케이션과 문서는 한국어로 작성**

- Claude의 모든 답변: 한국어
- 문서: 한국어
- 코드 식별자(변수/함수/클래스): 영어 (PEP8)
- 코드 주석/docstring: **새로 작성/수정하는 부분은 한국어 우선**
- 예외:
  - Git 커밋 메시지: 영어
  - 외부 라이브러리 인용: 원문 유지

---

## 4) Single Source of Truth (SSOT) — 최상위 문서 3개 (협상 불가)

아래 3개 문서만이 **단일 진실(Single Source of Truth)** 이다.  
정의/단위/우선순위/흐름/게이트 판단은 이 3개를 기준으로 한다.

1) `docs/constitution/FLOW.md`  
- 실행 순서, 상태 전환, 모드 규칙(헌법)

2) `docs/specs/account_builder_policy.md`  
- 정책 수치, 게이트 정의, 단위, 스키마(ADR 대상 포함)

3) `docs/plans/task_plan.md`  
- Gate 기반 구현 순서, DoD, 진행표(체크박스와 Evidence)

### 기타 문서의 지위
- `docs/PRD.md`, `docs/STRATEGY.md`, `docs/RISK.md` 등은 **참고 자료**다.
- 참고 문서 내용이 SSOT(3문서)와 충돌하면 **SSOT가 우선**이며,
  충돌 해결은 SSOT 수정(필요 시 ADR)로만 수행한다.

---

## 5) Pre-flight Hard Gates (Phase 진행 전 선행 강제 조건)

현재 레포는 “문서가 아니라 테스트가 단속 장치가 되어야 한다”를 목표로 한다.  
따라서 Phase(0~6) 진행 전에 아래 조건을 먼저 만족해야 한다.

### 5.1 Placeholder 테스트 금지 (Zero Tolerance)
- `assert True`, `pass`, `TODO` 포함 테스트는 **테스트가 아니다**
- 첫 작업은 오라클을 “진짜 assert”로 만드는 것(RED→GREEN 증명)

### 5.2 테스트가 도메인을 재정의하는 행위 금지
- 테스트에서 Position/Pending/Event/State를 별도 dataclass로 만들지 않는다
- 반드시 `src/domain/*`에 정의된 타입만 사용한다

### 5.3 단일 전이 진실 (Single Transition Truth)
- 상태 전이 규칙은 **오직 transition()** 에만 존재해야 한다
- Router/Handler는 transition()을 호출하는 thin wrapper로만 유지한다
- 전이 로직이 2군데 이상 있으면 즉시 중복 제거 후 진행한다

### 5.4 Docs vs Repo 경로 정렬
- `task_plan.md`의 Repo Map과 실제 코드 경로가 다르면 Phase 0에서 정렬한다
  - (A) 코드를 문서 경로로 이동하거나
  - (B) 문서를 실제 경로로 수정한다
- 어느 쪽이든 “단일 진실 경로” 확정 전에는 다음 Phase로 넘어가지 않는다

### 5.5 DONE 증거는 pytest 실행 결과
- 각 체크박스 DONE은 **pytest 실행 결과(RED→GREEN)** 로 증명해야 한다
- “통과했을 것” 추정 금지

### 5.6 문서 업데이트는 작업의 일부
- 완료 시 `docs/plans/task_plan.md`:
  - Last Updated 갱신
  - Progress Table에서 TODO→DOING→DONE 업데이트
  - Evidence에 (테스트 경로 + 구현 경로 + 가능하면 커밋 해시) 기록
- 문서 업데이트가 없으면 DONE 인정하지 않는다

### 5.7 Self-Verification Before DONE (완료 보고 전 필수 검증)
**"DONE" 체크 / 완료 보고 전 반드시 아래 검증을 통과해야 한다.**

검증 실패 시: DONE 보고 금지 → 즉시 수정.

#### (1) Placeholder 테스트 0개 (Gate 1)
아래 패턴이 1개라도 검출되면 FAIL:
- `assert True`
- `pytest.skip(` (정당한 사유 없이)
- `pass  # TODO`
- `TODO: implement`
- `raise NotImplementedError`

```bash
# (1a) Placeholder 표현 감지
grep -RInE "assert[[:space:]]+True|pytest\.skip\(|pass[[:space:]]*#.*TODO|TODO: implement|NotImplementedError|RuntimeError\(.*TODO" tests/ 2>/dev/null | grep -v "\.pyc"
# → 출력: 비어있음

# (1b) Skip/Xfail decorator 금지 (정당한 사유 없으면 FAIL)
grep -RInE "pytest\.mark\.(skip|xfail)|@pytest\.mark\.(skip|xfail)|unittest\.SkipTest" tests/ 2>/dev/null | grep -v "\.pyc"
# → 출력: 비어있음 (또는 특정 allowlist 경로만)

# (1c) 의미있는 assert 존재 여부 (거친 체크)
# 각 test_ 함수에 최소 1개 이상의 도메인 값 비교 assert 필요
# 예: assert new_state == State.IN_POSITION
grep -RIn "assert .*==" tests/ 2>/dev/null | wc -l
# → 출력: 0이 아님 (테스트가 있으면 반드시 비교 assert 존재)
```

#### (2) 테스트에서 "도메인 타입 이름" 재정의 금지 (Gate 2)
금지: Position, PendingOrder, ExecutionEvent, State 등 domain과 동일 이름 재정의.
허용: helper는 Dummy*, Fake*, Test* 접두어를 강제.
**절대 금지: tests/ 내에서 domain을 모사하는 파일 생성 (domain_state.py 등)**

```bash
# (2a) 도메인 타입 이름 재정의 금지
grep -RInE "^class[[:space:]]+(Position|PendingOrder|ExecutionEvent|State)\b" tests/ 2>/dev/null | grep -v "\.pyc"
# → 출력: 비어있음

# (2b) tests/ 내에 domain 모사 파일 생성 금지
find tests -type f -maxdepth 3 -name "*.py" 2>/dev/null | grep -E "(domain|state|intent|events)\.py"
# → 출력: 비어있음 (또는 allowlist만)
# 허용 예외: tests/fixtures/test_helpers.py 같은 명백한 helper만
```

#### (3) transition SSOT 파일 존재 (Gate 3)
```bash
test -f src/application/transition.py && echo "OK: transition.py exists" || (echo "FAIL: missing transition.py" && exit 1)
# → 출력: OK: transition.py exists
```

#### (4) EventRouter/Handler에 상태 분기 로직 금지 (Gate 3)
EventRouter는 thin wrapper여야 한다. `if state ==` / `elif state ==` 존재하면 FAIL.
**더 강한 규칙: EventRouter에서 `State.` 참조 자체를 금지 (dict dispatch, match/case 우회 차단)**

```bash
# (4a) 상태 분기문 감지 (if/elif state ==)
grep -RInE "if[[:space:]]+.*state[[:space:]]*==|elif[[:space:]]+.*state[[:space:]]*==" src/application/event_router.py src/application/services/event_router.py 2>/dev/null
# → 출력: 비어있음

# (4b) EventRouter에서 State enum 참조 자체 금지 (thin wrapper 강제)
grep -n "State\." src/application/event_router.py src/application/services/event_router.py 2>/dev/null
# → 출력: 비어있음
# 이 규칙으로 dict dispatch, match/case, 함수 이름 분기 전부 차단
```

#### (5) sys.path hack 금지 (구조 위반)
```bash
grep -RIn "sys\.path\.insert" src/ tests/ 2>/dev/null
# → 출력: 비어있음
```

#### (6) Deprecated wrapper import 사용 금지 (예외: 삭제 전 임시 단계만 허용)
Phase 1 시작 시점부터는 아래 import가 0이어야 한다:
- `application.services.state_transition`
- `application.services.event_router`

**Migration Protocol (Section 8.1) 준수 증거: 구 경로 import 0개**

```bash
# (6a) Deprecated wrapper import 추적
grep -RInE "application\.services\.(state_transition|event_router)" tests/ src/ 2>/dev/null
# → Phase 0/0.5: 허용 (단, 신규 추가 금지)
# → Phase 1+: 출력 비어있어야 함

# (6b) Migration 완료 증거 (구 경로 import 0개, Phase 1+ 필수)
grep -RInE "from application\.services|import application\.services" tests/ src/ 2>/dev/null | wc -l
# → Phase 1+: 출력 0 (Migration 완료)
```

#### (7) pytest 증거 + 문서 업데이트 (Gate 5/6)
```bash
pytest -q
# → PASS 결과를 Evidence에 기록 (명령어 + 결과 라인)

git status
git diff --stat
# → 의도한 파일만 변경되었는지 확인
```

---

**검증 성공 시 DONE 절차**:
1. pytest PASS 결과를 task_plan.md Evidence에 기록
2. Progress Table 업데이트 (체크박스 + Evidence 경로)
3. Last Updated 갱신
4. **5.7 커맨드 출력 결과 (붙여넣기) 또는 스크린샷을 DONE 보고에 필수 포함**
5. DONE 보고

---

**DONE 무효 조건 (자동 거부)**:
- Gate 7 커맨드 출력이 DONE 보고에 없으면 → **DONE 보고는 자동 무효**
- 출력 증거 없이 "검증 완료했습니다" 말만 하면 → **DONE 인정 불가**
- Placeholder 테스트(1a~1c), 도메인 재정의(2a~2b), 전이 분기(4a~4b) 중 1개라도 검출되면 → **즉시 수정 후 재보고**

---

## 6) ADR 규칙 (정책/정의/단위 변경 통제)

다음에 해당하면 **작업을 중단하고 ADR 필요성을 보고**한다:
- 정책 수치가 아니라 **정의/단위/스키마/우선순위/불변 규칙** 변경
- 상태 머신/모드/이벤트 의미 변경
- fee 단위, inverse 계산 단위, sizing 단위 변경
- SSOT 문서의 “협상 불가/불변” 섹션 변경

원칙:
- “코드로 먼저 바꾸고 문서 맞추기” 금지
- 먼저 ADR/SSOT 업데이트 → 구현

---

## 7) 구현 원칙 (Architecture & Boundaries)

### 7.1 transition() 순수성 (협상 불가)
- `transition()`은 **pure(무 I/O)** 함수다
- 외부 I/O(REST/WS/DB/로그)는 executor/adapter에서만 수행한다
- transition 입력은 “현재 상태 스냅샷 + 이벤트”로 제한한다
- transition 출력은 “새 상태 + intents(부수효과 명시)”로 반환한다

### 7.2 Intent 패턴
- Stop 갱신, 주문 취소, HALT, 로그 등 부수효과는 **Intent로 명시**
- “상태만 바꾸고 실제 행동 규칙이 사라지는 구현” 금지

### 7.3 통합 테스트 범위 제한
- Integration/E2E 테스트는 “연결 확인” 용도로만 5~10개 유지
- 핵심 검증은 Oracle/Unit이 담당한다 (빠르고 결정적이어야 한다)

---

## 8) 작업 절차 (Gate-Driven Workflow)

1) SSOT 3문서 읽고 오늘 작업 범위를 확정한다
2) 가장 먼저 TODO인 Phase/Task를 선택한다(Pre-flight 미완료면 Pre-flight부터)
3) 테스트 먼저 작성 → RED 확인
4) 최소 구현으로 GREEN 만들기
5) 리팩토링(중복 제거, 책임 분리)
6) pytest 재실행으로 증거 확보
7) `docs/plans/task_plan.md` 진행표/Last Updated/Evidence 업데이트

### 8.1 Migration Protocol (구조 변경 시 필수 절차)

**파일 이동/삭제/경로 변경 시 반드시 아래 순서를 따른다**

#### Phase 1: 현재 상태 확인
```bash
# 1) 대상 파일 존재 확인
ls -la src/path/to/old_file.py

# 2) 누가 이 파일을 import하는가? (의존성 파악)
grep -R "from .* import\|import .*old_file" src/ tests/ 2>/dev/null

# 3) 구 경로와 신 경로 명확히 정의
# 구: src/application/services/event_router.py
# 신: src/application/event_router.py
```

#### Phase 2: 새 구조 생성
```bash
# 4) 새 파일 생성 (thin wrapper 등)
# 5) 새 파일이 SSOT transition()을 올바르게 호출하는지 확인
```

#### Phase 3: Import Path 전환 (Critical!)
```bash
# 6) 테스트 import path 변경
# Before: from application.services.state_transition import ...
# After:  from application.transition import ...

# 7) 모든 참조 검색 후 변경
grep -R "from application.services" tests/ src/

# 8) 변경 후 grep 재실행 → 남은 참조 0개 확인
```

#### Phase 4: 구 파일 처리
```bash
# 9) 구 파일을 삭제하거나 deprecated wrapper로 전환
# Deprecated wrapper 예시:
# """⚠️ DEPRECATED: Use src/application/transition.py instead"""
# from application.transition import transition  # Re-export

# 10) 삭제 시 git rm, wrapper 전환 시 명확히 표기
```

#### Phase 5: 검증
```bash
# 11) Section 5.7 Self-Verification 커맨드 전체 실행
# 12) pytest 실행 → 모든 테스트 통과 확인
# 13) git diff --stat → 의도한 파일만 변경되었는가?
```

#### Phase 6: 문서화
```bash
# 14) Repo Map 업데이트 (task_plan.md)
# 15) Evidence에 "구→신 경로 변경" 명시
# 16) Deprecated wrapper 삭제 조건 DoD에 명시
```

**금지 사항**:
- 새 파일 생성 후 구 파일 방치 → **전이 진실 2개 공존**
- Import path 변경 없이 새 파일만 생성 → **테스트가 구 구조 참조**
- "나중에 정리하겠다" → **늪 영구화**

**Migration 완료 기준**:
1. 구 경로 import 0개 (deprecated wrapper 제외)
2. 새 경로가 SSOT로 동작
3. 테스트가 새 경로 사용
4. pytest 통과
5. Repo Map 일치

---

## 9) 개발 커맨드 (Development Commands)

```bash
# 가상환경 활성화 (필수)
source venv/bin/activate

# 패키지 editable mode 설치 (최초 1회 또는 pyproject.toml 변경 시)
pip install -e .

# 개발 의존성 설치 (pytest, mypy, ruff 등)
pip install -e ".[dev]"

# 전체 테스트 (PYTHONPATH 설정 불필요)
pytest -q

# 단일 테스트 파일
pytest -q tests/oracles/test_state_transition_oracle.py
pytest -q tests/unit/test_example.py -v

# 특정 테스트 함수
pytest -q tests/unit/test_example.py::test_function_name -v

# 커버리지
pytest --cov=src --cov-report=html

# 타입 체크
mypy src/

# 린트/포맷
ruff check src/
ruff format src/
## 최소 품질 게이트 (권장, DoD에 포함)
PR/완료 시 최소:
- `ruff check src/` 통과
- `mypy src/` 통과 (도입된 영역 기준)
- `pytest -q` 또는 관련 타겟 테스트 통과

**중요**: 테스트는 `pip install -e .[dev]` 이후 **PYTHONPATH 설정 없이** `pytest` 명령어만으로 실행되어야 한다.

**패키징 표준 (SSOT)**:
- 최초 설정: `pip install -e .[dev]` (pytest, mypy, ruff 등 개발 도구 포함)
- 테스트 실행: `pytest -q` (PYTHONPATH 불필요)
- CI/자동화: 항상 `pip install -e .[dev]` 후 pytest 실행

10) 레포 구조 (현재/정렬 규칙)
구조는 docs/plans/task_plan.md의 Repo Map을 기준으로 정렬한다.

Repo Map과 실제가 다르면 Phase 0에서 정렬하며, 정렬 완료 전 다음 Phase 진행 금지.

11) 작업 출력 형식 (요청 시 고정 포맷)
지금 구현할 체크박스/항목(Phase/Task)

추가/수정할 파일 목록

작성/수정할 테스트 목록(테스트 이름까지)

구현 요약(의도/경계조건/거절 사유 코드 포함)

완료 후 문서 업데이트 내용(Progress Table 행 업데이트 + Evidence)