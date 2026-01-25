#!/bin/bash
# scripts/verify_task_plan_consistency.sh
# Gate 9: task_plan.md 문서 일관성 자동 검증
#
# 목적: Section 2.1/2.2 동기화 + Status Line 일치 확인
# 근거: ADR-0011, CLAUDE.md Section 5.7 Gate 9
#
# 사용법:
#   ./scripts/verify_task_plan_consistency.sh
#   → ✅ Gate 9: ALL PASS (또는 FAIL with 명확한 오류)

set -e

TASK_PLAN="docs/plans/task_plan.md"

echo "=== Gate 9: Task Plan Consistency Check ==="
echo ""

# (1) DONE Phase가 Section 2.2에 남아있는지 확인
echo "[Gate 9a] DONE Phase in Section 2.2 Planned (should be 0)"
done_phases=$(grep "^| [0-9]" "$TASK_PLAN" | grep -E "DONE|\[x\]" | awk '{print $2}')
fail_count=0

for phase in $done_phases; do
  if sed -n '/### 2.2 Planned/,/^##/p' "$TASK_PLAN" | grep -q "Phase $phase"; then
    echo "  ❌ FAIL: Phase $phase is DONE but still in Section 2.2 Planned"
    fail_count=$((fail_count + 1))
  fi
done

if [ $fail_count -eq 0 ]; then
  echo "  ✅ PASS: All DONE phases removed from Section 2.2"
else
  echo "  ❌ FAIL: $fail_count DONE phases found in Section 2.2 Planned"
  echo ""
  echo "  → 조치: Section 5.6 절차 참조 (Phase DONE 시 Section 2.2 → 2.1 이동)"
  exit 1
fi

echo ""

# (2) Section 2.1 파일 존재 확인
echo "[Gate 9b] Section 2.1 files exist in repo"
section21_files=$(sed -n '/### 2.1 Implemented/,/### 2.2 Planned/p' "$TASK_PLAN" | grep -oE "[a-z_]+\.py" | sort -u)
missing_count=0

for f in $section21_files; do
  if ! find src tests -name "$f" 2>/dev/null | grep -q .; then
    echo "  ❌ FAIL: $f in Section 2.1 but not in repo"
    missing_count=$((missing_count + 1))
  fi
done

if [ $missing_count -eq 0 ]; then
  echo "  ✅ PASS: All Section 2.1 files exist in repo"
else
  echo "  ❌ FAIL: $missing_count files in Section 2.1 but not in repo"
  echo ""
  echo "  → 조치: Section 2.1에서 누락된 파일 제거 또는 파일 생성"
  exit 1
fi

echo ""

# (3) Status Line vs Progress Table 일치
echo "[Gate 9c] Status Line vs Progress Table match"

# Status Line에서 "Phase 0~12a-3 COMPLETE" 또는 "Phase 12a-3 COMPLETE" 형식 추출
status_phase=$(head -5 "$TASK_PLAN" | grep "Status:" | grep -oE "Phase [0-9~a-]+-*[0-9]*[a-z]*-*[0-9]* COMPLETE" | tail -1 | sed 's/.*Phase //' | sed 's/ COMPLETE//')

# Progress Table Implementation Phases 섹션에서만 마지막 DONE Phase 추출
table_phase=$(sed -n '/^### Implementation Phases/,/^##/p' "$TASK_PLAN" | grep "^| [0-9]" | grep -E "DONE|\[x\]" | tail -1 | awk '{print $2}')

# 빈 문자열 처리
if [ -z "$status_phase" ]; then
  status_phase="(not found)"
fi
if [ -z "$table_phase" ]; then
  table_phase="(not found)"
fi

# "0~12a-3" 형식에서 마지막 Phase만 추출 (비교용)
status_last=$(echo "$status_phase" | grep -oE "[0-9]+[a-z]*-[0-9]+$" || echo "$status_phase")

if [ "$status_last" == "$table_phase" ]; then
  echo "  ✅ PASS: Status Line ($status_phase) matches Progress Table ($table_phase)"
elif [ "$status_phase" == "(not found)" ] || [ "$table_phase" == "(not found)" ]; then
  echo "  ⚠️  WARN: Cannot verify (Status: $status_phase, Table: $table_phase)"
  echo "           Skipping Gate 9c check"
else
  echo "  ❌ FAIL: Status Line last phase ($status_last) vs Progress Table ($table_phase) mismatch"
  echo "           Full Status Line: $status_phase"
  echo ""
  echo "  → 조치: Status Line을 'Phase 0~$table_phase COMPLETE'로 수정"
  exit 1
fi

echo ""
echo "=== Gate 9: ALL PASS ==="
echo ""
echo "문서 일관성 검증 완료. DONE 보고 가능."
