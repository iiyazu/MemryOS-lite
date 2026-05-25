#!/bin/bash
# Bootstrap quality gate — runs after each codex exec dispatch
# Usage: bootstrap_gate.sh <worktree_path>
set -euo pipefail

WORKTREE="${1:-.}"
FAILURES=0

echo "=== Bootstrap Gate: $WORKTREE ==="

# 1. pytest (fast, fail-fast)
if ! uv run pytest tests/ -x -q --timeout=120 2>&1 | tail -5; then
    echo "GATE FAIL: pytest"
    FAILURES=$((FAILURES + 1))
fi

# 2. ruff check
if ! uv run ruff check src/ xmuse/ 2>&1 | tail -5; then
    echo "GATE FAIL: ruff"
    FAILURES=$((FAILURES + 1))
fi

# 3. diff sanity (no more than 1000 lines changed)
DIFF_LINES=$(git -C "$WORKTREE" diff --stat HEAD~1 2>/dev/null | tail -1 | grep -oP '\d+ insertion' | grep -oP '\d+' || echo "0")
if [ "$DIFF_LINES" -gt 1000 ]; then
    echo "GATE FAIL: diff too large ($DIFF_LINES insertions)"
    FAILURES=$((FAILURES + 1))
fi

if [ "$FAILURES" -gt 0 ]; then
    echo "GATE RESULT: FAILED ($FAILURES checks)"
    exit 1
fi

echo "GATE RESULT: PASSED"
exit 0
