from __future__ import annotations

from typing import Any

from enum import StrEnum

from pydantic import BaseModel, Field


class ProposalStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class ResolutionStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class Conversation(BaseModel):
    id: str
    title: str
    created_at: str


class ChatMessage(BaseModel):
    id: str
    conversation_id: str
    author: str
    role: str
    content: str
    created_at: str


class Proposal(BaseModel):
    id: str
    conversation_id: str
    author: str
    proposal_type: str
    content: str
    references: list[str] = Field(default_factory=list)
    status: ProposalStatus = ProposalStatus.OPEN
    created_at: str
    accepted_resolution_id: str | None = None


class StructuredResolution(BaseModel):
    id: str
    conversation_id: str
    version: int
    status: ResolutionStatus
    derived_from_proposal_ids: list[str] = Field(default_factory=list)
    approved_by: list[str] = Field(default_factory=list)
    approval_mode: str
    goal_summary: str
    content: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    superseded_by_resolution_id: str | None = None
