# ADR-0009: FLOW v1.11 SSOT 중복 제거 (문서 정리 + Stop Loss 통합)

**날짜**: 2026-01-25
**상태**: 제안됨
**영향 받는 문서**: FLOW.md v1.10 → v1.11
**작성자**: System Review (FLOW.md SSOT 검증)

---

## 컨텍스트

FLOW.md v1.10 검토 결과, **2가지 SSOT 원칙 위배**가 발견되었습니다.

### 문제 1: Section 10.2 "Document-First Workflow" 중복 44회
- 현재 상태: Section 10.2가 문서 전체에 44번 반복 삽입됨
- 라인 수: 5401줄 중 ~1800줄(32.6%)이 중복 내용
- 발견 명령어:
  ```bash
  grep -c "### 10.2 Document-First Workflow" docs/constitution/FLOW.md
  # 출력: 44
  ```
- 영향:
  - 문서 가독성 저하 (중복으로 인한 정보 노이즈)
  - 수정 시 44곳을 모두 업데이트해야 하는 유지보수 부담
  - SSOT 원칙 위배 (단일 진실이 44개 사본으로 분산)

### 문제 2: Stop Loss 정의 중복 (Section 2.5 vs 4.5)
- **Section 2.5** "Stop Loss 갱신 규칙":
  - Amend-first 정책 (공백 방지)
  - 20% threshold, 2초 debounce
  - Stop 주문 속성: `reduceOnly=True`, `positionIdx=0`

- **Section 4.5** "Stop Loss 주문 계약":
  - `triggerPrice` 계산 (방향별 분기)
  - `reduceOnly=True`, `positionIdx=0`
  - `stopOrderType="Market"`, `triggerDirection` (Long=2, Short=1)
  - `orderLinkId` 규격 정의

- **충돌**:
  - 두 섹션 모두 Stop Loss 정의를 포함하지만, **관점이 다름**
  - Section 2.5: 갱신 정책 (언제/어떻게 amend)
  - Section 4.5: 주문 계약 (Bybit API 파라미터)
  - 향후 Stop Loss 정의 변경 시 **두 곳을 모두 수정해야 하는 위험**
  - SSOT 원칙 위배 (단일 진실이 2곳에 분산)

### 실거래 위험
1. **유지보수 오류**: Section 2.5와 4.5 중 한 곳만 수정 시 정의 불일치 발생
2. **구현 혼란**: 개발자가 2.5와 4.5 중 어느 것을 따라야 할지 판단 불가
3. **문서 신뢰도 저하**: 중복/충돌로 인한 문서 품질 의심

---

## 결정

FLOW.md v1.11로 업데이트하여 **2가지 SSOT 중복을 모두 제거**합니다.

### 결정 1: Section 10.2 중복 제거
- **조치**: 44개 중 43개 삭제, **마지막 1개만 유지** (Section 10 끝)
- **근거**:
  - Section 10.2는 "작업 절차" 규칙이므로 **1회 선언으로 충분**
  - 각 섹션 끝마다 반복 삽입은 "리마인더" 의도였으나, 유지보수 부담만 증가
  - SSOT 원칙: 단일 진실은 단일 위치에만 존재
- **예상 결과**: 문서 크기 5401줄 → ~3600줄 (1800줄 감소, -32.6%)

### 결정 2: Stop Loss 정의 통합
- **SSOT 지정**: **Section 4.5**를 Stop Loss 정의의 유일한 진실로 지정
- **Section 2.5 처리**:
  - **삭제하지 않음** (갱신 정책은 여전히 필요)
  - **참조 표기 추가**: "Stop Loss 주문 계약은 Section 4.5 참조"
  - **중복 내용 제거**: `reduceOnly`, `positionIdx` 등 4.5와 중복되는 파라미터 정의 삭제
  - **고유 내용만 유지**: Amend-first 정책, 20% threshold, 2s debounce (갱신 로직)

- **Section 4.5 강화**:
  - 현재 내용 유지 (이미 충분히 상세)
  - **SSOT 표기 추가**: "⚠️ SSOT: Stop Loss 주문 계약 (Section 2.5는 갱신 정책만)"

- **근거**:
  - Section 4.5가 더 상세하고 Bybit API와 1:1 매핑됨 (구현 중심)
  - Section 2.5는 "갱신 정책"에 집중, 4.5는 "주문 계약"에 집중 (역할 분리)
  - 향후 Stop Loss 파라미터 변경 시 **Section 4.5만 수정**하면 됨

---

## 대안

### 대안 1: Section 2.5를 SSOT로 지정
- **내용**: Section 4.5 삭제, Section 2.5만 유지
- **장점**: 갱신 정책 중심으로 통합
- **단점**:
  - Section 2.5는 Bybit API 파라미터가 불완전 (triggerDirection, stopOrderType 누락)
  - Section 4.5가 더 상세하고 구현 중심적
- **거부 이유**: Section 4.5가 더 완전한 정의 제공

### 대안 2: 두 섹션 모두 유지 (현재 상태)
- **내용**: 중복 허용, 각 섹션의 "관점 차이"로 정당화
- **장점**: 갱신 정책/주문 계약을 별도 섹션에서 설명
- **단점**:
  - SSOT 원칙 위배
  - 향후 수정 시 2곳을 모두 업데이트해야 함
  - 정의 불일치 위험
- **거부 이유**: SSOT 원칙 준수 필수

### 대안 3: Section 10.2 중복 유지 ("리마인더" 정당화)
- **내용**: 각 섹션 끝마다 Section 10.2 삽입 유지
- **장점**: 작업자에게 Document-First 원칙 강조
- **단점**:
  - 1800줄 중복 (32.6%)
  - 유지보수 부담 (수정 시 44곳 업데이트)
  - 문서 가독성 저하
