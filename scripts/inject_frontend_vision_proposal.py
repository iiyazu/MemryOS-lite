#!/usr/bin/env python3
"""Inject the Frontend Vision Layer 1-4 work as a multi-lane proposal.

Posts a conversation, message, and proposal to chat_api, then approves it.
The runner's TerminalRunWatcher / orchestrator picks up the projected lanes
and dispatches them to Claude execute-god.

Task structure (8 lanes, dep-aware):

  Layer 1: Participants + RoleTemplates
    - layer1-participants-store-impl       (no deps)
    - layer1-participants-api-impl         (deps: store)
    - layer1-participants-tests            (deps: api)

  Layer 2: Worklist endpoint
    - layer2-worklist-endpoint             (deps: layer1-api)

  Layer 3: Feature read model
    - layer3-features-read-model-impl      (deps: layer1-api)
    - layer3-features-read-model-tests     (deps: layer3-impl)

  Layer 4: LaneGraph read endpoint
    - layer4-lane-graph-read-endpoint      (deps: layer1-api)

  Layer 5: Smoke / regression
    - layer5-acceptance-checklist-tests    (deps: all of above)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import urllib.request


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

    # 1. conversation
    conv = post("/conversations", {"title": "Frontend Vision: Layer 1-4 backend"})
    conv_id = conv["id"]
    print(f"conversation: {conv_id}")

    # 2. seed message describing the work
    msg = post(
        f"/conversations/{conv_id}/messages",
        {
            "author": "Operator",
            "role": "human",
            "content": (
                "Implement the backend Layer 1-4 described in "
                f"{VISION_DOC}. The frontend contract is fixed; do not "
                "change endpoint shapes or types. Read that file first, "
                "then implement each lane within its scope only. Each lane "
                "must add focused tests for its own slice."
            ),
        },
    )
    print(f"seed message: {msg['id']}")

    # 3. multi-lane proposal
    L1S = "fe-vision-layer1-participants-store-impl"
    L1A = "fe-vision-layer1-participants-api-impl"
    L1T = "fe-vision-layer1-participants-tests"
    L2 = "fe-vision-layer2-worklist-endpoint"
    L3I = "fe-vision-layer3-features-read-model-impl"
    L3T = "fe-vision-layer3-features-read-model-tests"
    L4 = "fe-vision-layer4-lane-graph-read-endpoint"
    L5 = "fe-vision-layer5-acceptance-tests"

    common_intro = (
        "Read xmuse/FRONTEND_VISION.md and xmuse/FRONTEND_API_INCREMENTAL.md "
        "for the contract before editing. Touch only the files listed in your "
        "lane prompt. Existing endpoints/types must not change shape. "
        "Add focused pytest tests in your lane only; do not modify "
        "tests outside your scope."
    )

    lanes = [
        lane(
            L1S,
            "Layer 1: Participants + RoleTemplates store",
            (
                f"{common_intro}\n\n"
                "Add a SQLite-backed store for chat participants and role templates. "
                "Files allowed:\n"
                "- src/xmuse_core/chat/participant_store.py (NEW): defines Participant + RoleTemplate "
                "Pydantic models (matching FRONTEND_VISION.md type signatures), "
                "ParticipantStore + RoleTemplateStore classes.\n"
                "- src/xmuse_core/chat/store.py (MODIFY): on init, run two CREATE TABLE IF NOT EXISTS "
                "statements adding 'participants' and 'role_templates' tables. Do not change existing tables.\n\n"
                "Tables:\n"
                "  participants(participant_id text pk, conversation_id text fk, role text, "
                "display_name text, cli_kind text, model text, role_template_id text nullable, "
                "status text, last_seen_at text nullable, created_at text)\n"
                "  role_templates(id text pk, slug text unique, display_name text, prompt text, "
                "cli_kind text, default_model text, predefined integer, created_at text, updated_at text)\n\n"
                "Seed three predefined role templates on first init: "
                "'architect', 'review', 'execute' with the prompts from "
                "src/xmuse_core/chat/driver.py:_ROLE_PROMPTS. Mark them predefined=1.\n\n"
                "Do NOT modify endpoints, ChatDriver, or any other module. This lane is store-only."
            ),
            depends_on=[],
            feature_group="layer1-participants",
            priority=90,
        ),
        lane(
            L1A,
            "Layer 1: Participants + RoleTemplates API",
            (
                f"{common_intro}\n\n"
                "Wire the new stores into FastAPI endpoints. Files allowed:\n"
                "- xmuse/chat_api.py (MODIFY)\n\n"
                "Add these endpoints with bodies matching FRONTEND_VISION.md:\n"
                "  POST /api/chat/conversations  — extend to accept optional initial_participants list. "
                "If omitted, seed 3 default participants (architect/review/execute) using predefined templates. "
                "Reuse existing ChatStore.create_conversation; participant insert is a separate ParticipantStore call.\n"
                "  GET    /api/chat/conversations/{id}/participants\n"
                "  POST   /api/chat/conversations/{id}/participants\n"
                "  DELETE /api/chat/conversations/{id}/participants/{participant_id}\n"
                "  GET    /api/chat/role-templates\n"
                "  POST   /api/chat/role-templates\n"
                "  PUT    /api/chat/role-templates/{id}\n"
                "  DELETE /api/chat/role-templates/{id}\n\n"
                "Predefined templates (slug in {architect,review,execute}) must reject DELETE/PUT with 409.\n"
                "Do NOT touch tests in this lane; tests come in the next lane."
            ),
            depends_on=[L1S],
            feature_group="layer1-participants",
            priority=89,
        ),
        lane(
            L1T,
            "Layer 1: Participants + RoleTemplates tests",
            (
                f"{common_intro}\n\n"
                "Add focused tests. Files allowed:\n"
                "- tests/test_xmuse_chat_participants.py (NEW)\n"
                "- tests/test_xmuse_chat_role_templates.py (NEW)\n\n"
                "Cover at minimum:\n"
                "- Default conversation creation seeds 3 builtin participants.\n"
                "- POST initial_participants creates a conversation with custom participant set.\n"
                "- GET /participants returns them.\n"
                "- DELETE /participants/<id> works for non-builtin; cannot delete builtin role templates.\n"
                "- POST /role-templates creates a custom template and it shows in GET listing.\n"
                "- PUT predefined template returns 409.\n"
                "- DELETE predefined template returns 409.\n\n"
                "Use TestClient(create_app(tmp_path)) from xmuse/chat_api.py. Tests must run in <2s each."
            ),
            depends_on=[L1A],
            feature_group="layer1-participants",
            capabilities=["code", "test"],
            priority=88,
        ),
        lane(
            L2,
            "Layer 2: Worklist endpoint",
            (
                f"{common_intro}\n\n"
                "Add GET /api/chat/conversations/{id}/worklist returning the WorklistResponse "
                "shape from FRONTEND_VISION.md.\n\n"
                "Files allowed:\n"
                "- xmuse/chat_api.py (MODIFY)\n"
                "- tests/test_xmuse_chat_worklist.py (NEW)\n\n"
                "Implementation:\n"
                "- Read xmuse/feature_lanes.json. Filter lanes whose conversation_id matches.\n"
                "- Group by feature_group; if feature_group is null treat as group 'unscoped'.\n"
                "- For each group, build status_summary using xmuse_core.platform.state_normalizer.summarize_lane_states.\n"
                "- Sort lanes within group by depends_on topology then priority.\n"
                "- Lane.title = lane.title or lane.feature_id (truncated to 80 chars).\n\n"
                "Tests cover empty conversation, single feature with 3 lanes, multiple features, "
                "and status_summary correctness."
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
                "Add GET /api/dashboard/features and GET /api/dashboard/features/{feature_group} "
                "in xmuse/dashboard_api.py.\n\n"
                "Files allowed:\n"
                "- xmuse/dashboard_api.py (MODIFY)\n\n"
                "Schema must match DashboardFeature / DashboardFeaturesResponse in FRONTEND_VISION.md.\n"
                "Implementation:\n"
                "- Group lanes from feature_lanes.json by feature_group (null → 'unscoped').\n"
                "- Status derives from normalized statuses: any not_terminal → in_progress; "
                "any blocked_for_input → blocked; all merged → merged; any failed → failed; "
                "no lanes yet → planning.\n"
                "- Filter query params: ?track=, ?status=, ?conversation_id=.\n"
                "- /features/{feature_group} additionally returns the joined LaneGraph (read from xmuse/lane_graphs/<graph_id>.json).\n"
                "Do NOT add tests here; they come in next lane."
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
                "Add tests. Files allowed:\n"
                "- tests/test_xmuse_dashboard_features.py (NEW)\n\n"
                "Cover empty corpus, mixed statuses, filters, and feature_group detail page joining a LaneGraph snapshot."
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
                "Add GET /api/dashboard/lane-graphs/{graph_id} in xmuse/dashboard_api.py.\n\n"
                "Schema: LaneGraphResponse from FRONTEND_VISION.md (graph_id, conversation_id, version, "
                "status, lanes[]). Each lane includes effective_status from state_normalizer.\n"
                "Files allowed:\n"
                "- xmuse/dashboard_api.py (MODIFY)\n"
                "- tests/test_xmuse_dashboard_lane_graphs.py (NEW)\n\n"
                "Tests cover existing snapshot, missing graph_id (404), and effective_status correctness."
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
                "Add a single end-to-end test file covering the FRONTEND_VISION.md acceptance "
                "checklist items 1-9. Files allowed:\n"
                "- tests/test_xmuse_frontend_vision_acceptance.py (NEW)\n\n"
                "Use chat_api + dashboard_api TestClient. Each numbered acceptance item is one test. "
                "Skip item 10 (frontend-only). Tests must not rely on external CLI tools or running "
                "platform_runner; they assert REST contract only."
            ),
            depends_on=[L1T, L2, L3T, L4],
            feature_group="layer5-acceptance",
            capabilities=["code", "test"],
            priority=50,
        ),
    ]

    proposal = post(
        f"/conversations/{conv_id}/proposals",
        {
            "author": "Operator",
            "proposal_type": "frontend-vision-backend",
            "content": "Implement Frontend Vision Layer 1-4 (8 lanes, dep-aware)",
            "references": [VISION_DOC, "xmuse/FRONTEND_API_INCREMENTAL.md"],
        },
    )
    proposal_id = proposal["id"]
    print(f"proposal: {proposal_id}")

    # 4. approve → triggers planner.build_lane_graph + projection
    resolution = post(
        f"/proposals/{proposal_id}/approve",
        {
            "approved_by": ["Operator"],
            "approval_mode": "human-direct",
            "goal_summary": "Implement Frontend Vision Layer 1-4 backend per FRONTEND_VISION.md",
            "content": {"lanes": lanes},
        },
    )
    print(f"resolution: {resolution['id']}")
    print(f"graph: {resolution['id']}-graph-v{resolution['version']}")

    # Verify projection
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
