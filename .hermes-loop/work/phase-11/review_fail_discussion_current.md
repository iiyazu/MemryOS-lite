# phase: phase-11

# Review Fail Discussion - Phase 11

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-11/context_bundle.md`.

Decision recommendation: `repeat_phase`.

## Findings

- Do not ACK or advance Phase 11.
- Do not pause the whole effort.
- Repeat a narrow Phase 11 after fixing the exact refusal on evidence-backed answers.

## Review Blockers

- LongMemEval `58ef2f1c` is a real pass-to-fail: Phase 10 was `pass`, Phase 11 is `fail`, `failure_boundary=citation_drop`, and the answer is the exact no-evidence refusal even though the expected source is in answer evidence.
- LongMemEval `51a45a95` remains an unchanged evidence-hit-answer-fail.
- LoCoMo `conv-26_qa_028` is a real pass-to-fail: Phase 10 was `pass`, Phase 11 is `fail`, `failure_boundary=citation_drop`, and the answer is the exact no-evidence refusal even though the expected sources are in answer evidence.
- LoCoMo `conv-26_qa_003` is a fail-to-pass by judge verdict, but it is not source-grounded because `source_hit=false`.
- LoCoMo `conv-26_qa_015` remains a judge-pass unsupported-answer citation-drop risk.
- The remaining LoCoMo failures stay visible: `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`, `conv-26_qa_027`.

## Smallest Next Action

Fix the refusal-on-relevant-evidence behavior in `PublicAnswerer` with focused RED tests first. Then rerun the focused public benchmark tests and the parallel 30-case gate.
