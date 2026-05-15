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

## Public M3 — LoCoMo Actual Message Evidence Remains Zero

### Symptom

In the M3 public benchmark run, LoCoMo `memoryos_lite` has non-zero page
candidate overlap but `msg_source_hit_at_5 = 0.00` and
`msg_session_hit_at_5 = 0.00`. This means page candidates still sometimes
cover the expected source/session, but the actual `context.retrieved_evidence`
path does not load the expected raw message evidence.

### Manual trace

Case traced: `conv-26_qa_001` from `locomo10.json`.

Question:

```
When did Caroline go to the LGBTQ support group?
```

Expected source:

```
conv-26_qa_001:conv-26:D1:3
[1:56 pm on 8 May, 2023] Caroline: I went to a LGBTQ support group yesterday and it was so powerful.
```

Observed diagnostics:

- `page_count = 24` before supersession filtering; `13` active pages remain.
- Active page types: `11 core_profile_page`, `2 source_summary_page`.
- All paged source IDs: `417`; active `source_page_ids`: `230`.
- The expected source is in a superseded page, not in active `source_page_ids`.
- Query/message lexical overlap is not the root problem for the expected
  message: overlap tokens are `{caroline, to, lgbtq, support, group}`.
- Among active paged messages, `216` have positive lexical overlap, but none
  are the expected source because the expected source was removed by
  supersession.
- Before evidence retrieval, the task uses `10` tokens and three pinned core
  pages consume the remaining budget (`used_before_evidence = 90`,
  `remaining_before_evidence = 0`).
- Actual context result: `retrieved_evidence = []`, no loaded retrieved pages,
  and `10` dropped pages.

### Why it happens

There are two interacting causes:

1. Page supersession can remove the page that contains the expected LoCoMo
   evidence from the active `source_page_ids` map. Since raw evidence retrieval
   intentionally only considers active paged sources, the expected message is
   no longer a candidate.
2. The heuristic pager still labels many LoCoMo windows as `core_profile_page`.
   Core pages are pinned before raw evidence retrieval, so the 90-token eval
   budget can be exhausted before any evidence snippet is considered.

### Current status

M3 improves page granularity and reduces the single giant-page pathology, but
it does not solve LoCoMo actual evidence retrieval. This is an accepted
negative/mixed result for M3 and should be used as the next benchmark target.

### Future fix direction

- Make core-profile pinning conditional or budget-capped for public benchmark
  style multi-session dialogues.
- Revisit supersession for benchmark pages: a superseded page may still contain
  valid historical evidence and should perhaps remain eligible for raw evidence
  retrieval even if it is skipped for page summary retrieval.
- Add a diagnostic counter separating "expected source not paged", "expected
  source superseded", "positive lexical overlap but not top-k", and "candidate
  found but budget dropped".


## Ticket #5 — eval source_accuracy 混合两条证据路径，不等于 evidence-first RAG 验证

### Symptom

_run_baseline 的 memoryos_lite 路径同时使用：
- context.retrieved_evidence（真实 context path，受 budget 约束）
- _page_evidence(page, ...)（从 store 直接加载 page.facts，绕过 budget）

当前 source_accuracy 是两条路径叠加的结果。

### 指标区分

- page_source_overlap_at_5：page 覆盖 expected source session（page 粒度）
- msg_source_hit_at_5：evidence 定位到具体 message（evidence 粒度）
- 当前 source_accuracy：page-fact 展开 + retrieved_evidence 叠加，不能单独作为 evidence-first RAG 的验收指标

### 当前状态

已接受限制。M3 的验收目标是 LoCoMo dropped_relevant_page_count 下降，不是修这个指标混合问题。

### 未来修正方向

将 eval 的 source attribution 统一到 context.retrieved_evidence.message_id，去掉 page-fact 展开路径，使指标与实际 context 路径一一对应。

## Ticket #6 — LoCoMo msg_source_hit_at_5 = 0.0 根因分支诊断

### Symptom

M3 public benchmark LoCoMo memoryos_lite 的 msg_source_hit_at_5 = 0.0，msg_session_hit_at_5 = 0.0。_retrieve_message_evidence 在 LoCoMo 场景下没有命中任何 expected source message。

### 诊断范围

手动追踪 frozen M3 first-50 LoCoMo 口径（`locomo10.json` 的 `conv-26`
前 50 个 QA）。为避免重复建页开销，诊断复用同一份 paged `conv-26`
会话，并将各 QA 的 case-specific source id 映射到同一会话的 message id。
该步骤只用于根因分类，不是新的 benchmark 结果。

### 分支占比

