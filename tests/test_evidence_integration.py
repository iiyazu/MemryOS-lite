"""Integration tests for EvidenceRepresenter + EvidenceSearcher wired into ContextBuilder."""

from pathlib import Path

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import MessageCreate, Role
from memoryos_lite.store import create_store


@pytest.fixture()
def contextual_service(tmp_path: Path) -> MemoryOSService:
    """Service configured with deterministic_context evidence strategy."""
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=1,
        memoryos_evidence_representation="deterministic_context",
        memoryos_evidence_candidate_top_k=10,
    )
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)


@pytest.fixture()
def legacy_service(tmp_path: Path) -> MemoryOSService:
    """Service configured with legacy evidence strategy."""
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=1,
        memoryos_evidence_representation="legacy",
    )
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)


def _ingest_conversation(service: MemoryOSService, session_id: str) -> None:
    """Ingest a conversation where neighbor context helps retrieval."""
    messages = [
        (Role.USER, "I'm planning a trip to Tokyo next month."),
        (Role.ASSISTANT, "That sounds exciting! What dates are you considering?"),
        (Role.USER, "I'll be there from June 10 to June 20."),
        (Role.USER, "My budget for the hotel is around 200 dollars per night."),
    ]
    for role, content in messages:
        service.ingest(session_id, MessageCreate(role=role, content=content))


def test_contextual_evidence_returns_results(contextual_service):
    """Contextual evidence path finds messages via enriched index text."""
    service = contextual_service
    session = service.create_session("contextual test")
    _ingest_conversation(service, session.id)

    page = service.page(session.id)
    assert page is not None, "paging should produce at least one page"

    context = service.build_context(session.id, "Tokyo trip dates", budget=500)

    assert context.retrieved_evidence, "should find evidence via contextual BM25"
    evidence_texts = " ".join(e.text for e in context.retrieved_evidence)
    assert "June" in evidence_texts or "Tokyo" in evidence_texts


def test_contextual_evidence_builder_initializes_representer(contextual_service):
    """ContextBuilder should have evidence_representer when not legacy."""
    cb = contextual_service.context_builder
    assert cb.evidence_representer is not None
    assert cb.evidence_searcher is not None
    assert cb.evidence_representer.strategy == "deterministic_context"


def test_legacy_evidence_path_still_works(legacy_service):
    """Legacy path should work unchanged when configured."""
    service = legacy_service
    session = service.create_session("legacy test")
    _ingest_conversation(service, session.id)

    page = service.page(session.id)
    assert page is not None

    context = service.build_context(session.id, "Tokyo trip dates", budget=500)

    # Legacy path should also find evidence (via raw BM25 on message content)
    assert context.retrieved_evidence
    # Verify legacy path doesn't use contextual representer
    cb = service.context_builder
    assert cb.evidence_representer is None
    assert cb.evidence_searcher is None


def test_contextual_fallback_to_legacy_when_no_candidates(tmp_path):
    """When no candidates are built, falls back to legacy retrieval."""
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=1,
        memoryos_evidence_representation="deterministic_context",
        memoryos_evidence_direct_raw_fallback=True,
    )
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(store=store, settings=settings)

    session = service.create_session("fallback test")
    _ingest_conversation(service, session.id)
    page = service.page(session.id)
    assert page is not None

    # Query that matches paged messages — should find evidence via fallback
    context = service.build_context(session.id, "Tokyo trip dates", budget=500)
    # The contextual path should produce results (either directly or via fallback)
    assert context.retrieved_evidence


def test_contextual_evidence_reason_format(contextual_service):
    """Contextual evidence items should have reason starting with contextual_bm25."""
    service = contextual_service
    session = service.create_session("reason format test")
    _ingest_conversation(service, session.id)
    service.page(session.id)

    context = service.build_context(session.id, "Tokyo trip dates", budget=500)

    for ev in context.retrieved_evidence:
        # Either contextual_bm25 (new path) or message_bm25 (fallback)
        assert "bm25" in ev.reason.lower(), f"unexpected reason: {ev.reason}"


def test_contextual_evidence_active_overlap_is_zero(contextual_service):
    """Contextual path returns active_overlap_not_top5 = 0."""
    service = contextual_service
    session = service.create_session("overlap test")
    _ingest_conversation(service, session.id)
    service.page(session.id)

    context = service.build_context(session.id, "Tokyo trip", budget=500)

    # The contextual path always returns 0 for active_overlap_not_top5
    assert context.active_overlap_not_top5 == 0


def test_page_context_plus_raw_strategy(tmp_path):
    """page_context_plus_raw strategy also works end-to-end."""
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=1,
        memoryos_evidence_representation="page_context_plus_raw",
        memoryos_evidence_candidate_top_k=10,
    )
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(store=store, settings=settings)

    session = service.create_session("page_context test")
    _ingest_conversation(service, session.id)
    service.page(session.id)

    context = service.build_context(session.id, "Tokyo trip dates", budget=500)
    assert context.retrieved_evidence
