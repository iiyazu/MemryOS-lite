# Modular Gate Profiles Design

Date: 2026-05-26

## Purpose

xmuse currently has two verification paths that are too coarse for the current
state of MemoryOS:

- lane-local quality checks run a lightweight fixed gate.
- full quality gates run one hard-coded pytest command.

The project now has several isolated historical or experimental surfaces:
legacy paging, page/item memory, v1 eval baselines, experimental `agent_graph`,
archive-rag, and gray-area diagnostics. These should not block normal xmuse
iteration for the current product surface.

This design replaces hard-coded full-gate commands with configuration-driven
gate profiles. It also changes the full quality gate interval from 12 completed
normal lanes to 20 completed normal lanes.

## Current Product Surface

The blocking product surface for normal xmuse iteration is:

- `MEMORYOS_MEMORY_ARCH=v3`
- `MEMORYOS_RECALL_PIPELINE=v2`
- `MEMORYOS_PAGING_MODE=off`
- `MEMORYOS_AGENT_KERNEL=off`

The blocking surface covers:

- v3 context composition, contracts, core memory, and current store behavior.
- v2 episode-first recall, query analysis, recall cache, and episode storage.
- current API, middleware, and current CLI smoke paths.
- xmuse core orchestration: master loop, lane status, quality gate, rework,
  auto-discovery, session manager, launchers, registry, routing, and callback
  server.

The blocking surface excludes:

- legacy paging, page/item memory, and context-builder behavior.
- v1 eval baseline behavior.
- item retrieval and item tools.
- old retrieval/RAG pipeline tests that operate on `MemoryPage`.
- experimental `agent_graph` and demo agent tests.
- archive-rag, archive service, archive vector/searcher, and archive CLI tests.
- opt-in agent kernel tests.
- gray-area diagnostics: budget, conflict, evidence, observability, and patch
  edge-case tests.

Excluded surfaces can still run under a nonblocking historical profile.

## Gate Profiles

The first version defines these profiles:

- `strict-product`: periodic full gate and default unknown-diff fallback.
- `memoryos-core`: config, schema, store, engine current path, v3 composer, and
  core memory.
- `memoryos-recall`: episode storage/search, query analysis, v2 recall pipeline,
  recall cache, and query expansion.
- `memoryos-api`: FastAPI, middleware, and current CLI entry points.
- `xmuse-core`: master loop, full-gate logic, lane status, quality gate, rework,
  auto-discovery, agent consumer/session/registry/launchers/routing/callbacks.
- `xmuse-ui`: dashboard API and frontend lanes.
- `memoryos-kernel`: opt-in kernel tests. This profile is blocking only when a
  lane explicitly targets kernel work; it is not part of `strict-product`.
- `historical`: legacy, experimental, and gray-area tests. This profile is
  nonblocking and never creates automatic repair lanes.

## Configuration File

Gate profiles live in `xmuse/gate_profiles.json`.

The file is schema-versioned and strongly validated. Unknown fields fail closed.
Profiles may not contain free-form shell strings. Commands must reference a
catalog entry and provide structured arguments.

Example shape:

```json
{
  "schema_version": 1,
  "defaults": {
    "full_gate_profile": "strict-product",
    "full_gate_interval": 20,
    "unknown_diff_policy": "strict-product",
    "unclassified_test_policy": "fail"
  },
  "command_catalog": {
    "pytest": {
      "argv": ["uv", "run", "pytest"],
      "cwd": ".",
      "timeout_s": 0,
      "allow_extra_args": true
    },
    "ruff": {
      "argv": ["uv", "run", "ruff", "check"],
      "cwd": ".",
      "timeout_s": 0,
      "allow_extra_args": true
    }
  },
  "profiles": {
    "strict-product": {
      "description": "Current enabled MemoryOS and xmuse product surface.",
      "blocking": true,
      "env": {
        "MEMORYOS_MEMORY_ARCH": "v3",
        "MEMORYOS_RECALL_PIPELINE": "v2",
        "MEMORYOS_PAGING_MODE": "off",
        "MEMORYOS_AGENT_KERNEL": "off"
      },
      "commands": [
        {
          "command": "pytest",
          "args": ["-q", "tests/test_v3_path.py"]
        }
      ],
      "diff_selectors": [
        "src/memoryos_lite/config.py",
        "src/memoryos_lite/store.py",
        "src/memoryos_lite/engine.py",
        "src/memoryos_lite/retrieval/**",
        "xmuse/**",
        "src/xmuse_core/**"
      ]
    }
  }
}
```

