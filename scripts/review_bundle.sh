#!/usr/bin/env bash
set -euo pipefail

# 레포 루트 강제 체크
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  echo "ERROR: not a git repo" >&2
  exit 2
fi
cd "$ROOT"

OUT="${1:-review_bundle.md}"

echo "# REVIEW BUNDLE" > "$OUT"
echo "" >> "$OUT"
echo "PWD: $(pwd)" >> "$OUT"
echo "Git root: $ROOT" >> "$OUT"
echo "" >> "$OUT"
echo "Generated: $(date)" >> "$OUT"
echo "" >> "$OUT"

echo "## Repo status" >> "$OUT"
echo "\`\`\`" >> "$OUT"
git status -sb >> "$OUT" 2>&1 || true
echo "\`\`\`" >> "$OUT"
echo "" >> "$OUT"

echo "## SSOT 1: docs/constitution/FLOW.md (head)" >> "$OUT"
echo "\`\`\`" >> "$OUT"
sed -n '1,200p' docs/constitution/FLOW.md >> "$OUT" 2>&1 || echo "MISSING: docs/constitution/FLOW.md" >> "$OUT"
echo "\`\`\`" >> "$OUT"
echo "" >> "$OUT"

echo "## SSOT 2: plans/task_plan.md (head)" >> "$OUT"
echo "\`\`\`" >> "$OUT"
sed -n '1,200p' plans/task_plan.md >> "$OUT" 2>&1 || echo "MISSING: plans/task_plan.md" >> "$OUT"
echo "\`\`\`" >> "$OUT"
echo "" >> "$OUT"

echo "## Reference (optional): docs/specs/account_builder_policy.md (head)" >> "$OUT"
echo "\`\`\`" >> "$OUT"
sed -n '1,200p' docs/specs/account_builder_policy.md >> "$OUT" 2>&1 || echo "MISSING: docs/specs/account_builder_policy.md (optional)" >> "$OUT"
echo "\`\`\`" >> "$OUT"
echo "" >> "$OUT"

echo "## Git diff (staged + unstaged)" >> "$OUT"
echo "\`\`\`diff" >> "$OUT"
git diff >> "$OUT" 2>&1 || true
echo "" >> "$OUT"
git diff --staged >> "$OUT" 2>&1 || true
echo "\`\`\`" >> "$OUT"
echo "" >> "$OUT"

echo "## Tests: pytest --collect-only -q" >> "$OUT"
echo "\`\`\`" >> "$OUT"
pytest --collect-only -q >> "$OUT" 2>&1 || true
echo "\`\`\`" >> "$OUT"
echo "" >> "$OUT"

echo "## Tests: pytest -q" >> "$OUT"
echo "\`\`\`" >> "$OUT"
pytest -q >> "$OUT" 2>&1 || true
echo "\`\`\`" >> "$OUT"
echo "" >> "$OUT"

echo "Wrote $OUT"
