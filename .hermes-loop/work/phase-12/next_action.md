# phase: phase-12

Phase-11 is preserved as unfinished debt. Do not mark it complete.
Phase-12 is now recovering through `GOD_DISPATCH` after an orphan EXECUTE
guard.

Current carry-forward:

- LongMemEval is clean in the latest gate.
- LoCoMo still has `conv-26_qa_028` as a new `pass_to_fail` regression.
- LoCoMo still has one judged pass with `source_hit=false` and a cluster of retrieval / evidence-hit failures.

Next controller action:

1. Read `.hermes-loop/work/phase-12/context_bundle.md`.
2. Regenerate phase-12 `god_dispatch.json` and `plan_final.md` before any new
   implementation or eval.
3. Execute phase-12 from the archival/RAG unification hypothesis only after the
   dispatch/plan pair exists.
4. Prepare phase-13 as the next planning lane.
5. Do not write `ack.json` for phase-11.
6. Do not overwrite phase-11 artifacts; they remain the record of the latest unfinished gate.
