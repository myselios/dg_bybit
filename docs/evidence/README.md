# Evidence Directory — Immutable Completion Artifacts

## 목적 (Purpose)

이 디렉토리는 **"컨텍스트 단절 시에도 검증 가능한 완료 증거"** 를 저장합니다.

### 핵심 원칙
1. **"사람의 말이 아니라 artifact가 증거다"**
2. **새 세션에서도 "이 Phase가 진짜 DONE인지" 검증 가능**
3. **Progress Table의 [x] 체크박스보다 Evidence 파일이 우선**

---

## 디렉토리 구조 (Structure)

```
docs/evidence/
├── README.md (본 문서)
├── phase_0/
│   ├── completion_checklist.md    # DoD 체크리스트 + 자체 검증
│   ├── gate7_verification.txt     # CLAUDE.md Section 5.7 커맨드 7개 출력
│   ├── pytest_output.txt          # pytest -q 실행 결과
│   ├── file_tree.txt              # ls -laR src/ (Repo Map 정렬 증거)
│   └── red_green_proof.md         # RED→GREEN 재현 증거
├── phase_1/
│   ├── completion_checklist.md
│   ├── gate7_verification.txt
│   ├── pytest_output.txt
│   ├── emergency_thresholds_verification.txt  # Policy 임계값 일치 증거
│   └── red_green_proof.md
└── ... (Phase 2~6)
```

---

## Phase 완료 시 필수 파일 (Required Files per Phase)

각 Phase 완료 시 반드시 아래 4~5개 파일을 생성해야 합니다:

### 1) `completion_checklist.md` (필수)
- **목적**: DoD(Definition of Done) 자체 검증 결과
- **내용**:
  - Metadata (Phase, Date, Commit Hash)
  - DoD 5개 항목 체크리스트
  - Deliverables 검증
  - 새 세션 검증 커맨드

### 2) `gate7_verification.txt` (필수)
- **목적**: CLAUDE.md Section 5.7 Self-Verification 출력 전문
- **생성 방법**:
  ```bash
  # (1a) Placeholder
  grep -RInE "assert[[:space:]]+True|pytest\.skip\(" tests/ > gate7_verification.txt
  # (1b) Skip/Xfail
  grep -RInE "pytest\.mark\.(skip|xfail)" tests/ >> gate7_verification.txt
  # ... (7개 커맨드 출력 모두 포함)
  ```

### 3) `pytest_output.txt` (필수)
- **목적**: pytest 실행 결과 (통과 개수 + 시간)
- **생성 방법**:
  ```bash
  pytest -q > pytest_output.txt 2>&1
  ```

### 4) `red_green_proof.md` (필수)
- **목적**: RED→GREEN 재현 증거
- **내용**:
  - 대표 케이스 2~3개 선택
  - Preconditions, Expected Outcome, Implementation 위치
  - Verification Command
  - TDD 방식 확인

### 5) Phase별 추가 파일 (선택)
- `file_tree.txt` (Phase 0/1): Repo Map 정렬 증거
- `emergency_thresholds_verification.txt` (Phase 1): Policy 임계값 일치 검증
- `entry_gates_verification.txt` (Phase 2): Entry gate 순서/로직 검증
- `stop_update_debounce_proof.txt` (Phase 4): Stop update policy 동작 증거

---

## DoD (Definition of Done) with Evidence

### CLAUDE.md Section 1.2 개정 (Evidence Artifacts 추가)

**기존 DoD**:
1. 관련 테스트 최소 1개 이상 존재
2. 테스트가 구현 전 실패했고(RED) 구현 후 통과했음(GREEN)
3. 코드가 Flow/Policy와 충돌하지 않음 (Gate 1~8)
4. CLAUDE.md Section 5.7 Self-Verification 통과

**추가 (신규 DoD 5번)**:
5. **Evidence Artifact 생성 필수** (새 세션 검증 가능하도록)
   - `docs/evidence/phase_N/completion_checklist.md`
   - `docs/evidence/phase_N/gate7_verification.txt`
   - `docs/evidence/phase_N/pytest_output.txt`
   - `docs/evidence/phase_N/red_green_proof.md`
   - 위 파일들을 git commit 완료 후 Progress Table에 링크 추가

---

## Phase 완료 프로토콜 (Completion Protocol)

### Step 1: Evidence 파일 생성
```bash
# Phase N 완료 시
mkdir -p docs/evidence/phase_N

# Gate 7 검증 출력 저장
grep -RInE "assert[[:space:]]+True" tests/ > docs/evidence/phase_N/gate7_verification.txt
# ... (7개 커맨드 출력 모두 저장)

# pytest 결과 저장
pytest -q > docs/evidence/phase_N/pytest_output.txt 2>&1

# (Phase별 추가 파일 생성)

# completion_checklist.md 작성 (템플릿 참고)
# red_green_proof.md 작성 (대표 케이스 2~3개)
```

### Step 2: 자동 검증 스크립트 실행
```bash
./scripts/verify_phase_completion.sh N
# → ✅ PASS 확인
```

### Step 3: git commit
```bash
git add docs/evidence/phase_N/
git commit -m "docs(evidence): Add Phase N completion artifacts"
```

### Step 4: task_plan.md 업데이트
- Progress Table에 Evidence 링크 추가:
  ```markdown
  | N | ✅ DONE | **Evidence**: [Completion](docs/evidence/phase_N/completion_checklist.md), [Gate7](docs/evidence/phase_N/gate7_verification.txt) | ... | Commit: [해시] |
  ```
