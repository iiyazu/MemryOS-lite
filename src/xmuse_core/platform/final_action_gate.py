from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class PendingFinalAction(BaseModel):
    id: str
    lane_id: str
    verdict_id: str
    action: str
    target_status: str
    status: str = "pending"
    summary: str
    resolved_by: str | None = None


class FinalActionGateStore:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def list_actions(self) -> list[PendingFinalAction]:
        data = self._read()
        return [PendingFinalAction(**item) for item in data.get("holds", [])]

    def create_hold(
        self,
        *,
        lane_id: str,
        verdict_id: str,
        action: str,
        target_status: str,
        summary: str,
    ) -> PendingFinalAction:
        hold = PendingFinalAction(
            id=f"final-{uuid.uuid4().hex[:12]}",
            lane_id=lane_id,
            verdict_id=verdict_id,
            action=action,
            target_status=target_status,
            summary=summary,
        )
        data = self._read()
        holds = data.setdefault("holds", [])
        holds.append(hold.model_dump(mode="json"))
        self._write(data)
        return hold

    def resolve(self, hold_id: str, *, status: str, resolved_by: str | None = None) -> PendingFinalAction:
        data = self._read()
        for item in data.get("holds", []):
            if item.get("id") == hold_id:
                item["status"] = status
                item["resolved_by"] = resolved_by
                self._write(data)
                return PendingFinalAction(**item)
        raise KeyError(f"unknown final action hold: {hold_id}")

    def get(self, hold_id: str) -> PendingFinalAction:
        for item in self._read().get("holds", []):
            if item.get("id") == hold_id:
                return PendingFinalAction(**item)
        raise KeyError(f"unknown final action hold: {hold_id}")

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"holds": []}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
