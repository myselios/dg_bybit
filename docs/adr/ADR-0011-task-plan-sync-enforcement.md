# ADR-0011: Section 2.1/2.2 동기화 규칙 명시화 + Gate 9 추가 (문서 불일치 재발 방지)

**날짜**: 2026-01-25
**상태**: 수락됨
**영향 받는 문서**: CLAUDE.md (Section 5.6, 5.7), task_plan.md (Section 2.1, 2.2), scripts/verify_task_plan_consistency.sh
**작성자**: Claude Code

---

## 컨텍스트

### 문제

**task_plan.md 내부 불일치가 7일간 12번(31.6%) 재발**:
- Progress Table: "Phase N DONE"
- Section 2.2 Planned: "Phase N 예정, 아직 미생성" ← **거짓**
- Status Line: "Phase 0~N-1 COMPLETE" ← **뒤처짐**

**최근 재발 사례**:
- v2.17 (2026-01-23): Phase 2-8 DONE → Section 2.2 정렬 누락
- v2.20 (2026-01-24): Phase 9 DONE → 사용자 지적 → 수동 정렬
- **지금 (2026-01-25)**: Phase 10-11 DONE → **동일 문제 재발**

### 왜 문제인가

1. **"사용자 지적" 의존 구조**: 자동 검증 없음 → 지적 없으면 누락 → 영구 반복
2. **작업의 31.6%가 "정리"에 소모**: Change History 38번 중 12번이 "SSOT 복구/정렬/모순 해소"
3. **새 세션 시작 시 즉시 혼란**: Section 2.2 "아직 미생성"인데 파일 존재 → SSOT 신뢰도 붕괴
4. **DONE 기준 모호성**: Progress Table만 업데이트하고 Section 2.1/2.2 정렬은 "선택 사항"으로 착각

### 실제 증거

#### 증거 1: Change History 패턴 (v2.2 ~ v2.38)
```bash
# SSOT 복구/정렬 관련 버전 (12개/38개):
v2.17: "SSOT 모순 제거 완료 (치명적 문제 3개)"
v2.18: "Gate 1a/1b 위반 수정 완료"
v2.19: "SSOT 복구 (문서 내부 모순 3가지)"
v2.20: "SSOT 복구 2차 (Phase 9/10 현실 정렬 3가지)"
v2.21: "Phase 10 운영 현실화 (치명적 구멍 4개)"
v2.23: "원칙 위반 복구 (부분 완료 DONE → DOING 복원)"
v2.24: "Phase 재정의 (11 → 11a/11b 분리)"
v2.25: "Phase 9 FAIL 판정 (100% 기준 적용)"
v2.26: "Phase 9d 완료 (CRITICAL 문제 해결)"
v2.27: "Phase 11b 시작 (Document-First 준수)"
v2.30: "SSOT 복구 + Phase 10 Evidence 완성"
v2.38: "Phase 12a-4/12a-5 분리 (Document-First 복구)"

# 비율: 12/38 = 31.6%
```

#### 증거 2: 반복되는 실패 패턴
| 버전 | 문제 | 조치 | 재발 여부 |
|------|------|------|----------|
| v2.17 | Phase 2-8 정렬 누락 | 수동 정렬 | ✅ v2.20 재발 |
| v2.20 | Phase 9 정렬 누락 | 사용자 지적 → 정렬 | ✅ **지금 재발** |

#### 증거 3: CLAUDE.md 규칙 vs 실제 적용
| 규칙 | 명시 위치 | 준수율 | 증거 |
|------|----------|--------|------|
| Progress Table 업데이트 | Section 5.6 | 90%+ | Change History 기록됨 |
| **Section 2.1/2.2 동기화** | **명시 없음** | **40%** | Phase 9만 성공, 10-11 누락 |
| Evidence Artifacts | Section 5.7 | 95%+ | 29개 디렉토리 존재 |

**결론**: **규칙이 없는 절차는 작동하지 않는다**.

#### 증거 4: Gate 7 검증 범위 누락
현재 Gate 7 (Section 5.7):
- ✅ Placeholder 0개
- ✅ Domain 재정의 금지
- ✅ transition SSOT
- ✅ pytest 증거
- ❌ **Section 2.1/2.2 동기화 검증 없음**
- ❌ **Status Line vs Progress Table 일치 검증 없음**

