#!/usr/bin/env python3
"""REST API for the xmuse chat-plane MVP."""

import json
import sqlite3
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from xmuse_core.chat.participant_store import ParticipantStore, RoleTemplate, RoleTemplateStore
from xmuse_core.chat.store import ChatStore
from xmuse_core.structuring.graph_store import LaneGraphStore
from xmuse_core.structuring.planner import build_lane_graph
from xmuse_core.structuring.projection import project_ready_lanes

DEFAULT_PORT = 8201
DEFAULT_BASE_DIR = Path(__file__).resolve().parent


class ParticipantInit(BaseModel):
    role: str = Field(min_length=1)
    cli_kind: Literal["claude", "codex"]
    model: str | None = None
    role_template_id: str | None = None
    display_name: str | None = None


class ConversationCreate(BaseModel):
    title: str = Field(min_length=1)
    initial_participants: list[ParticipantInit] | None = None


class RoleTemplateCreate(BaseModel):
    slug: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    cli_kind: Literal["claude", "codex"]
    default_model: str = Field(min_length=1)


class RoleTemplateUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1)
    prompt: str | None = Field(default=None, min_length=1)
    cli_kind: Literal["claude", "codex"] | None = None
    default_model: str | None = Field(default=None, min_length=1)


class MessageCreate(BaseModel):
    author: str = Field(min_length=1)
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class ProposalCreate(BaseModel):
    author: str = Field(min_length=1)
    proposal_type: str = Field(min_length=1)
    content: str = Field(min_length=1)
    references: list[str] = Field(default_factory=list)


class ProposalApproval(BaseModel):
    approved_by: list[str] = Field(min_length=1)
    approval_mode: str = Field(min_length=1)
    goal_summary: str = Field(min_length=1)
    content: dict = Field(default_factory=dict)


class ThreadMessageCreate(BaseModel):
    message: str = Field(min_length=1)


def _store(base_dir: Path) -> ChatStore:
    return ChatStore(base_dir / "chat.db")


def _participant_store(base_dir: Path) -> ParticipantStore:
    _store(base_dir)
    return ParticipantStore(base_dir / "chat.db")


def _role_template_store(base_dir: Path) -> RoleTemplateStore:
    _store(base_dir)
    return RoleTemplateStore(base_dir / "chat.db")


def _conversation_exists(store: ChatStore, conversation_id: str) -> bool:
    return any(conversation.id == conversation_id for conversation in store.list_conversations())


def _default_participant_inits(role_templates: RoleTemplateStore) -> list[ParticipantInit]:
    defaults: list[ParticipantInit] = []
    for role in ("architect", "review", "execute"):
        template = role_templates.get_by_slug(role)
        if template is None:
            raise HTTPException(status_code=500, detail=f"missing predefined role template: {role}")
        defaults.append(
            ParticipantInit(
                role=role,
                cli_kind=template.cli_kind,
                model=template.default_model,
                role_template_id=template.id,
                display_name=f"{role}-god",
            )
        )
    return defaults


def _template_for_participant(
    role_templates: RoleTemplateStore,
    participant: ParticipantInit,
) -> RoleTemplate:
    if participant.role_template_id is not None:
        try:
            return role_templates.get(participant.role_template_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="role template not found") from exc

    template = role_templates.get_by_slug(participant.role)
    if template is None or not template.predefined:
        raise HTTPException(
            status_code=400,
            detail="role_template_id is required for custom participants",
        )
    return template


def _add_participants(
    *,
    base_dir: Path,
    conversation_id: str,
    participants: list[ParticipantInit],
) -> list[dict[str, object]]:
    participant_store = _participant_store(base_dir)
    role_templates = _role_template_store(base_dir)
    created = []
    for participant in participants:
        template = _template_for_participant(role_templates, participant)
        try:
            created_participant = participant_store.add(
                conversation_id=conversation_id,
                role=participant.role.strip(),
                display_name=(participant.display_name or f"{participant.role}-god").strip(),
                cli_kind=participant.cli_kind,
                model=(participant.model or template.default_model).strip(),
                role_template_id=template.id,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=404, detail="conversation not found") from exc
        created.append(created_participant.model_dump(mode="json"))
    return created


