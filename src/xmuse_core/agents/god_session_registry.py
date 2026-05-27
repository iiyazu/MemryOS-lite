from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4


@dataclass
class GodSessionRecord:
    god_session_id: str
    role: str
    agent_name: str
    runtime: str
    session_address: str
    session_inbox_id: str
    status: str = "starting"
    assignment_feature_id: str | None = None
    pid: int | None = None


class GodSessionRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def create(
        self,
        role: str,
        agent_name: str,
        runtime: str,
        session_address: str,
        session_inbox_id: str,
    ) -> GodSessionRecord:
        sessions = self.list()
        for existing in sessions:
            if existing.session_address == session_address:
                raise ValueError(f"duplicate session_address: {session_address}")
            if existing.session_inbox_id == session_inbox_id:
                raise ValueError(f"duplicate session_inbox_id: {session_inbox_id}")

        record = GodSessionRecord(
            god_session_id=f"god-{uuid4().hex}",
            role=role,
            agent_name=agent_name,
            runtime=runtime,
            session_address=session_address,
            session_inbox_id=session_inbox_id,
        )
        sessions.append(record)
        self._write(sessions)
        return record

    def list(self) -> list[GodSessionRecord]:
        payload = self._read()
        return [GodSessionRecord(**entry) for entry in payload["sessions"]]

    def get(self, god_session_id: str) -> GodSessionRecord:
        for record in self.list():
            if record.god_session_id == god_session_id:
                return record
        raise KeyError(god_session_id)

    def find_by_address(self, session_address: str) -> GodSessionRecord:
        for record in self.list():
            if record.session_address == session_address:
                return record
        raise KeyError(session_address)

    def find_by_inbox(self, session_inbox_id: str) -> GodSessionRecord:
        for record in self.list():
            if record.session_inbox_id == session_inbox_id:
                return record
        raise KeyError(session_inbox_id)

    def assign(self, god_session_id: str, feature_id: str | None) -> GodSessionRecord:
        sessions = self.list()
        for index, record in enumerate(sessions):
            if record.god_session_id == god_session_id:
                updated = replace(record, assignment_feature_id=feature_id)
                sessions[index] = updated
                self._write(sessions)
                return updated
        raise KeyError(god_session_id)

    def _read(self) -> dict[str, list[dict[str, object]]]:
        if not self.path.exists():
            return {"sessions": []}
        return json.loads(self.path.read_text())

    def _write(self, sessions: list[GodSessionRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"sessions": [asdict(session) for session in sessions]}
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f"{self.path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle)
            temp_path = Path(handle.name)
        temp_path.replace(self.path)