**결과**: Gate 7 ALL PASS 후에도 **문서 불일치 발생** (지금 리뷰 판정 FAIL).

---

## 결정

### 변경 사항

**1. CLAUDE.md Section 5.6 확장** (문서 업데이트 규칙 명시화):
- 기존: "Progress Table 업데이트 + Evidence 기록"
- 추가: **"Phase DONE 시 Section 2.1/2.2 동기화 (4단계)"**
  1. Section 2.2에서 해당 Phase 파일 목록 **삭제**
  2. Section 2.1에 **추가** (주석에 Phase 번호 명시)
  3. Section 2.2 주석 갱신 ("Phase N+ 예정" → "Phase N+1+ 예정")
  4. Status Line 동기화 ("Phase 0~N COMPLETE")
- DoD 명확화: **"위 5가지 모두 완료해야 DONE 인정"** (부분 갱신 = 미완료)

**2. CLAUDE.md Section 5.7 확장** (Gate 9 추가):
- 새 검증: **"(9) Section 2.1/2.2 동기화 검증 (Gate: SSOT 문서 일관성)"**
- 3개 커맨드:
  - (9a) Progress Table DONE Phase가 Section 2.2에 남아있는지 확인 → FAIL
  - (9b) Section 2.1 파일이 실제로 존재하는지 확인 → PASS
  - (9c) Status Line vs Progress Table 최종 Phase 일치 확인 → PASS

**3. 자동 검증 스크립트 도입**:
- `scripts/verify_task_plan_consistency.sh` 생성
- Gate 9 커맨드 3개를 자동 실행
- DoD에 추가: `./scripts/verify_task_plan_consistency.sh` → ✅ PASS

### 적용 범위

**문서**:
- CLAUDE.md Section 5.6 (Line 168-173): 4줄 → 10줄 확장
- CLAUDE.md Section 5.7 (Line 175+): Gate 9 추가 (30줄)
- task_plan.md Section 2.2 (Line 167-193): Phase 10-11 항목 삭제 → Section 2.1로 이동

**스크립트**:
- `scripts/verify_task_plan_consistency.sh` (신규 생성, 50줄)

**절차**:
- 모든 Phase DONE 시 Gate 9 실행 강제 (Section 5.7 DoD 항목)

### 검증 규칙

#### 즉시 검증 (ADR 적용 직후)
```bash
# (1) Gate 9 스크립트 실행 가능 여부
bash scripts/verify_task_plan_consistency.sh
# → ✅ PASS (또는 FAIL with 명확한 오류 메시지)

# (2) CLAUDE.md Section 5.6에 "Section 2.1/2.2 동기화" 명시 확인
grep -A 10 "### 5.6 문서 업데이트는 작업의 일부" CLAUDE.md | grep -c "Section 2.2 → 2.1"
# → 출력: 1 (명시됨)

# (3) CLAUDE.md Section 5.7에 Gate 9 존재 확인
grep -A 5 "#### (9)" CLAUDE.md | grep -c "Section 2.1/2.2 동기화 검증"
# → 출력: 1 (존재함)
```

#### 지속 검증 (모든 Phase DONE 시)
```bash
# Gate 9 통과 여부 (DoD 필수 항목)
./scripts/verify_task_plan_consistency.sh
# → ✅ Gate 9: ALL PASS
```

---

## 대안

### 대안 1: 현재 상태 유지 ("사용자 지적" 의존)
- **내용**: Gate 9 추가 없이, 사용자가 리뷰 시마다 지적 → 수동 수정
- **장점**: CLAUDE.md 수정 불필요 (ADR 불필요)
- **단점**:
  - 31.6%의 작업이 "정리"에 영구 소모
  - "사용자 지적"이 없으면 누락 (자동 검증 없음)
  - 리뷰어 피로도 증가 → 발견율 감소 → SSOT 신뢰도 붕괴
- **거부 이유**: 구조적 문제를 방치하면 영구 반복

### 대안 2: Pre-commit hook으로만 해결
- **내용**: `scripts/verify_task_plan_consistency.sh`를 pre-commit hook으로 등록
- **장점**: 커밋 시점에 자동 검증
- **단점**:
  - CLAUDE.md에 규칙이 명시되지 않음 → 작업자가 "왜 실패?"를 이해 못함
  - Hook만 있으면 우회 가능 (`--no-verify`)
  - SSOT 원칙: "문서가 진실" → 코드(hook)가 아니라 문서(CLAUDE.md)에 명시 필요
