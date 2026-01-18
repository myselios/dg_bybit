#!/bin/bash
# Phase Completion Verification Script
# Usage: ./scripts/verify_phase_completion.sh <phase_number>
# Example: ./scripts/verify_phase_completion.sh 0

set -e

PHASE=$1
EVIDENCE_DIR="docs/evidence/phase_${PHASE}"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Usage check
if [ -z "$PHASE" ]; then
    echo -e "${RED}❌ Error: Phase number required${NC}"
    echo "Usage: $0 <phase_number>"
    echo "Example: $0 0"
    exit 1
fi

echo "=========================================="
echo "🔍 Verifying Phase ${PHASE} completion..."
echo "=========================================="
echo ""

# 1) Evidence 파일 존재 확인
echo "[1/5] Checking evidence files..."
REQUIRED_FILES=(
    "${EVIDENCE_DIR}/completion_checklist.md"
    "${EVIDENCE_DIR}/gate7_verification.txt"
    "${EVIDENCE_DIR}/pytest_output.txt"
    "${EVIDENCE_DIR}/red_green_proof.md"
)

MISSING_FILES=0
for FILE in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$FILE" ]; then
        echo -e "${RED}  ❌ Missing: ${FILE}${NC}"
        MISSING_FILES=$((MISSING_FILES + 1))
    else
        echo -e "${GREEN}  ✅ Found: ${FILE}${NC}"
    fi
done

if [ $MISSING_FILES -gt 0 ]; then
    echo -e "${RED}❌ FAIL: ${MISSING_FILES} evidence file(s) missing${NC}"
    echo "Phase ${PHASE} Evidence Artifacts가 불완전합니다."
    exit 1
fi

# 2) Gate 7 검증 결과 확인
echo ""
echo "[2/5] Checking Gate 7 verification results..."
if grep -qE "FAIL|ERROR" "${EVIDENCE_DIR}/gate7_verification.txt" 2>/dev/null; then
    echo -e "${RED}  ❌ Gate 7 verification has failures${NC}"
    echo "  Details:"
    grep -E "FAIL|ERROR" "${EVIDENCE_DIR}/gate7_verification.txt" | head -5
    echo -e "${RED}❌ FAIL: Gate 7 검증 실패${NC}"
    exit 1
else
    echo -e "${GREEN}  ✅ Gate 7: ALL PASS${NC}"
fi

# 3) pytest 결과 재실행 & 비교
echo ""
echo "[3/5] Running pytest to verify current state..."
if [ ! -f "${EVIDENCE_DIR}/pytest_output.txt" ]; then
    echo -e "${YELLOW}  ⚠️  pytest_output.txt not found, skipping comparison${NC}"
else
    # venv 활성화 및 pytest 실행
    if [ -d "venv/bin" ]; then
        source venv/bin/activate
    fi

    # pytest 실행 (output to temp file)
    pytest -q > /tmp/current_pytest.txt 2>&1 || true

    # Expected count 추출
    EXPECTED_COUNT=$(grep -oP '\d+(?= passed)' "${EVIDENCE_DIR}/pytest_output.txt" 2>/dev/null || echo "0")
    CURRENT_COUNT=$(grep -oP '\d+(?= passed)' /tmp/current_pytest.txt 2>/dev/null || echo "0")

    echo "  Expected: ${EXPECTED_COUNT} passed"
    echo "  Current:  ${CURRENT_COUNT} passed"

    if [ "$CURRENT_COUNT" -lt "$EXPECTED_COUNT" ]; then
        echo -e "${RED}  ❌ pytest count decreased (expected: ${EXPECTED_COUNT}, current: ${CURRENT_COUNT})${NC}"
        echo "  Current pytest output:"
        cat /tmp/current_pytest.txt
        echo -e "${RED}❌ FAIL: 테스트 개수 감소 또는 실패${NC}"
        exit 1
    elif [ "$CURRENT_COUNT" -gt "$EXPECTED_COUNT" ]; then
        echo -e "${YELLOW}  ⚠️  pytest count increased (expected: ${EXPECTED_COUNT}, current: ${CURRENT_COUNT})${NC}"
        echo -e "${YELLOW}  새 테스트가 추가되었습니다. Evidence 업데이트를 고려하세요.${NC}"
    fi

    echo -e "${GREEN}  ✅ pytest: ${CURRENT_COUNT} passed (≥ ${EXPECTED_COUNT})${NC}"
fi

# 4) Placeholder 테스트 재검증
echo ""
echo "[4/5] Re-checking for placeholder tests..."
PLACEHOLDER_COUNT=$(grep -RInE "assert[[:space:]]+True|pytest\.skip\(|pass[[:space:]]*#.*TODO" tests/ 2>/dev/null | grep -v "\.pyc" | wc -l)
if [ "$PLACEHOLDER_COUNT" -gt 0 ]; then
    echo -e "${RED}  ❌ Found ${PLACEHOLDER_COUNT} placeholder test(s)${NC}"
    grep -RInE "assert[[:space:]]+True|pytest\.skip\(|pass[[:space:]]*#.*TODO" tests/ 2>/dev/null | grep -v "\.pyc" | head -5
    echo -e "${RED}❌ FAIL: Placeholder 테스트 발견 (Gate 1 위반)${NC}"
    exit 1
else
    echo -e "${GREEN}  ✅ No placeholder tests found${NC}"
fi

# 5) Migration 완료 확인 (Phase 1+ 필수)
echo ""
echo "[5/5] Checking migration protocol compliance..."
MIGRATION_COUNT=$(grep -RInE "from application\.services|import application\.services" tests/ src/ 2>/dev/null | wc -l)
if [ "$MIGRATION_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}  ⚠️  Found ${MIGRATION_COUNT} old import path(s)${NC}"
    grep -RInE "from application\.services|import application\.services" tests/ src/ 2>/dev/null | head -5

    # Phase 0은 경고만, Phase 1+는 FAIL
    if [ "$PHASE" -ge 1 ]; then
        echo -e "${RED}❌ FAIL: Migration 미완료 (Gate 8 위반)${NC}"
        exit 1
    else
        echo -e "${YELLOW}  Phase 0이므로 경고만 출력합니다.${NC}"
    fi
else
    echo -e "${GREEN}  ✅ Migration complete (no old import paths)${NC}"
fi

# Final summary
echo ""
echo "=========================================="
echo -e "${GREEN}✅ PASS: Phase ${PHASE} verification complete${NC}"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - Evidence files: OK"
echo "  - Gate 7: PASS"
echo "  - pytest: ${CURRENT_COUNT} passed (≥ ${EXPECTED_COUNT})"
echo "  - Placeholder tests: 0"
echo "  - Migration: OK"
echo ""
echo "Phase ${PHASE}는 DoD를 충족하며, 재작업이 필요하지 않습니다."
echo ""

exit 0
