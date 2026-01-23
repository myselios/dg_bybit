#!/bin/bash
# scripts/verify_phase_completion.sh
# Phase 완료 검증 스크립트 (Evidence Artifacts 기반)

set -e

PHASE=$1
EVIDENCE_DIR="docs/evidence/phase_${PHASE}"

if [ -z "$PHASE" ]; then
  echo "Usage: $0 <phase_number>"
  echo "Example: $0 7"
  exit 1
fi

echo "=== Phase ${PHASE} Completion Verification ==="
echo "Evidence Directory: $EVIDENCE_DIR"
echo ""

# 1. Evidence 디렉토리 존재 확인
if [ ! -d "$EVIDENCE_DIR" ]; then
  echo "❌ FAIL: Evidence directory missing: $EVIDENCE_DIR"
  exit 1
fi
echo "✅ Evidence directory exists"

# 2. 필수 파일 4개 존재 확인
REQUIRED_FILES=("completion_checklist.md" "gate7_verification.txt" "pytest_output.txt" "red_green_proof.md")
for file in "${REQUIRED_FILES[@]}"; do
  if [ ! -f "$EVIDENCE_DIR/$file" ]; then
    echo "❌ FAIL: Missing evidence file: $file"
    exit 1
  fi
  echo "✅ $file exists"
done

# 3. gate7_verification.txt에서 FAIL/ERROR 검색
echo ""
echo "=== Checking gate7_verification.txt for FAIL/ERROR ==="
if grep -qE "^FAIL:|^ERROR:" "$EVIDENCE_DIR/gate7_verification.txt"; then
  echo "❌ FAIL: gate7_verification.txt contains FAIL/ERROR"
  grep -E "^FAIL:|^ERROR:" "$EVIDENCE_DIR/gate7_verification.txt"
  exit 1
fi
echo "✅ No FAIL/ERROR found in gate7_verification.txt"

# 4. pytest_output.txt에서 "passed" 확인
echo ""
echo "=== Checking pytest_output.txt for passed tests ==="
if ! grep -q "passed" "$EVIDENCE_DIR/pytest_output.txt"; then
  echo "❌ FAIL: pytest_output.txt missing 'passed' keyword"
  exit 1
fi
PASSED_COUNT=$(grep -oE "[0-9]+ passed" "$EVIDENCE_DIR/pytest_output.txt" | head -1 | awk '{print $1}')
echo "✅ Tests passed: $PASSED_COUNT"

# 5. red_green_proof.md에서 RED→GREEN 증거 확인
echo ""
echo "=== Checking red_green_proof.md for RED→GREEN evidence ==="
if ! grep -q "RED" "$EVIDENCE_DIR/red_green_proof.md" || ! grep -q "GREEN" "$EVIDENCE_DIR/red_green_proof.md"; then
  echo "❌ FAIL: red_green_proof.md missing RED or GREEN evidence"
  exit 1
fi
echo "✅ RED→GREEN evidence found"

# 6. completion_checklist.md에서 DoD 완료 확인
echo ""
echo "=== Checking completion_checklist.md for DoD completion ==="
if ! grep -q "DONE 판정" "$EVIDENCE_DIR/completion_checklist.md"; then
  echo "⚠️  WARN: completion_checklist.md missing 'DONE 판정' section"
fi
echo "✅ completion_checklist.md exists"

echo ""
echo "=========================================="
echo "✅ PASS: Phase ${PHASE} completion verified"
echo "=========================================="
echo ""
echo "Next action: Update task_plan.md Progress Table if not already done"
exit 0