def _append_resolution_read_model(base_dir: Path, resolution_payload: dict[str, object]) -> None:
    read_models_dir = base_dir / "read_models"
    path = read_models_dir / "resolutions.json"
    data: dict[str, list[dict[str, object]]]
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {"resolutions": []}
    else:
        data = {"resolutions": []}

    resolutions = data.get("resolutions", [])
    if not isinstance(resolutions, list):
        resolutions = []

    entry = {
        "resolution_id": resolution_payload["id"],
        "conversation_id": resolution_payload["conversation_id"],
        "version": resolution_payload["version"],
        "status": resolution_payload["status"],
        "goal_summary": resolution_payload["goal_summary"],
        "approved_by": resolution_payload["approved_by"],
        "approval_mode": resolution_payload["approval_mode"],
    }
    data["resolutions"] = [
        item for item in resolutions
        if isinstance(item, dict) and item.get("resolution_id") != entry["resolution_id"]
    ]
    data["resolutions"].append(entry)
    read_models_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _project_resolution_into_execution_queue(base_dir: Path, resolution: object) -> None:
    graph = build_lane_graph(resolution)
    LaneGraphStore(base_dir / "lane_graphs").save(graph)
    project_ready_lanes(graph, base_dir / "feature_lanes.json")


def create_app(base_dir: Path | str = DEFAULT_BASE_DIR) -> FastAPI:
    root = Path(base_dir)
    app = FastAPI(title="xmuse Chat API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/api/chat/conversations", status_code=status.HTTP_201_CREATED)
    def create_conversation(request: ConversationCreate) -> dict[str, object]:
        store = _store(root)
        role_templates = _role_template_store(root)
        participants = (
            _default_participant_inits(role_templates)
            if request.initial_participants is None
            else request.initial_participants
        )
        for participant in participants:
            _template_for_participant(role_templates, participant)

        conversation = store.create_conversation(title=request.title.strip())
        payload = conversation.model_dump(mode="json")
        payload["participants"] = _add_participants(
            base_dir=root,
            conversation_id=conversation.id,
            participants=participants,
        )
        return payload

    @app.get("/api/chat/conversations")
    def list_conversations() -> dict[str, object]:
        conversations = _store(root).list_conversations()
        return {
            "conversations": [
                conversation.model_dump(mode="json") for conversation in conversations
            ]
        }

    @app.get("/api/chat/conversations/{conversation_id}/participants")
    def list_participants(conversation_id: str) -> dict[str, object]:
        store = _store(root)
        if not _conversation_exists(store, conversation_id):
            raise HTTPException(status_code=404, detail="conversation not found")
        participants = _participant_store(root).list_by_conversation(conversation_id)
        return {
            "participants": [
                participant.model_dump(mode="json") for participant in participants
            ]
        }

    @app.post(
        "/api/chat/conversations/{conversation_id}/participants",
        status_code=status.HTTP_201_CREATED,
    )
    def add_participant(conversation_id: str, request: ParticipantInit) -> dict[str, object]:
        created = _add_participants(
            base_dir=root,
            conversation_id=conversation_id,
            participants=[request],
        )
        return created[0]

    @app.delete(
        "/api/chat/conversations/{conversation_id}/participants/{participant_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_participant(conversation_id: str, participant_id: str) -> None:
        store = _store(root)
        if not _conversation_exists(store, conversation_id):
            raise HTTPException(status_code=404, detail="conversation not found")
        participant_store = _participant_store(root)
        try:
            participant = participant_store.get(participant_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="participant not found") from exc
        if participant.conversation_id != conversation_id:
            raise HTTPException(status_code=404, detail="participant not found")
        participant_store.delete(participant_id)

    @app.get("/api/chat/role-templates")
    def list_role_templates() -> dict[str, object]:
        templates = _role_template_store(root).list_all()
        return {"role_templates": [template.model_dump(mode="json") for template in templates]}

    @app.post("/api/chat/role-templates", status_code=status.HTTP_201_CREATED)
    def create_role_template(request: RoleTemplateCreate) -> dict[str, object]:
        try:
            template = _role_template_store(root).create(
                slug=request.slug.strip(),
                display_name=request.display_name.strip(),
                prompt=request.prompt.strip(),
                cli_kind=request.cli_kind,
                default_model=request.default_model.strip(),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="role template slug already exists",
            ) from exc
        return template.model_dump(mode="json")

    @app.put("/api/chat/role-templates/{template_id}")
    def update_role_template(template_id: str, request: RoleTemplateUpdate) -> dict[str, object]:
        role_templates = _role_template_store(root)
        try:
            existing = role_templates.get(template_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="role template not found") from exc
        if existing.predefined:
            raise HTTPException(status_code=409, detail="predefined role templates are read-only")
        template = role_templates.update(
            template_id,
            display_name=request.display_name.strip() if request.display_name is not None else None,
            prompt=request.prompt.strip() if request.prompt is not None else None,
            cli_kind=request.cli_kind,
            default_model=(
                request.default_model.strip() if request.default_model is not None else None
            ),
        )
        return template.model_dump(mode="json")

    @app.delete(
        "/api/chat/role-templates/{template_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_role_template(template_id: str) -> None:
        role_templates = _role_template_store(root)
        try:
            role_templates.delete(template_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="role template not found") from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail="predefined role templates are read-only",
            ) from exc

    @app.get("/api/chat/conversations/{conversation_id}/messages")
    def list_messages(conversation_id: str) -> dict[str, object]:
        messages = _store(root).list_messages(conversation_id)
        return {"messages": [message.model_dump(mode="json") for message in messages]}

    @app.post(
        "/api/chat/conversations/{conversation_id}/messages",
        status_code=status.HTTP_201_CREATED,
    )
    def add_message(conversation_id: str, request: MessageCreate) -> dict[str, object]:
        try:
            message = _store(root).add_message(
                conversation_id=conversation_id,
                author=request.author.strip(),
                role=request.role.strip(),
                content=request.content.strip(),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=404, detail="conversation not found") from exc
        return message.model_dump(mode="json")

    @app.post(
        "/api/chat/conversations/{conversation_id}/proposals",
        status_code=status.HTTP_201_CREATED,
    )
    def create_proposal(conversation_id: str, request: ProposalCreate) -> dict[str, object]:
        try:
            proposal = _store(root).create_proposal(
                conversation_id=conversation_id,
                author=request.author.strip(),
                proposal_type=request.proposal_type.strip(),
                content=request.content.strip(),
                references=request.references,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=404, detail="conversation not found") from exc
        return proposal.model_dump(mode="json")

    @app.post("/api/chat/proposals/{proposal_id}/approve")
    def approve_proposal(proposal_id: str, request: ProposalApproval) -> dict[str, object]:
        try:
            resolution = _store(root).approve_proposal(
                proposal_id=proposal_id,
                approved_by=request.approved_by,
                approval_mode=request.approval_mode.strip(),
                goal_summary=request.goal_summary.strip(),
                content=request.content,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="proposal not found") from exc
        payload = resolution.model_dump(mode="json")
        _append_resolution_read_model(root, payload)
        _project_resolution_into_execution_queue(root, resolution)
        return payload

    @app.get("/api/chat/resolutions/{resolution_id}")
    def get_resolution(resolution_id: str) -> dict[str, object]:
        try:
            resolution = _store(root).get_resolution(resolution_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="resolution not found") from exc
        return resolution.model_dump(mode="json")

    @app.get("/api/chat/threads")
    def list_threads() -> dict[str, object]:
        store = _store(root)
        threads = []
        for conversation in store.list_conversations():
            messages = store.list_messages(conversation.id)
            last_message = messages[-1] if messages else None
            threads.append(
                {
                    "id": conversation.id,
                    "featureId": conversation.title,
                    "title": conversation.title,
                    "agent": "Human + Gods",
                    "status": "pending" if not messages else "reviewed",
                    "updatedAt": (
                        last_message.created_at if last_message else conversation.created_at
                    ),
                    "summary": (last_message.content if last_message else conversation.title),
                    "messages": [
                        {
                            "id": message.id,
                            "role": (
                                "user"
                                if message.role == "human"
                                else ("tool" if message.role == "tool" else "assistant")
                            ),
                            "author": message.author,
                            "kind": (
                                "tool_call"
                                if message.role == "tool"
                                else (
                                    "checkpoint"
                                    if message.role == "human"
                                    else "answer"
                                )
                            ),
                            "content": message.content,
                        }
                        for message in messages
                    ],
                }
            )
        return {"threads": threads}

    @app.post("/api/chat/threads/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
    def add_thread_message(conversation_id: str, request: ThreadMessageCreate) -> dict[str, object]:
        try:
            message = _store(root).add_message(
                conversation_id=conversation_id,
                author="Human operator",
                role="human",
                content=request.message.strip(),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=404, detail="conversation not found") from exc
        return {
            "thread_id": conversation_id,
            "message": {
                "id": message.id,
                "role": "user",
                "author": message.author,
                "kind": "checkpoint",
                "content": message.content,
            },
        }

    return app


def main() -> None:
    uvicorn.run(create_app(), host="127.0.0.1", port=DEFAULT_PORT)


if __name__ == "__main__":
    main()
