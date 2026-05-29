#!/usr/bin/env python3
"""Re-inject Frontend Vision Layer 1-4 work, AFTER Layer 1 store is already
implemented (the previous chain hit max retries on review-god rework but the
code is verified good — 38 tests pass).

This second-attempt graph SKIPS the store-impl lane and treats the existing
participant_store.py + tests as "already merged". Subsequent lanes
(api-impl, tests, worklist, dashboard layer 3/4, acceptance) become the
new dependency root.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

CHAT_BASE = "http://127.0.0.1:8201/api/chat"
VISION_DOC = "xmuse/FRONTEND_VISION.md"


def post(path: str, payload: dict) -> dict:
    url = f"{CHAT_BASE}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def lane(
    feature_id: str,
    title: str,
    prompt: str,
    depends_on: list[str],
    feature_group: str,
    capabilities: list[str] | None = None,
    priority: int = 80,
) -> dict:
    return {
        "feature_id": feature_id,
        "title": title,
        "prompt": prompt,
        "priority": priority,
        "capabilities": capabilities or ["code"],
        "depends_on": depends_on,
        "task_type": "execute",
        "gate_profiles": ["xmuse-core"],
        "feature_group": feature_group,
    }


def main() -> int:
    if not Path(VISION_DOC).exists():
        print(f"ERROR: {VISION_DOC} missing", file=sys.stderr)
        return 1

    conv = post(
        "/conversations",
        {"title": "Frontend Vision Layer 1-4 v2 (skip store-impl, already done)"},
    )
    conv_id = conv["id"]
    print(f"conversation: {conv_id}")

    msg = post(
        f"/conversations/{conv_id}/messages",
        {
            "author": "Operator",
            "role": "human",
            "content": (
                "Layer 1 participant_store.py is already complete and tested "
                "(38 passing tests). Implement the remaining backend layers "
                "described in xmuse/FRONTEND_VISION.md. Do NOT modify "
                "src/xmuse_core/chat/participant_store.py or "
                "tests/test_fe_vision_layer1_participant_store.py. Treat them "
                "as fixed-shape dependencies. Each lane below covers one slice."
            ),
        },
    )
    print(f"seed message: {msg['id']}")

    L1A = "fe-vision2-layer1-participants-api"
    L2 = "fe-vision2-layer2-worklist-endpoint"
    L3I = "fe-vision2-layer3-features-impl"
    L3T = "fe-vision2-layer3-features-tests"
    L4 = "fe-vision2-layer4-lane-graph-endpoint"
    L5 = "fe-vision2-layer5-acceptance-tests"

    common_intro = (
        "Read xmuse/FRONTEND_VISION.md and src/xmuse_core/chat/participant_store.py "
        "for the contract. ALREADY IMPLEMENTED (treat as fixed):\n"
        "  - Participant + RoleTemplate Pydantic models\n"
        "  - ParticipantStore + RoleTemplateStore classes\n"
        "  - _PREDEFINED_TEMPLATES (architect/review/execute) seeded on init\n"
        "  - participants/role_templates SQLite tables created in ChatStore._init_db\n\n"
        "Do not change those files. Touch only the files listed in your lane prompt. "
        "Add focused pytest tests in your lane only; full suite is gated by the "
        "platform after each lane."
    )

    lanes = [
        lane(
            L1A,
            "Layer 1: Participants + RoleTemplates HTTP API",
            (
                f"{common_intro}\n\n"
                "Add HTTP endpoints to xmuse/chat_api.py wiring up the existing "
                "ParticipantStore and RoleTemplateStore. Files allowed:\n"
                "- xmuse/chat_api.py (MODIFY)\n"
                "- tests/test_fe_vision_layer1_api.py (NEW)\n\n"
                "Endpoints (shapes from FRONTEND_VISION.md):\n"
                "  POST /api/chat/conversations  — extend with optional initial_participants. "
                "If absent, seed 3 builtins (architect/review/execute) using predefined templates.\n"
                "  GET    /api/chat/conversations/{id}/participants\n"
                "  POST   /api/chat/conversations/{id}/participants\n"
                "  DELETE /api/chat/conversations/{id}/participants/{participant_id}\n"
                "  GET    /api/chat/role-templates\n"
                "  POST   /api/chat/role-templates\n"
                "  PUT    /api/chat/role-templates/{id}\n"
                "  DELETE /api/chat/role-templates/{id}\n\n"
                "Predefined templates reject DELETE/PUT with 409. Tests must use "
                "fastapi.testclient.TestClient(create_app(tmp_path))."
            ),
            depends_on=[],
            feature_group="layer1-participants-api",
            priority=88,
        ),
        lane(
            L2,
            "Layer 2: Worklist endpoint",
            (
                f"{common_intro}\n\n"
                "Add GET /api/chat/conversations/{id}/worklist returning the "
                "WorklistResponse from FRONTEND_VISION.md (features grouped by "
                "feature_group with status_summary).\n"
                "Files allowed:\n"
                "- xmuse/chat_api.py (MODIFY)\n"
                "- tests/test_fe_vision_layer2_worklist.py (NEW)\n\n"
                "- Read xmuse/feature_lanes.json. Filter lanes whose conversation_id matches.\n"
                "- Group by feature_group; null → 'unscoped'.\n"
                "- status_summary uses xmuse_core.platform.state_normalizer.summarize_lane_states.\n"
                "- Sort lanes within group by topology then priority.\n"
                "- Tests cover: empty conversation, single feature with 3 lanes, "
                "multiple features, status_summary correctness."
            ),
            depends_on=[L1A],
            feature_group="layer2-worklist",
            capabilities=["code", "test"],
            priority=78,
        ),
        lane(
            L3I,
            "Layer 3: Feature read model",
            (
                f"{common_intro}\n\n"
                "Add to xmuse/dashboard_api.py:\n"
                "  GET /api/dashboard/features  (with ?track= ?status= ?conversation_id= filters)\n"
                "  GET /api/dashboard/features/{feature_group}  (joins LaneGraph snapshot)\n\n"
                "Files allowed:\n"
                "- xmuse/dashboard_api.py (MODIFY)\n\n"
                "Schemas: DashboardFeature / DashboardFeaturesResponse from FRONTEND_VISION.md.\n"
                "Status derivation: any blocked → blocked; any not-terminal → in_progress; "
                "all merged → merged; any failed (without merged) → failed; no lanes → planning.\n"
                "No tests in this lane; tests come in next lane."
            ),
            depends_on=[L1A],
            feature_group="layer3-features",
            priority=68,
        ),
        lane(
            L3T,
            "Layer 3: Feature read model tests",
            (
                f"{common_intro}\n\n"
                "Add tests for the Layer 3 endpoints. Files allowed:\n"
                "- tests/test_fe_vision_layer3_features.py (NEW)\n\n"
                "Cover: empty corpus, mixed statuses, ?track= filter, ?status= filter, "
                "?conversation_id= filter, /features/{feature_group} detail joining "
                "LaneGraph snapshot."
            ),
            depends_on=[L3I],
            feature_group="layer3-features",
            capabilities=["code", "test"],
            priority=67,
        ),
        lane(
            L4,
            "Layer 4: LaneGraph read endpoint",
            (
                f"{common_intro}\n\n"
                "Add GET /api/dashboard/lane-graphs/{graph_id} returning LaneGraphResponse "
                "from FRONTEND_VISION.md (lanes include effective_status from state_normalizer).\n"
                "Files allowed:\n"
                "- xmuse/dashboard_api.py (MODIFY)\n"
                "- tests/test_fe_vision_layer4_lane_graphs.py (NEW)\n\n"
                "Tests: existing snapshot returns 200, missing graph_id returns 404, "
                "effective_status reflects state_normalizer mapping."
            ),
            depends_on=[L1A],
            feature_group="layer4-lane-graphs",
            capabilities=["code", "test"],
            priority=58,
        ),
        lane(
            L5,
            "Layer 5: Acceptance checklist tests",
            (
                f"{common_intro}\n\n"
                "Add ONE test file covering FRONTEND_VISION.md acceptance items 1-9 "
                "(skip 10 — frontend-only). Each item is one test function.\n"
                "Files allowed:\n"
                "- tests/test_fe_vision_acceptance.py (NEW)\n\n"
                "Use TestClient(create_app(tmp_path)) for chat_api and dashboard_api. "
                "Tests assert REST contract only — no platform_runner, no Claude/Codex calls."
            ),
            depends_on=[L1A, L2, L3T, L4],
            feature_group="layer5-acceptance",
            capabilities=["code", "test"],
            priority=50,
        ),
    ]

    proposal = post(
        f"/conversations/{conv_id}/proposals",
        {
            "author": "Operator",
            "proposal_type": "frontend-vision-backend-v2",
            "content": "Frontend Vision Layer 1-4 (skip already-done store-impl)",
            "references": [VISION_DOC, "src/xmuse_core/chat/participant_store.py"],
        },
    )
    proposal_id = proposal["id"]
    print(f"proposal: {proposal_id}")

    resolution = post(
        f"/proposals/{proposal_id}/approve",
        {
            "approved_by": ["Operator"],
            "approval_mode": "human-direct",
            "goal_summary": (
                "Frontend Vision Layer 1-4 backend (v2) — store-impl already done"
            ),
            "content": {"lanes": lanes},
        },
    )
    print(f"resolution: {resolution['id']}")

    feature_lanes = json.loads(Path("xmuse/feature_lanes.json").read_text())
    projected = [
        l
        for l in feature_lanes.get("lanes", [])
        if isinstance(l, dict)
        and l.get("graph_id") == f"{resolution['id']}-graph-v{resolution['version']}"
    ]
    print(f"\nprojected lanes: {len(projected)}/{len(lanes)}")
    for l in projected:
        deps = l.get("depends_on", [])
        print(f"  {l.get('feature_id'):60} deps={len(deps)}  fg={l.get('feature_group')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