This JSON is an abbreviated shape example. The production
`strict-product` profile is invalid unless it includes the current-product
manifest described in the test selection rules.

`timeout_s=0` means no timeout. This preserves the user's requirement that long
lane verification must not be killed by a fixed timeout.

Command catalog entries are not shell snippets. `argv` and profile `args` are
lists of argv parts. `cwd` must resolve inside the repository. Unknown command
fields fail validation. A profile may add `args` only when the catalog entry has
`allow_extra_args=true`.

## Test Selection Rules

Profiles may use:

- whole test files when the file belongs to one surface;
- pytest nodeids when a test file mixes current and historical surfaces;
- pytest markers later, after the test suite is marked intentionally;
- a small `-k` expression only as a migration tool.

`strict-product` must not rely on a large ignore list. It must explicitly name
the current product tests it runs. The first implementation must include a
manifest of file and nodeid ownership for each profile.

Mixed files need nodeid selection or test splitting before they can be safely
included. Examples:

- `tests/test_engine.py` mixes v3/current tests with explicit v1 and context
  builder tests.
- `tests/test_context_composer.py` mixes v3 composer tests with kernel,
  archival, and vector concerns.
- `tests/test_v3_contracts.py` mixes core contracts with legacy adapter and
  kernel trace tests.
- `tests/test_api.py` currently uses a shared service fixture and may need a
  current-product fixture before it enters `strict-product`.

Declared mixed files need nodeid ownership. The coverage guard fails if a mixed
file has tests that are not assigned to exactly one profile by nodeid or marker.
Whole-file ownership is allowed only for files declared as single-surface files.

The first `strict-product` config must not be a placeholder. It must include a
manifest for at least these current-product areas:

- whole-file or nodeid coverage for `tests/test_v3_path.py`;
- core memory service/store tests that do not depend on page/item legacy paths;
- episode store, episode retrieval, recall pipeline, recall cache, and query
  expansion tests;
- current-product API and middleware tests that run under the current-product
  environment;
- xmuse core tests for master loop, quality gate, rework, auto-discovery,
  consumer/session/registry/launchers/routing/callback server, MCP server, and
  overnight runner.

Files known to be mixed (`test_engine.py`, `test_context_composer.py`,
`test_v3_contracts.py`, and `test_api.py`) must be represented with nodeids,
markers, or a documented split-before-include step.

## Current-Product Environment

Blocking profiles for current product behavior must set the current-product
environment explicitly:

```text
MEMORYOS_MEMORY_ARCH=v3
MEMORYOS_RECALL_PIPELINE=v2
MEMORYOS_PAGING_MODE=off
MEMORYOS_AGENT_KERNEL=off
```

This avoids accidentally running strict-product under legacy defaults from
global pytest fixtures or developer shell state.

The gate runner overlays profile `env` over the process environment. The
profile value wins over the caller shell, pytest fixture defaults, and inherited
agent environment for the command process.

## Resolution Rules

Lane JSON may include:

- `gate_profile`: one profile id.
- `gate_profiles`: multiple profile ids.

`gate_profiles` wins over `gate_profile` if both are present.

`load_lanes()` must preserve gate metadata by extending `TaskDescriptor` with:

- `gate_profile: str | None`;
- `gate_profiles: list[str]`;
- `lane_metadata: dict[str, Any]`;
- `base_head_sha: str | None`.

Unknown lane fields that are relevant to gates are retained in `lane_metadata`.
Full-gate lanes use the same metadata path as normal lanes.

Changed paths are computed from a defined base:

- lane-local gates compare the lane worktree branch against the root repository
  `HEAD` that the worktree was created from. The implementation stores this as
  `base_head_sha` in lane metadata when the worktree is created.
- full-gate lanes use the completed lane batch metadata and root `HEAD` recorded
  when the full-gate lane is created. They do not infer product scope from the
  repair worktree.
- if `base_head_sha` is missing for an old lane, the resolver uses the current
  worktree merge-base with the root branch and records
  `legacy_diff_base_inferred` in the report.

Resolution order:

1. If explicit profile metadata exists, start with that profile set.
2. If no explicit profile metadata exists, infer profiles from changed file
   paths using each profile's `diff_selectors`.
3. If no selector matches, use the configured `unknown_diff_policy`.
4. If explicit profiles were provided, validate that the explicit profile set
   covers every changed path whose selector maps to a blocking profile.