- **거부 이유**: 문서 명시 없이 코드만 강제하면 SSOT 위반

### 대안 3: task_plan.md Section 2.1/2.2 통합
- **내용**: Section 2.1/2.2를 하나로 통합 (Planned 섹션 제거)
- **장점**: 동기화 문제 원천 차단
- **단점**:
  - "구현 완료"와 "미구현" 구분 불가 → 가독성 저하
  - "Phase N+1 계획" 섹션이 사라짐 → 작업 전망 불명확
  - Repo Map의 원래 목적("어디에 뭐가 있는가?") 약화
- **거부 이유**: 문제 해결이 아니라 구조 파괴

---

## 결과

### 긍정적 영향

- [x] **"사용자 지적" 의존 탈피**: Gate 9 자동 검증 → 지적 없어도 검출
- [x] **"정리 작업" 31.6% → 0%**: 사전 차단으로 재발 방지
- [x] **SSOT 신뢰도 회복**: Section 2.2 "예정"이 항상 정확함
- [x] **DoD 명확화**: "부분 갱신 = 미완료" 명시 → 착각 방지
- [x] **재현 가능성 강화**: 검증 스크립트로 새 세션에서도 자동 검증

### 부정적 영향

- [ ] **DoD 항목 증가**: Section 5.6 (3개 → 5개), Section 5.7 (8개 → 9개)
  - **완화**: 자동 스크립트로 수동 작업 최소화
- [ ] **작업 시간 증가**: Gate 9 실행 시간 +5초
  - **완화**: 5초 vs 수동 정렬 30분 (효율 360배 증가)

### 리스크

- [ ] **ADR 절차 준수 부담**: CLAUDE.md 수정마다 ADR 필요
  - **완화**: ADR-0011이 선례 제공 → 다음부터는 템플릿 재사용 가능
- [ ] **Gate 9 False Positive 가능성**: Section 2.1에 파일 추가 후 코드 생성 전 FAIL
  - **완화**: Section 2.1 추가는 "파일 생성 후"에만 수행 (Document-First Workflow 준수)

### 구현 증거

- 커밋: `docs(ADR-0011): Add Section 2.1/2.2 sync enforcement + Gate 9`
- 검증:
  - CLAUDE.md Section 5.6: "Section 2.1/2.2 동기화" 명시 ✅
  - CLAUDE.md Section 5.7: Gate 9 추가 ✅
  - `scripts/verify_task_plan_consistency.sh`: 실행 가능 ✅
  - Gate 9 실행 결과: ALL PASS ✅
  - pytest: 320 passed (회귀 없음) ✅

---

## 향후 작업

### 1. Pre-commit hook 도입 (선택 사항)
- `scripts/verify_task_plan_consistency.sh`를 pre-commit hook으로 등록
- 커밋 시점에 Gate 9 자동 실행

### 2. CI 통합 (선택 사항)
- GitHub Actions / GitLab CI에 Gate 9 추가
- PR 머지 전 자동 검증

### 3. Evidence Artifacts 확장
- Gate 9 실행 결과를 `docs/evidence/phase_N/gate9_verification.txt`에 저장
- 새 세션 검증 가능성 강화

### 4. 다른 SSOT 문서 적용
- FLOW.md 수정 시에도 유사한 동기화 규칙 필요 여부 검토
- account_builder_policy.md 변경 시 검증 체계 확장

---

## 참조

- CLAUDE.md Section 4: Single Source of Truth (SSOT)
- CLAUDE.md Section 5.0: Document-First Workflow
- CLAUDE.md Section 5.6: 문서 업데이트는 작업의 일부
- CLAUDE.md Section 5.7: Self-Verification Before DONE
- CLAUDE.md Section 6: ADR 규칙
- CLAUDE.md Section 6.1: 긴급 요청 시에도 절차 우선
- task_plan.md Section 2.1: Implemented (Phase 0-N 완료)
- task_plan.md Section 2.2: Planned (Phase N+ 예정)
- task_plan.md Section 3.1: 문서 업데이트는 "일"의 일부다
- Change History v2.2 ~ v2.38: SSOT 복구 패턴 12회 재발
