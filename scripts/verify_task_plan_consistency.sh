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
status_phase=$(head -5 "$TASK_PLAN" | grep "Status:" | grep -oE "Phase [0-9a-]+-*[0-9]*[a-z]*-*[0-9]* COMPLETE" | tail -1 | sed 's/ COMPLETE//')
table_phase=$(grep "^| [0-9]" "$TASK_PLAN" | grep -E "DONE|\[x\]" | tail -1 | awk '{print $2}')

if [ "$status_phase" == "$table_phase" ]; then
  echo "  ✅ PASS: Status Line ($status_phase) matches Progress Table ($table_phase)"
elif [ -z "$status_phase" ]; then
  echo "  ⚠️  WARN: Status Line has no 'Phase N COMPLETE' (acceptable for initial phases)"
  echo "           Table last DONE: $table_phase"
else
  echo "  ❌ FAIL: Status Line ($status_phase) vs Progress Table ($table_phase) mismatch"
  echo ""
  echo "  → 조치: Status Line을 'Phase 0~$table_phase COMPLETE'로 수정"
  exit 1
fi

echo ""
echo "=== Gate 9: ALL PASS ==="
echo ""
echo "문서 일관성 검증 완료. DONE 보고 가능."
