# eval collab

Quality of the `collab` profile of `POST /curate`: the alignment curator for
one xmuse 2 topic. Each `c*.json` scenario is one topic: the hub's `active`
entries, a `window` of new messages, and what a good curator does with them.

```bash
# Deterministic pipeline check (runs in CI through tests/test_collab_eval.py)
uv run python -m memoryos_eval collab --fake-llm --repeats 2
# Real provider (key from the environment), 3 repeats, 3 calls at a time
uv run python -m memoryos_eval collab --repeats 3 --workers 3 --out artifacts/collab
```

Output: `summary.md`, `summary.json` and `runs.jsonl` (every response, its
score, and its initial and final violations). `--fake-llm` output has no wall
times and is byte-identical across runs.

## Scenarios

| id | case | expectation |
|---|---|---|
| c01 | Qualified decision ("Decimal only in the payment API; ledger totals stay in cents") | a proposal that keeps all three qualifiers and supersedes the old amount decision |
| c02 | An answer to one of two open questions | `resolves_ids: ["Q1"]`, and Q2 stays open |
| c03 | A review request and a handoff that contradict two conventions | conflicts with both C1 and C2 |
| c04 | Two messages restating declared entries, one new rule | only the new rule is proposed, with its scope ("external APIs only") |
| c05 | Chit-chat and status updates | nothing stored |
| c06 | A `review_objection` | assigned to a lesson (closed-world accounting) |
| c07 | A human overturns a convention mid-task (the hub's rot-2 seed) | a proposal superseding the old decision, keeping its qualifiers |

`expect` keys: `proposals` (`sources`, `qualifiers` as groups of
alternatives, optional `supersedes`), `resolves` and `not_resolved`,
`conflicts` (active ids), `restates` (activity → active id), `chatter`, and
`objections`. The metric definitions are in `memoryos_eval/collab.py`.

## Results (2026-10-10, r7)

Real provider: OpenCode `muse-spark-1.3-contributor` (Responses API), 3
repeats, `max_repairs` 2. Means ± sample standard deviation over repeats.

| metric | fake LLM | real, before the prompt fix | real, c06 after the fix |
|---|---|---|---|
| proposal_recall | 0.75 | 1.00 ± 0 | n/a |
| qualifier_retention | 0.33 | 1.00 ± 0 | n/a |
| resolves precision / recall | n/a / 0.00 | 1.00 / 1.00 ± 0 | n/a |
| conflict_recall | 0.00 | 1.00 ± 0 (6/6) | n/a |
| duplicate_rate | 1.00 | 0.00 ± 0 | n/a |
| chatter_stored_rate | 0.00 | 0.00 ± 0 | n/a |
| objection_lesson_rate | 1.00 | 1.00 ± 0 | 1.00 ± 0 |
| supersedes_accuracy | 0.00 | 1.00 ± 0 | n/a |
| clean_first_reply | 1.00 | 0.857 ± 0 (c06 failed 3/3) | 1.00 ± 0 (3/3) |

The fake LLM echoes one entry per decision, assumption, question, or handoff
message and never resolves or reports conflicts, so its numbers only prove the
pipeline.

Cost per run (real provider, every attempt counted):

| scenario | completion tokens | LLM calls per run | wall s |
|---|---|---|---|
| c01 | 2,573 ± 291 | 1 | 20.4 ± 4.1 |
| c02 | 4,477 ± 1,260 | 1 | 36.7 ± 12.0 |
| c03 | 7,385 ± 2,179 | 1 | 51.9 ± 20.5 |
| c04 | 1,327 ± 127 | 1 | 9.1 ± 1.9 |
| c05 | 1,035 ± 83 | 1 | 6.6 ± 0.8 |
| c06, before the fix | 12,774 ± 853 | 3 | 92.9 ± 1.1 |
| c06, after the fix (`max_repairs` 0) | 3,859 ± 1,640 | 1 | 25.0 ± 11.3 |
| c07 | 1,936 ± 500 | 1 | 13.0 ± 4.3 |

Prompt tokens are about 650-830 per call.

**The prompt fix.** Before it, the collab system prompt did not say how to
account for a review objection. Every c06 run needed two repairs, three calls in
all, before its lesson was defined in `lessons` and assigned. The collab prompt
now spells out the assignment and `lessons` format, as the module prompt does.
After the fix, all 3 runs were valid on the first reply with repairs disabled:
3.3× fewer completion tokens and 3.7× less wall time. The fix was measured on c06
only, because the 30-call budget was spent (21 runs + 6 repairs before, 3 after).
The other scenarios have no failures to account for, so the added rule does not
apply to them, but they were not re-run.

**Limits.** The scenarios are small (2-4 messages), and the real provider
scored 1.0 on every quality metric. They catch regressions, but they do not
separate good curators from great ones. In M2-MO, a busier 8-message window
missed a conflict in 1 of 3 runs. Longer, mixed windows are the next scenarios
to add.