- Last Updated 갱신

### Step 5: DONE 보고
- Evidence 파일 경로 포함
- 검증 스크립트 PASS 결과 포함

---

## 새 세션 시작 시 검증 방법 (Verification for New Sessions)

### 방법 1: 빠른 확인 (5초)
```bash
cat docs/evidence/phase_N/gate7_verification.txt | grep -E "FAIL|ERROR"
# → 출력 비어있으면 PASS
```

### 방법 2: 자동 검증 스크립트 (30초)
```bash
./scripts/verify_phase_completion.sh N
# → ✅ PASS: Phase N verification complete
```

### 방법 3: 수동 재검증 (2분)
```bash
# 1) Evidence 파일 존재 확인
ls -la docs/evidence/phase_N/

# 2) Gate 7 재실행
grep -RInE "assert[[:space:]]+True" tests/ | wc -l
# → 0

# 3) pytest 재실행
pytest -q
# → N passed (≥ Evidence 기록된 개수)

# 4) Migration 확인 (Phase 1+)
grep -RInE "from application\.services" tests/ src/ | wc -l
# → 0
```

---

## DONE 무효 조건 (Automatic Invalidation)

아래 조건 중 하나라도 충족되면 **DONE 자동 무효** (Progress Table [x]가 있어도 무시):

1. **Evidence 파일 없음**:
   - `docs/evidence/phase_N/completion_checklist.md` 없음
   - `docs/evidence/phase_N/gate7_verification.txt` 없음

2. **검증 스크립트 FAIL**:
   ```bash
   ./scripts/verify_phase_completion.sh N
   # → ❌ FAIL 출력
   ```

3. **Gate 7 검증 FAIL**:
   ```bash
   cat docs/evidence/phase_N/gate7_verification.txt | grep -E "FAIL|ERROR"
   # → 출력 있음 (에러 발견)
   ```

4. **pytest 개수 감소**:
   - Evidence에 "83 passed" 기록
   - 현재 pytest 실행 시 "75 passed" (감소)
   - → 테스트가 삭제되었거나 실패함

---

## 컨텍스트 단절 대비 (Context Recovery)

### 문제: "phase0을 통과했는데 새 대화마다 계속 실패라고 하는" 현상

**Before (Evidence 없음)**:
- Progress Table에 "DONE" 체크박스만 있음
- 새 세션: "증거가 없으니 FAIL" 판정
- 작업자: "이미 했는데 왜 또 하냐"

**After (Evidence 시스템)**:
- Evidence 파일이 git에 존재
- 새 세션: `./scripts/verify_phase_completion.sh 0` → ✅ PASS
- 작업자: 재작업 불필요

### 효과
- **5분 투자** (Evidence 수집) → **영구적 컨텍스트 복구 능력**
- **새 세션 시작 시 30초** 안에 "DONE 여부" 판단 가능
- **"Trust but Verify" → "Verify from Immutable Artifacts"**

---

## 템플릿 (Templates)

### completion_checklist.md 템플릿
```markdown
# Phase N Completion Checklist

## Metadata
- Phase: N
- Completed Date: YYYY-MM-DD HH:MM (KST)
- Git Commit: [해시]
- Status: ✅ DONE

## DoD Verification
### 1) 관련 테스트 존재
- [x] tests/oracles/... (N cases)
- [x] tests/unit/... (M cases)

### 2) RED→GREEN 증거
- Evidence File: red_green_proof.md
- Sample Case: test_example_name

### 3) Gate 7 Verification
- Evidence File: gate7_verification.txt
- Result: ALL PASS

### 4) Repo Map Alignment
- Evidence File: file_tree.txt (Phase별 선택)

### 5) Evidence Artifacts
- [x] gate7_verification.txt
- [x] pytest_output.txt
- [x] red_green_proof.md
- [x] completion_checklist.md

## Verification Command
\`\`\`bash
./scripts/verify_phase_completion.sh N
\`\`\`

## Sign-off
Phase N은 위 DoD를 모두 충족했으며, Evidence artifacts가 git에 commit되었으므로, 새 세션에서도 검증 가능한 상태임을 확인합니다.
```

---

## 관련 문서 (Related Documents)

- **SSOT (Single Source of Truth)**:
  - [CLAUDE.md](../CLAUDE.md) Section 1.2 (DoD)
  - [CLAUDE.md](../CLAUDE.md) Section 5.7 (Self-Verification)
  - [task_plan.md](../plans/task_plan.md) Section 3 (Progress Tracking Rules)

- **검증 스크립트**:
  - [scripts/verify_phase_completion.sh](../../scripts/verify_phase_completion.sh)

- **Example (Phase 0)**:
  - [phase_0/completion_checklist.md](phase_0/completion_checklist.md)
  - [phase_0/gate7_verification.txt](phase_0/gate7_verification.txt)
  - [phase_0/pytest_output.txt](phase_0/pytest_output.txt)
  - [phase_0/red_green_proof.md](phase_0/red_green_proof.md)

---

## 원칙 재확인 (Core Principles)

1. **Immutable**: Evidence 파일은 생성 후 수정 금지 (새 버전은 별도 파일로)
2. **Verifiable**: 새 세션에서 스크립트 1개로 PASS/FAIL 판단 가능
3. **Traceable**: Git history에 Phase 완료 시점이 명확히 기록됨
4. **Self-Contained**: Evidence 디렉토리만 있으면 검증 가능 (외부 의존성 최소)

---

**"Progress Table 체크박스가 아니라, Evidence 파일이 DONE의 증거다."**
