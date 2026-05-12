# Known Issues

This document tracks known, deliberately-deferred limitations of the
paging / conflict / retrieval pipeline. Each entry records what the
symptom is, why the current behaviour is acceptable, and what a future
fix would look like.

## Ticket #4 — `fact_accumulation` drops mid-stream preferences without a recognised verb

### Symptom

In the `advanced` eval case-set, `fact_accumulation_00{1..4}` each inject
three user preferences:

```
第N次记录偏好1：我喜欢用 Vim 编辑器。
第N次记录偏好2：我偏好暗色主题。
第N次记录偏好3：我习惯用 tmux 管理终端。
```

The expected answer mentions all three (`Vim`, `暗色主题`, `tmux`). The
current heuristic pager surfaces 偏好1 and 偏好3 but drops 偏好2 from
`page.summary`, so the assembled answer is missing the middle
preference.

### Why it happens

`PagingAgent.heuristic_draft` composes `page.summary` from the first
three items of `ranked_facts`, where `ranked_facts` puts
slot-extractable (`subject+verb+value`) facts ahead of filler. With the
eval's `recent_message_limit = 2`, the first five messages are paged and
seven `facts` candidates enter the draft; filler lines ("已记录",
"今天写了很多代码") plus 偏好1 and 偏好2 compete for three slots.

`SlotExtractor` yields a slot for 偏好1 ("我喜欢用 Vim" matches verb
`用`) and for 偏好3 ("我习惯用 tmux" matches `用`), but **not** for
偏好2 — the sentence "我偏好暗色主题" has no verb in the active
allow-list (adding `偏好` as a verb causes false-positive slot parses on
labelled noise like `第N次记录偏好2：…`, which silently shadows
unrelated preferences).

### Why the current behaviour is acceptable

* `tests/` is fully green (142 passed).
* The `hard` eval case-set is at `1.00 / 1.00` — no regression on the
  conflict / recall / supersession suites.
* Naive summary (which has no structured ranking) and vector RAG already
  beat `memoryos_lite` on this specific pattern; the gap is limited to
  4 of 16 advanced cases.
* Every reasonable fix attempted so far regressed some other suite:
  - Adding `偏好` / `习惯` / `喜欢` to `_TRANSITION_VERBS` → false-
    positive slot parses on `第N次记录偏好2：…` shadowed unrelated
    preferences via `_drop_intra_draft_conflicts`.
  - Colon-presence ("contains `：`") as an additional informativeness
    signal → labelled noise (`旧方向：Runbook…`, `第 N 段无关长噪声：…`)
    rode that signal into `page.summary`, leaking forbidden facts and
    bloating the summary enough to push the page below the retrieval
    threshold on `hard_long_recall` / `hard_source_budget`.
  - Widening `facts[:3]` to `facts[:5]` → same forbidden-fact leak on
    `hard_conflict_update`.

### What a proper fix looks like

Two directions, both out of scope for this pass:

1. **Preference-verb white-list that ignores noun-like positions.**
   Teach `SlotExtractor` to require a pronoun or honorific subject
   immediately before verbs like `偏好` / `习惯` / `喜欢`, and to refuse
   the match when the verb is preceded by a digit or the literal string
   `记录` (as in `偏好N：` labelling). This keeps the extraction narrow
   enough that only genuine "`我 偏好 X`" sentences earn a slot.

2. **Importance-weighted summary packing.** Replace the fixed
   `facts[:3]` cap with a budget-aware packer that prefers facts with
   high keyword-overlap against the current session's question
   distribution, still capped by a character budget so noise lines
   cannot dominate.

Either fix should be landed together with a new eval case set that
covers at least:
- labelled-but-stale facts (`旧方向：…`) adjacent to a final decision,
- labelled noise that looks informative but should not enter summary,
- mid-conversation preferences using `偏好` / `习惯` / `喜欢`.
