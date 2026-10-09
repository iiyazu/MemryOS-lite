# RoomMem dataset

Purpose: measure a "memory curator" that reads multi-agent chat-room transcripts (a Human plus 2–3 AI agents from different vendors collaborating on a software project) and must store the right long-term memories (facts, decisions, rules, preferences, lessons), merge duplicates, supersede outdated ones, and ignore noise; then answer probe questions from memory.

## Files

| File | Project | Language |
|---|---|---|
| `rooms/rm01.json` – `rooms/rm04.json` | atlas | rm01 zh, rm02 mixed, rm03–rm04 en |
| `rooms/rm05.json` – `rooms/rm08.json` | beacon | rm05 zh, rm06 mixed, rm07–rm08 en |
| `rooms/rm09.json` – `rooms/rm12.json` | cobalt | rm09 zh, rm10 mixed, rm11–rm12 en |
| `validate.py` | stdlib-only validator | |
| `README.md` | this file | |

## Running the harness

```
uv run memoryos eval roommem --data benchmarks/roommem/rooms --arm raw --arm oracle --fake-llm --out /tmp/roommem
```

`--arm raw` replays the xmuse Room host (session + per-message archive outbox);
`--arm oracle` uses the gold memories themselves as the curator upper bound and
is what CI runs; `--arm curated` needs a `CuratedMemorySource` registered via
`memoryos_lite.roommem.register_curated_source` and fails with a clear message
otherwise. Reports land in `--out` as `results.jsonl`, `write_side.json`,
`summary.json`, and `summary.md`. Use `--repeats N` for run-to-run spread (LLM responses
are disk-cached per repeat under `--out/llm_cache`).

## Schema (JSON, UTF-8, 2-space indent)

```
{
  "room_id": "rm01",
  "title": "short title",
  "language": "en" | "zh" | "mixed",
  "project": "atlas" | "beacon" | "cobalt",
  "participants": [{"id": "human", "kind": "human", "name": "Mira"},
                   {"id": "lead", "kind": "agent", "name": "Product Lead", "vendor": "claude"}, ...],
  "messages": [{"id": "m01", "speaker": "human", "text": "..."}],
  "gold_memories": [
    {"id": "g1", "kind": "fact|decision|rule|preference|lesson",
     "scope": "room|project|user",
     "topic_key": "dotted.lowercase.key",
     "statement": "one self-contained sentence",
     "sources": [{"message_id": "m03", "quote": "EXACT verbatim substring of that message's text"}],
     "superseded_by": null}
  ],
  "noise": [{"message_id": "m05", "type": "rejected_proposal|hypothetical|question|chitchat|agent_instruction|restatement|tentative|plan_step",
             "note": "why this must NOT become a new memory"}],
  "probes": [
    {"id": "p1", "question": "...", "asked_in": "same_room|new_room_same_project",
     "answer_memory_ids": ["g7"], "must_contain": ["..."], "must_not_contain": ["..."]}
  ]
}
```