5. If a changed path maps to a blocking profile that is missing from the
   explicit profile set, fail closed with a blocking `profile_mismatch` gate
   report. This applies to under-scoped blocking profiles as well as
   nonblocking `historical`.

When multiple profiles match, the resolver runs the union of all matching
profiles. It does not choose a single highest-priority profile. Duplicate
commands are deduplicated only when command id, args, cwd, and env are
identical.

The resolver records why each profile was selected:

- `explicit_lane_profile`
- `diff_selector`
- `unknown_diff_policy`
- `profile_mismatch`
- `legacy_diff_base_inferred`

## Execution Model

The implementation uses three units:

- `GateProfileLoader`: loads and validates `xmuse/gate_profiles.json`.
- `GateProfileResolver`: resolves lane metadata and changed paths into a
  `GatePlan`.
- `GateRunner`: executes a `GatePlan` and returns a `GateReport`.

`GateReport` contains:

- selected profiles and resolution reasons;
- command argv, cwd, env overlay, exit code, stdout/stderr artifact path;
- blocking and nonblocking result summaries;
- profile mismatch details, if any.

Reports are written under `xmuse/logs/gates/<feature_id>/`. The latest report
path is also written back to the lane as `gate_report`. Nonblocking failures are
recorded in `gate_warnings` and are visible to dashboard/status readers, but
they do not change terminal lane status.

## Lane-Local Gate Flow

After a normal lane finishes its agent work, xmuse runs a lane-local gate through
the resolver and runner.

- Blocking failures enter the existing rework loop.
- Nonblocking failures are recorded as artifacts and reports, but they do not
  mark the lane failed and do not trigger automatic repair.
- Profile mismatch is a blocking failure.

The existing diff sanity and ruff checks can become commands in `xmuse-core` or
shared preflight commands instead of remaining hard-coded behavior.

## Full Quality Gate Flow

After 20 successful normal lanes, xmuse appends one full quality gate lane.

The full gate lane contains:

```json
{
  "task_type": "full_quality_gate",
  "gate_profiles": ["strict-product"]
}
```

The full gate uses the same resolver and runner. On blocking failure, it keeps
the existing behavior:

- write a full-gate artifact;
- mark the full gate failed;
- create one repair lane for the failed gate;
- preserve the existing single-flight full-gate-family behavior.

Historical nonblocking failures do not create repair lanes.

Existing full gate lanes with old batch metadata remain valid. New batch
creation uses the configured interval of 20 lanes. If the config is missing or
invalid, startup fails closed rather than silently falling back to an old
interval.

## Historical Gate Flow

The `historical` profile is explicitly nonblocking. It can run when:

- a lane explicitly requests it;
- a diff selector matches isolated historical paths;
- an operator starts it manually.

Historical failures create reports and dashboard-visible warnings. They do not
change a lane from done to failed and do not create repair lanes.

## Coverage Guard

Because explicit test lists can miss new tests, the gate system needs a coverage
guard test:

- enumerate `tests/test*.py`;
- verify each file is covered by at least one profile, or explicitly listed as
  historical/nonblocking;
- fail if a new test file is unclassified.

This guard checks profile ownership, not whether every test is blocking.
Single-surface files may be assigned by file path. Mixed files must be assigned
by nodeid or marker. A mixed file with unassigned nodeids fails the guard unless
the file is explicitly marked for later splitting and assigned to `historical`
as nonblocking.

## Error Handling

The system fails closed for:

- invalid `gate_profiles.json`;
- unknown profile ids in lane JSON;
- unknown command ids;
- free-form command strings;
- profile mismatch between explicit profile metadata and changed paths that map
  to missing blocking profiles;
- unclassified changed paths when `unknown_diff_policy` is not configured.

The system records nonblocking reports for:

- historical profile command failures;
- manually requested nonblocking diagnostics.

## Migration Plan Boundary

This design does not require adding pytest markers in the first implementation.
It permits nodeid lists and file lists immediately, then marker migration later.

It also does not require deleting legacy tests. Legacy tests remain available
through `historical` or manual commands; they simply stop blocking ordinary
xmuse lane throughput.

## Verification Scope For Implementation

Implementation should include tests for:

- config loading and schema validation;
- command catalog rejection of free-form shell strings;
- explicit lane profile resolution;
- diff-based fallback profile resolution;
- profile mismatch fail-closed behavior;
- full gate interval of 20 lanes;
- full gate lane generation with `gate_profiles=["strict-product"]`;
- nonblocking historical failures not creating repair lanes;
- profile coverage guard for test files.
