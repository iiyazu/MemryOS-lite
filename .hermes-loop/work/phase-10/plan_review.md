# phase: phase-10

# Phase 10 Plan Self Review

Context bundle: `.hermes-loop/work/phase-10/context_bundle.md`.

Read-order confirmation: `.hermes-loop/work/phase-10/context_bundle.md` was read first, then `.hermes-loop/work/phase-10/god_dispatch.json`, then `.hermes-loop/work/phase-10/spec.md`, then `.hermes-loop/work/phase-10/plan.md`.

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Verdict: PASS

## Review Findings

- No blocking findings. The spec targets the repeated LoCoMo recall/session-localization failure class identified by the context bundle and Phase 9 evidence, rather than answer projection, scoring, or kernel behavior. References: `.hermes-loop/work/phase-10/context_bundle.md:29-34`, `.hermes-loop/work/phase-9/failure_taxonomy.md:28-34`, `.hermes-loop/work/phase-10/spec.md:17-29`.
- The plan uses RED before production changes. It adds focused failing tests for session-diverse recall selection, packet metadata propagation, and public/v3 diagnostic visibility before modifying searcher, pipeline, composer, engine, or public diagnostics. It also requires recording the exact RED failure. References: `.hermes-loop/work/phase-10/plan.md:29-184`, `.hermes-loop/work/phase-10/spec.md:100-108`.
- The plan avoids case-id, expected-answer, expected-source, and scoring hacks. The spec explicitly forbids branching on failed case ids, expected source ids, expected answer strings, and known LoCoMo lexical terms; the plan's review checklist repeats those constraints before ACK. References: `.hermes-loop/work/phase-10/spec.md:91-98`, `.hermes-loop/work/phase-10/plan.md:419-430`.
- The plan preserves v1 fallback, v3 default, and kernel opt-in. The spec keeps v1 fallback and kernel defaults out of scope; the plan includes targeted guards for explicit v1 fallback, kernel trace default-off behavior, and settings defaulting to v3 with kernel off. Current code also defaults `memoryos_memory_arch` to `v3` and `memoryos_agent_kernel` to `off`. References: `.hermes-loop/work/phase-10/spec.md:43-49`, `.hermes-loop/work/phase-10/plan.md:403-417`, `src/memoryos_lite/config.py:29-31`, `tests/test_context_composer.py:28-32`.
- The plan reaches the real v3/public benchmark path, not demo-only. It requires packet metadata through `RecallPipeline`, v3 `ContextComposer`, `MemoryOSService._context_package_from_v3`, and public benchmark reports, then verifies deterministic LoCoMo public eval and full-chain LongMemEval/LoCoMo 30 gates with `MEMORYOS_MEMORY_ARCH=v3`. References: `.hermes-loop/work/phase-10/spec.md:17-23`, `.hermes-loop/work/phase-10/plan.md:241-262`, `.hermes-loop/work/phase-10/plan.md:307-379`, `src/memoryos_lite/engine.py:1981-1992`, `src/memoryos_lite/engine.py:2189-2235`.
- The plan protects case-level regression visibility. It requires phase-local artifacts listing fail-to-pass, pass-to-fail, unchanged-fail, retrieval movement, planned/selected/rendered movement, failure-class movement, packet/session movement, and cause/disposition for every pass-to-fail. This aligns with the anti-demo gate and prior memory that LoCoMo should not be promoted by aggregate-only movement. References: `.hermes-loop/work/phase-10/context_bundle.md:115-122`, `.hermes-loop/work/phase-10/plan.md:329-349`, `.hermes-loop/work/phase-10/plan.md:375-385`, `.hermes-loop/work/phase-9/result.md:101-105`.
- The plan keeps retrieval/source metrics separate from judged answer quality. The spec preserves `source_hit` semantics as final projection source overlap and requires diagnostics to expose retrieval, selection, rendering, answer, or diagnostic gaps separately; the plan checks `source_hit_semantics` and case-matrix separation. References: `.hermes-loop/work/phase-10/spec.md:77-89`, `.hermes-loop/work/phase-10/plan.md:148-158`, `.hermes-loop/work/phase-10/plan.md:423-429`.

## Required Checks

- RED before production changes: YES. The plan requires focused RED tests and an initial focused RED run before implementation.
- Avoids case-id/expected-answer/expected-source hacks: YES. The spec and plan prohibit those mechanisms; execution review must still inspect the final diff for violations.
- Preserves v1 fallback: YES. It forbids v1 fallback changes and includes an explicit v1 fallback guard.
- Preserves v3 default: YES. It keeps default v3 and adds a settings default guard.
- Preserves kernel opt-in: YES. It keeps `MEMORYOS_AGENT_KERNEL=v1` opt-in and checks default-off kernel traces.
- Reaches real v3/public benchmark path: YES. It requires v3 composer/service conversion, public report visibility, deterministic public eval, and full-chain 30-case public gates when provider access is available.
- Benchmark overfitting risk: LOW if execute follows the plan. The test examples use LoCoMo-like session markers, but the accepted behavior is session-metadata diversification and packet provenance, not case-id or answer-string promotion.

## Required Fixes

None before execution. Execution review must verify the implemented diff continues to satisfy the anti-overfitting and fallback/default constraints, especially that no retrieval behavior branches on `conv-26`, `qa_*`, expected source ids, expected answers, or known failed-case lexical terms.