Scope rules: `rule` → project, `preference` → user (the human's), `fact`/`decision`/`lesson` → room. The same human (Mira) appears in every room of a project; the agent lineup varies (2–3 agents, vendors claude / antigravity / opencode).

## Validation

```
python3 validate.py rooms/rm01.json ...   # explicit files
python3 validate.py                       # no args: all rooms/*.json next to the script
```

`validate.py` enforces: sequential message ids `m01..`, speakers are participant ids, 30–60 messages; 6–12 gold memories, ≥ 6 noise entries, 7–10 probes; exact-substring quotes on existing messages; `superseded_by` points to a gold memory of the same `topic_key` whose earliest source comes later; probe answers exist and are not superseded; `new_room_same_project` probes reference only project/user-scope memories; kind–scope consistency; non-empty `must_contain`; `must_not_contain` lists the stale value when an answer memory supersedes another memory. It prints per-room counts plus coverage totals and exits 1 on any error.

## Room contents

| Room | Theme |
|---|---|
| rm01 | atlas 存储选型与工程规范 |
| rm02 | atlas 认证模块定稿 |
| rm03 | atlas 发布流水线 |
| rm04 | atlas 性能优化 |
| rm05 | beacon 推送服务架构 |
| rm06 | beacon 数据管道 |
| rm07 | beacon incident postmortem |
| rm08 | beacon feature flag rollout |
| rm09 | cobalt 数据导出服务 |
| rm10 | cobalt 告警体系 |
| rm11 | cobalt 权限模型 |
| rm12 | cobalt 配额服务 |

## Coverage matrix (spec items 1–10 × rooms)

| # | Coverage item | rm01 | rm02 | rm03 | rm04 | rm05 | rm06 | rm07 | rm08 | rm09 | rm10 | rm11 | rm12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Decision/fact later changed by a different speaker (supersession; `must_not_contain` old value) | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | Same fact restated 2–3× (ONE gold with multiple sources; later restatements are noise) | – | ✓ | – | ✓ | – | ✓ | – | – | – | – | ✓ | ✓ |
| 3 | Proposal explicitly rejected (noise `rejected_proposal`) | ✓ | ✓ | ✓ | – | ✓ | ✓ | – | ✓ | – | – | ✓ | ✓ |
| 4 | Hypothetical "what if we used X" (noise `hypothetical`) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ | ✓ |
| 5 | Human instruction wrapper (only the rule inside is gold; message also noise `agent_instruction`) | ✓ | – | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 6 | Lesson learned from a failure | – | ✓ | – | ✓ | – | ✓ | ✓ | – | ✓ | ✓ | ✓ | ✓ |
| 7 | Project rule recallable from a different room (`new_room_same_project` probe) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 8 | User preference of the human | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 9 | Numeric/time facts (wrong number = wrong answer) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 10 | Tentative statement later confirmed (tentative = noise, confirmed = gold) | ✓ | – | – | ✓ | – | ✓ | ✓ | – | ✓ | – | – | ✓ |

Selected examples:

- Item 1: rm01 SQLite→Postgres (p1 `must_not_contain` "SQLite"); rm03 blue-green→canary; rm07 human-stated 200 req/s corrected by the verifier's log evidence to 100 req/s; rm08 project rule changed from "flags in the admin console" to "flags in the config repo"; rm09 a three-step chain on one `topic_key` (1000→5000→2000 rows); rm11 30→15 min sessions; rm12 starter quota 10k→5k.
- Item 2: rm02 JWT (m04+m11 as sources, m18/m30 as restatement noise); rm04 300ms p95 target; rm06 30-day retention; rm11 explicit tenant filter; rm12 600 rpm default.
- Item 5: rule supersessions in rm08 also pass through a wrapper message that is itself listed as `agent_instruction` noise.
- Item 10: rm07 tentative "about 100 minutes" superseded by the verified 82-minute window.

## Totals

`python3 validate.py` across all 12 rooms: **0 errors**.

| Metric | Total | Spec target |
|---|---|---|
| Rooms | 12 | 12 |
| Messages | 396 | 30–60 per room |
| Gold memories | 97 (11 superseded, 28 multi-source) | 6–12 per room |
| Noise entries | 89 | ≥ 6 per room |
| Probes | 96 | 90–110 overall |
| `new_room_same_project` probes | 24 | ≥ 20 overall |

Per-room counts (messages / gold / noise / probes):

| rm01 | rm02 | rm03 | rm04 | rm05 | rm06 | rm07 | rm08 | rm09 | rm10 | rm11 | rm12 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 34/7/8/8 | 33/8/6/8 | 33/8/7/8 | 33/8/7/8 | 33/7/8/8 | 33/8/8/8 | 33/9/7/8 | 33/7/6/8 | 33/9/7/8 | 33/8/7/8 | 32/10/10/8 | 33/8/8/8 |

## Limitations

- **LLM-authored**: all transcripts, memories, and probes were generated by a language model, not collected from real teams; phrasing may be more regular than natural chat.
- **Single annotator**: gold memories and noise labels come from one annotation pass; a second annotator would likely disagree on borderline items (e.g., whether a small process step deserves a memory).
- **Gold may miss legitimate memories**: the transcripts contain more true statements than the annotated `gold_memories`; unlabeled statements are not necessarily noise, and a curator storing them is not always wrong.
- **English/Chinese mix**: rm01/rm05/rm09 are Chinese, rm02/rm06/rm10 mixed Chinese/English, the rest English; evaluation should not assume a single working language.
- **Probe checks are keyword-based**: `must_contain`/`must_not_contain` are minimal sanity constraints, not a full correctness rubric.
- **Fictional content**: no real company or person names; vendors (claude/antigravity/opencode) and service names (NimbusPush/AuroraPush) are used only as context labels.
