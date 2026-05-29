#!/usr/bin/env python3
"""CLI for xmuse blueprint-anchored self-evolution bootstrap."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xmuse_core.self_evolution import SelfEvolutionController

PROJECT_ROOT = Path(__file__).resolve().parents[1]
XMUSE_ROOT = PROJECT_ROOT / "xmuse"
DEFAULT_BLUEPRINT = (
    PROJECT_ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-05-28-xmuse-initial-self-evolution-blueprint.md"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run xmuse self-evolution bootstrap actions")
    parser.add_argument("action", choices=["aggregate", "dry-run", "from-evidence"])
    parser.add_argument("--graph-id")
    parser.add_argument("--evidence-bundle-id")
    parser.add_argument("--xmuse-root", type=Path, default=XMUSE_ROOT)
    parser.add_argument("--blueprint", type=Path, default=DEFAULT_BLUEPRINT)
    args = parser.parse_args()

    controller = SelfEvolutionController(
        xmuse_root=args.xmuse_root,
        blueprint_path=args.blueprint,
    )
    if args.action in {"aggregate", "dry-run"} and not args.graph_id:
        parser.error("--graph-id is required for aggregate and dry-run")
    if args.action == "from-evidence" and not args.evidence_bundle_id:
        parser.error("--evidence-bundle-id is required for from-evidence")

    if args.action == "aggregate":
        result = controller.aggregate_run_terminal(args.graph_id)
    elif args.action == "dry-run":
        result = controller.dry_run_from_graph(args.graph_id)
    else:
        result = controller.run_from_evidence_bundle(args.evidence_bundle_id)
    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
