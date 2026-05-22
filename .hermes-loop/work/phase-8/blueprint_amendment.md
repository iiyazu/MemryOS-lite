# phase: phase-8

active_goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

original_hypothesis:
MemoryOS Lite v3 could move from the Letta-style usability blueprint into broader eval if 50-case LongMemEval and LoCoMo evidence stayed stable, source-grounded, and free of same-subset regressions.

triggering_evidence:
LongMemEval 50-case full-chain LLM judge reached `47/50`, but LoCoMo reached only `30/50`. Same-subset movement showed no pass-to-fail cases, but LoCoMo still had twelve unchanged failures and eight new failures. Failure clusters split into retrieval/session localization misses and evidence-hit-answer-fail cases.

case_examples:
LongMemEval retrieval misses: `b86304ba`, `ccb36322`.
LongMemEval evidence-hit-answer-fail: `51a45a95`.
LoCoMo retrieval misses: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, `conv-26_qa_035`, `conv-26_qa_036`, `conv-26_qa_039`, `conv-26_qa_044`, `conv-26_qa_050`.
LoCoMo evidence-hit-answer-fail: `conv-26_qa_006`, `conv-26_qa_012`, `conv-26_qa_016`, `conv-26_qa_024`, `conv-26_qa_027`, `conv-26_qa_033`, `conv-26_qa_041`, `conv-26_qa_048`.

decision:
Do not expand eval or promote the blueprint from aggregate score. Continue with a targeted LoCoMo reliability loop.

phases_advanced:
None.

phases_delayed:
Broader eval expansion and any production-style promotion language.

phases_added_or_removed:
Add a next targeted loop around LoCoMo session/temporal retrieval, context selection for expected-source sessions, and answer use of selected evidence. Keep LongMemEval as a regression guard rather than the primary optimization target.

next_verification_command:
Run a fixed LoCoMo failure slice covering `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_012`, `conv-26_qa_033`, `conv-26_qa_041`, `conv-26_qa_048`, and `conv-26_qa_050`, plus a 30-case LongMemEval regression guard, both through `MEMORYOS_MEMORY_ARCH=v3` with LLM answer/judge when provider access is available.

risk:
Optimizing answer projection alone may mask retrieval/session misses. Optimizing retrieval alone may leave evidence-hit-answer-fail unchanged. Future gates must report both categories separately and keep pass-to-fail lists explicit.