50 个 traced case 都没有 actual `context.retrieved_evidence` 命中 expected
source。其中 47 个 case 带 expected source id，3 个 QA 没有 evidence id，
不纳入三条失败分支的比例。

- Branch 1：expected source 在被 supersede 的 page 里，不在 active
  `source_page_ids`：`40/47 = 85.1%`。
- Branch 2：expected source 在 active page 里但 BM25 lexical overlap 为
  0：`0/47 = 0.0%`。first-50 中没有观察到这个分支。
- Branch 3：expected source 已进入 top-5 evidence candidates，但 core
  page pinning 后预算不足，未进入 actual `retrieved_evidence`：`4/47 =
  8.5%`。
- Additional observed branch：expected source 在 active page 中且 lexical
  overlap > 0，但被其他 message 排到 top-5 之外：`3/47 = 6.4%`。这不在
  原三分支内，但应作为 M4 ranking 验收项单独跟踪。

### Manual trace samples

- Branch 1 sample：`conv-26_qa_001`，question 为 “When did Caroline go to
  the LGBTQ support group?”。Expected source `D1:3` 在 all paged sources 中，
  但不在 active `source_page_ids`；query/message overlap 为 `{caroline, to,
  lgbtq, support, group}`，说明不是 overlap=0 问题。Context 里 3 个 pinned
  core pages 用掉剩余预算，`retrieved_evidence = []`。
- Branch 3 sample：`conv-26_qa_013`，question 为 “How long ago was
  Caroline's 18th birthday?”。Expected source `D4:5` 是 top-1 evidence
  candidate，`message_bm25=12.5073 overlap=4`，snippet 估算 `34` tokens；
  但 task 用 `11` tokens、2 个 pinned core pages 用 `70` tokens，
  `remaining_before_evidence = 9`，因此 candidate 被预算挡掉。
- Additional ranking sample：`conv-26_qa_028`，question 为 “Would Caroline
  pursue writing as a career option?”。Expected sources `D7:5` 和 `D7:9`
  都在 active pages 中且 overlap > 0，但 top-5 candidates 是其他 message，
  所以 actual evidence 仍为空。

### M4 验收基准

M4 paging/ranking 改动至少应分别报告：

- expected source superseded count 是否下降到 `<= 10/47`；
- active expected source overlap=0 是否仍为 0；
- expected source top-5 candidate 但 budget dropped 是否下降；
- active overlap>0 but not top-5 是否下降；
- actual `msg_source_hit_at_5` 是否从 frozen M3 的 `0.0` 改善到
  `>= 0.15`；
- LongMemEval source hit 不低于 M3 的 `0.86 - 0.05`，即 `>= 0.81`。

M3b 的具体方向是 supersession-aware raw evidence retrieval：superseded
pages 仍不参与 page summary retrieval / page-fact attribution，但其
`source_message_ids` 可以作为 raw-message evidence candidates，并通过
`ContextEvidence.superseded` 显式标记，供 scoring 降权和诊断使用。

### M3b 当前结果

已实现并冻结 first-50 public benchmark 诊断：

- LoCoMo `msg_source_hit_at_5 = 0.2083`，超过 `>= 0.15` 下限。
- LoCoMo `superseded_source_recovered = 27`，`25/50` case 至少恢复一条
  superseded-source evidence。
- LongMemEval `source_hit = 0.94`，超过 `>= 0.81` 下限。
- LoCoMo final deterministic `source_hit/session_hit = 0.00/0.00`，说明 M3b
  只改善 actual evidence loading，不解决 answer projection / ranking。

## Ticket #7 — _project_evidence_text 中单字「换」作为 priority_marker 过于宽泛

### Symptom

evals.py 的 _project_evidence_text 中 priority_markers 包含单字「换」，会误匹配「换行」「交换」「兑换」等无关 clause。在 deterministic eval 里不触发，在 public benchmark 真实对话里有误匹配风险。

### 修正方向

将「换」替换为「换成」「换用」，并补充一个测试 case 覆盖误匹配场景。

### 当前状态

已修复。`priority_markers` 不再包含单字「换」，测试覆盖 `换行`、`交换`、`兑换` 不应触发错误 projection。

## Ticket #8 — _is_generic_ack 在 engine.py 和 evals.py 重复定义

### Symptom

engine.py:335 和 evals.py:921 各有一份逻辑相同的 _is_generic_ack，独立维护，未来可能不同步。

### 修正方向

提取到共享位置（schemas.py 或独立 utils 模块），两处改为导入。

### 当前状态

已修复。共享判断位于 `memoryos_lite.utils.is_generic_ack`，engine/evals 均导入该函数。
