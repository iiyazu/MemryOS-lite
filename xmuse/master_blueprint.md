# Hermes Master Blueprint

Master is the only active controller after activation. Legacy root-loop files are audit history.

## Dynamic Feature Control

Master owns feature-lane lifecycle decisions. It may create, split, combine,
rename, re-scope, reorder, hold, resume, archive, or request bounded repair for
feature lanes when the decision is recorded as Master-owned evidence.

Dynamic changes must be append-only and auditable under
`xmuse/master/amendments/`. Every amendment must preserve v3 default,
v1 fallback, kernel opt-in, diagnostic-only benchmark semantics, and
`no_gate_lowering`.

Slave Gods may refine a feature-local blueprint or propose a feature amendment,
but only Master may apply registry-level changes in `master_state.json`.

## Rework Loop

Master may repeatedly send a feature back to its Slave God when review, ACK, or
integration evidence shows concrete engineering blockers. Feature-local
failures use active repair states such as `repairing`, `reworking`,
`feature_blocked`, or `active_repair`; they are not Master-level `blocked`
unless the blocker crosses Slave authority.

Slave God owns autonomous repair inside its assigned branch/worktree until it
produces usable ACK and PASS review, proposes re-scope, or identifies an
external/Master-level blocker. Rework cannot use benchmark score targets or
pass-rate targets. Eval output is diagnostic evidence only.

## Autonomous Yolo Runner Policy

Master, Slave, plan, execute, and review nodes run through
`xmuse/codex_node_launcher.sh` or an equivalent:

```text
codex exec --yolo -c approval_policy=never
```

The loop must not wait for human confirmation for routine planning, execution,
review, repair, rework, ACK, or status/report decisions. Human-confirmation
steps from workflow skills become written Master/Slave artifacts.

This does not bypass external merge approval, destructive out-of-scope cleanup,
unrelated user-work deletion, or gate-lowering decisions.