- **거부 이유**: 비용 대비 효과 낮음 (CLAUDE.md에 이미 명시됨)

---

## 결과

### 긍정적 영향
- [x] **SSOT 원칙 준수** (Stop Loss 정의 단일화)
- [x] **문서 크기 32.6% 감소** (5401줄 → ~3600줄)
- [x] **유지보수 부담 감소** (Section 10.2 수정 시 1곳만 변경)
- [x] **문서 가독성 향상** (중복 제거로 정보 밀도 증가)
- [x] **향후 충돌 방지** (Stop Loss 정의 변경 시 Section 4.5만 수정)

### 부정적 영향 / Trade-off
- [x] **마이그레이션 필요**: 기존 코드가 Section 2.5 참조 시 Section 4.5로 변경 필요
- [ ] **성능 영향 없음** (문서 정리는 런타임 무관)
- [ ] **실거래 로직 변경 없음** (정의 통합일 뿐, 규칙 변경 아님)

### 변경이 필요한 문서
- [x] **FLOW.md Section 10.2**: 43개 삭제, 1개만 유지
- [x] **FLOW.md Section 2.5**: 중복 내용 제거, "Section 4.5 참조" 추가
- [x] **FLOW.md Section 4.5**: "⚠️ SSOT" 표기 추가
- [x] **FLOW.md 버전**: v1.10 → v1.11
- [ ] **코드 영향 없음** (현재 구현은 이미 Section 4.5 기준으로 작성됨)

---

## 실거래 영향 분석

### 리스크 변화
- **청산 리스크**: 불변 (정의 통합일 뿐, 로직 변경 없음)
- **손실 한도**: 불변
- **Emergency 대응**: 불변

### 백워드 호환성
- [x] **기존 포지션 영향 없음** (문서 정리만 수행)
- [x] **기존 설정 영향 없음**
- [x] **기존 로직 영향 없음** (현재 구현은 Section 4.5 기준)

### 롤백 가능성
- [x] **쉽게 롤백 가능** (git revert로 v1.10 복원 가능)
- [ ] **데이터 마이그레이션 불필요**
- [ ] **코드 변경 불필요**

---

## 구현 계획

### Phase 1: Section 10.2 중복 제거
1. Section 10.2 출현 위치 전수 확인:
   ```bash
   grep -n "### 10.2 Document-First Workflow" docs/constitution/FLOW.md
   ```
2. 마지막 1개를 제외한 43개 삭제
3. 검증:
   ```bash
   grep -c "### 10.2 Document-First Workflow" docs/constitution/FLOW.md
   # 기대 출력: 1
   ```

### Phase 2: Stop Loss 정의 통합
1. Section 2.5 수정:
   - `reduceOnly`, `positionIdx` 등 중복 파라미터 제거
   - "⚠️ Stop Loss 주문 계약은 Section 4.5 참조" 추가
   - Amend-first 정책, 20% threshold, 2s debounce만 유지

2. Section 4.5 수정:
   - "⚠️ SSOT: Stop Loss 주문 계약 정의" 추가
   - 기존 내용 유지

3. 검증:
   ```bash
   # Section 2.5에 "Section 4.5 참조" 표기 확인
   grep -A5 "Section 2.5" docs/constitution/FLOW.md | grep "Section 4.5"

   # Section 4.5에 SSOT 표기 확인
   grep -A5 "Section 4.5" docs/constitution/FLOW.md | grep "SSOT"
   ```

### Phase 3: 문서 업데이트
1. FLOW.md 버전: v1.10 → v1.11
2. Change History 업데이트:
   ```markdown
   | v1.11 | 2026-01-25 | SSOT 중복 제거 (Section 10.2 × 43 삭제, Stop Loss 통합) | ADR-0009 |
   ```

### Phase 4: Evidence Artifacts
1. Before/After 비교 파일 생성:
   ```bash
   # Before
   wc -l docs/constitution/FLOW.md > docs/evidence/flow_refactor/before_line_count.txt
   grep -c "### 10.2" docs/constitution/FLOW.md >> docs/evidence/flow_refactor/before_line_count.txt

   # After (수정 후)
   wc -l docs/constitution/FLOW.md > docs/evidence/flow_refactor/after_line_count.txt
   grep -c "### 10.2" docs/constitution/FLOW.md >> docs/evidence/flow_refactor/after_line_count.txt
   ```

2. Diff 생성:
   ```bash
   git diff docs/constitution/FLOW.md > docs/evidence/flow_refactor/flow_v1.10_to_v1.11.diff
   ```

---

## 참고 자료

- CLAUDE.md Section 6: ADR 규칙 (SSOT 문서 수정 시 ADR 필수)
- FLOW.md v1.10: 현재 버전 (5401줄, Section 10.2 × 44회)
- Review 결과: FAIL 판정 (Section 10.2 중복, Stop Loss SSOT 중복)
- SSOT 원칙: docs/constitution/FLOW.md, docs/specs/account_builder_policy.md, docs/plans/task_plan.md

---

## 승인 기준

이 ADR은 아래 조건을 만족해야 수락됩니다:

1. [ ] Section 10.2 중복 제거로 문서 크기 감소 확인 (5401줄 → ~3600줄)
2. [ ] Stop Loss 정의가 Section 4.5에만 존재 확인
3. [ ] Section 2.5에 "Section 4.5 참조" 표기 확인
4. [ ] FLOW.md 버전 v1.11로 업데이트 확인
5. [ ] Evidence Artifacts 생성 (before/after 비교)
6. [ ] Git commit에 "ADR-0009" 표기
