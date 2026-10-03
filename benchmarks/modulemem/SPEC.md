# ModuleMem dataset spec (for authors)

ModuleMem evaluates memory for a long-lived **module owner** agent in a multi-agent coding
project: after the owner's session is compacted or restarted, a bounded "resume pack" must
bring back the module's current contracts, decisions still in force, and lessons learned
from review objections and failing gates. Each file `modules/mmNN.json` is one module's
activity stream.

## File format

```json
{
  "module_id": "auth",
  "project": "orbit",
  "language": "en",
  "title": "orbit auth module",
  "participants": [
    {"id": "human", "kind": "human", "name": "Priya"},
    {"id": "owner", "kind": "agent", "name": "Auth owner"},
    {"id": "reviewer", "kind": "agent", "name": "Reviewer"},
    {"id": "gate", "kind": "infra", "name": "CI gate"}
  ],
  "activities": [
    {"id": "a01", "type": "message", "speaker": "human", "text": "..."},
    {"id": "a02", "type": "contract_revision", "speaker": "human", "contract_id": "auth-api",
     "contract_version": 1, "text": "auth-api v1: POST /login returns {token, expires_in} ..."},
    {"id": "a07", "type": "gate_failure", "speaker": "gate", "gate_id": "pytest",
     "text": "<realistic multi-line CI log>"},
    {"id": "a09", "type": "review_objection", "speaker": "reviewer", "text": "..."}
  ],
  "gold": {
    "contracts": [{"contract_id": "auth-api", "version": 2, "activity_id": "a15"}],
    "decisions": [
      {"id": "d1", "topic_key": "auth.token_store", "statement": "...",
       "sources": [{"activity_id": "a04", "quote": "<exact substring of a04 text>"}],
       "superseded_by": "d2"}
    ],
    "lessons": [
      {"id": "l1", "topic_key": "auth.refresh_lock", "statement": "...",
       "sources": [{"activity_id": "a07", "quote": "..."}, {"activity_id": "a21", "quote": "..."}],
       "occurrences": 2}
    ]
  },
  "noise": [{"activity_id": "a03", "type": "chitchat", "note": "why it is not memory"}],
  "probes": [
    {"id": "p1", "question": "What does POST /login return in the current contract?",
     "answer_ids": ["contract:auth-api"], "must_contain": ["refresh_token"],
     "must_not_contain": ["expires_in only"]}
  ]
}
```

## Rules (a validator enforces them)

- Activity ids are `a01`, `a02`, ... in order; 30 to 50 activities per module.
- `type` is one of `message`, `review_objection`, `gate_failure`, `contract_revision`.
  - `contract_revision` needs `contract_id` and an integer `contract_version` that increases
    per contract. Its text is the full contract revision (an API or interface spec,
    5 to 20 lines).
  - `gate_failure` speaker is the `infra` participant; text is a realistic CI log of 15 to
    60 lines (pytest, tsc, eslint, mypy, go test or cargo output) with the actual error
    line inside the noise of the log.
  - `review_objection` comes from an agent other than the owner and states a concrete
    problem in the owner's change.
- Every gold `quote` is an exact substring of the cited activity text, at least 8
  characters long.
- Every gold **lesson** cites only `review_objection` or `gate_failure` activities. At least
  one lesson has `occurrences >= 2`: the same mistake fails again later (a different gate
  run or a review), and the lesson cites both. `occurrences` equals the number of distinct
  cited activities.
- At least one decision is superseded (`superseded_by` points to a later decision with the
  same `topic_key`); at least one contract has two or more versions, and `gold.contracts`
  lists only the **current** version of each contract.
- Traps (required, at least 3 per module): later activities that mention an old value or an
  old contract version in a non-current way ("v1 clients still send expires_in, ignore
  them", "we used to store tokens in Redis"), and a rejected proposal to go back.
- Noise (at least 6 entries): chit-chat, status updates, plan steps, questions,
  hypotheticals, rejected proposals, restatements.
- Probes: 6 to 10 per module, each answerable from the current gold only. `answer_ids`
  reference gold ids (`d2`, `l1`) or `contract:<contract_id>`. Use `must_not_contain` for
  every probe whose answer replaced an older value. At least 2 probes ask about lessons
  ("What must you do before ... ?", "Which mistake failed CI twice?").
- Realism: the module is a slice of a small web product (API service, frontend page,
  worker, data pipeline, CLI); owners write like engineers; logs look like real tool output.
- Language: `en` unless the brief says `zh` (then human and agent text is Chinese; logs stay
  in their tool's language).
