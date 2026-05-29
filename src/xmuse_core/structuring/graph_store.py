from __future__ import annotations

import json
from pathlib import Path

from xmuse_core.structuring.models import LaneGraph


class LaneGraphStore:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def save(self, graph: LaneGraph) -> Path:
        path = self._path_for(graph.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(graph.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def get(self, graph_id: str) -> LaneGraph:
        path = self._path_for(graph_id)
        if not path.exists():
            raise KeyError(f"lane graph not found: {graph_id}")
        return LaneGraph.model_validate_json(path.read_text(encoding="utf-8"))

    def _path_for(self, graph_id: str) -> Path:
        return self._root / f"{graph_id}.json"
