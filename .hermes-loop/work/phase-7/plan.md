# phase: phase-7

# Plan: Benchmark + Evaluation Compatibility

## Task 1: Extend benchmark harness
**File:** `src/memoryos_lite/public_benchmarks.py`

### Step 1: RED — test v3 diagnostics appear
### Step 2: GREEN — add diagnostic fields
### Step 3: Verify v1/v2 still work

## Task 2: Run full eval
```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval ...
```
