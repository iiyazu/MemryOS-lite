"""Tests for ParticipantStore and RoleTemplateStore.

Covers:
- ParticipantStore: add / get / list_by_conversation / update_status / delete
- RoleTemplateStore: create / get / get_by_slug / list_all / update / delete
- Predefined-template guard: delete raises ValueError
- Seeding idempotency
"""
from __future__ import annotations

from pathlib import Path

import pytest

from xmuse_core.chat.participant_store import (
    ParticipantStore,
    RoleTemplateStore,
    _PREDEFINED_TEMPLATES,
)
from xmuse_core.chat.store import ChatStore


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Fresh chat.db with all tables created and predefined templates seeded."""
    path = tmp_path / "chat.db"
    ChatStore(path)
    return path


@pytest.fixture()
def conv_id(db_path: Path) -> str:
    """A conversation id that satisfies the FK constraint on participants."""
    return ChatStore(db_path).create_conversation("test-conv").id


# ---------------------------------------------------------------------------
# ParticipantStore
# ---------------------------------------------------------------------------


class TestParticipantStore:
    def test_add_returns_participant_with_correct_fields(
        self, db_path: Path, conv_id: str
    ) -> None:
        store = ParticipantStore(db_path)
        p = store.add(
            conversation_id=conv_id,
            role="architect",
            display_name="Architect GOD",
            cli_kind="claude",
            model="sonnet",
        )
        assert p.participant_id.startswith("part_")
        assert p.conversation_id == conv_id
        assert p.role == "architect"
        assert p.display_name == "Architect GOD"
        assert p.cli_kind == "claude"
        assert p.model == "sonnet"
        assert p.role_template_id is None
        assert p.status == "active"
        assert p.last_seen_at is None
        assert p.created_at

    def test_add_with_role_template_id(self, db_path: Path, conv_id: str) -> None:
        store = ParticipantStore(db_path)
        p = store.add(
            conversation_id=conv_id,
            role="review",
            display_name="Review GOD",
            cli_kind="claude",
            model="sonnet",
            role_template_id="tmpl_abc123",
        )
        assert p.role_template_id == "tmpl_abc123"

    def test_get_returns_persisted_participant(
        self, db_path: Path, conv_id: str
    ) -> None:
        store = ParticipantStore(db_path)
        added = store.add(
            conversation_id=conv_id,
            role="execute",
            display_name="Execute GOD",
            cli_kind="codex",
            model="gpt-4o",
        )
        fetched = store.get(added.participant_id)
        assert fetched.participant_id == added.participant_id
        assert fetched.role == "execute"
        assert fetched.cli_kind == "codex"

    def test_get_raises_key_error_for_unknown(self, db_path: Path) -> None:
        store = ParticipantStore(db_path)
        with pytest.raises(KeyError, match="unknown participant"):
            store.get("part_does_not_exist")

    def test_list_by_conversation_returns_only_matching(
        self, db_path: Path
    ) -> None:
        chat = ChatStore(db_path)
        conv1 = chat.create_conversation("conv-1")
        conv2 = chat.create_conversation("conv-2")
        store = ParticipantStore(db_path)

        p1 = store.add(
            conversation_id=conv1.id,
            role="architect",
            display_name="A",
            cli_kind="claude",
            model="sonnet",
        )
        p2 = store.add(
            conversation_id=conv1.id,
            role="review",
            display_name="R",
            cli_kind="claude",
            model="sonnet",
        )
        store.add(
            conversation_id=conv2.id,
            role="execute",
            display_name="E",
            cli_kind="codex",
            model="gpt-4o",
        )

        result = store.list_by_conversation(conv1.id)
        ids = {p.participant_id for p in result}
        assert p1.participant_id in ids
        assert p2.participant_id in ids
        assert len(result) == 2

    def test_list_by_conversation_empty_when_none_added(
        self, db_path: Path, conv_id: str
    ) -> None:
        store = ParticipantStore(db_path)
        assert store.list_by_conversation(conv_id) == []

    def test_update_status_to_stopped(self, db_path: Path, conv_id: str) -> None:
        store = ParticipantStore(db_path)
        p = store.add(
            conversation_id=conv_id,
            role="architect",
            display_name="A",
            cli_kind="claude",
            model="sonnet",
        )
        updated = store.update_status(p.participant_id, "stopped")
        assert updated.status == "stopped"
        assert updated.last_seen_at is not None

    def test_update_status_with_explicit_last_seen_at(
        self, db_path: Path, conv_id: str
    ) -> None:
        store = ParticipantStore(db_path)
        p = store.add(
            conversation_id=conv_id,
            role="architect",
            display_name="A",
            cli_kind="claude",
            model="sonnet",
        )
        ts = "2026-05-28T10:00:00Z"
        updated = store.update_status(p.participant_id, "stopped", last_seen_at=ts)
        assert updated.last_seen_at == ts

    def test_update_status_back_to_active(self, db_path: Path, conv_id: str) -> None:
        store = ParticipantStore(db_path)
        p = store.add(
            conversation_id=conv_id,
            role="architect",
            display_name="A",
            cli_kind="claude",
            model="sonnet",
        )
        store.update_status(p.participant_id, "stopped")
        updated = store.update_status(p.participant_id, "active")
        assert updated.status == "active"

    def test_delete_removes_participant(self, db_path: Path, conv_id: str) -> None:
        store = ParticipantStore(db_path)
        p = store.add(
            conversation_id=conv_id,
            role="architect",
            display_name="A",
            cli_kind="claude",
            model="sonnet",
        )
        store.delete(p.participant_id)
        with pytest.raises(KeyError):
            store.get(p.participant_id)

    def test_delete_nonexistent_is_silent(self, db_path: Path) -> None:
        store = ParticipantStore(db_path)
        # Should not raise
        store.delete("part_nonexistent")


# ---------------------------------------------------------------------------
# RoleTemplateStore
# ---------------------------------------------------------------------------


class TestRoleTemplateStore:
    def test_predefined_templates_seeded_by_chat_store(
        self, db_path: Path
    ) -> None:
        store = RoleTemplateStore(db_path)
        slugs = {t.slug for t in store.list_all()}
        assert "architect" in slugs
        assert "review" in slugs
        assert "execute" in slugs

    def test_predefined_templates_have_predefined_flag(
        self, db_path: Path
    ) -> None:
        store = RoleTemplateStore(db_path)
        predefined_slugs = {
            t.slug for t in store.list_all() if t.predefined
        }
        assert {"architect", "review", "execute"}.issubset(predefined_slugs)

    def test_create_returns_non_predefined_template(
        self, db_path: Path
    ) -> None:
        store = RoleTemplateStore(db_path)
        t = store.create(
            slug="custom-role",
            display_name="Custom Role",
            prompt="You are a custom agent.",
            cli_kind="claude",
            default_model="haiku",
        )
        assert t.id.startswith("tmpl_")
        assert t.slug == "custom-role"
        assert t.predefined is False
        assert t.created_at
        assert t.updated_at

    def test_get_returns_template_by_id(self, db_path: Path) -> None:
        store = RoleTemplateStore(db_path)
        created = store.create(
            slug="my-role",
            display_name="My Role",
            prompt="Do stuff.",
            cli_kind="codex",
            default_model="gpt-4o",
        )
        fetched = store.get(created.id)
        assert fetched.id == created.id
        assert fetched.slug == "my-role"

    def test_get_raises_key_error_for_unknown(self, db_path: Path) -> None:
        store = RoleTemplateStore(db_path)
        with pytest.raises(KeyError, match="unknown role_template"):
            store.get("tmpl_nonexistent")

    def test_get_by_slug_returns_predefined(self, db_path: Path) -> None:
        store = RoleTemplateStore(db_path)
        result = store.get_by_slug("architect")
        assert result is not None
        assert result.slug == "architect"
        assert result.predefined is True

    def test_get_by_slug_returns_none_for_unknown(self, db_path: Path) -> None:
        store = RoleTemplateStore(db_path)
        assert store.get_by_slug("no-such-slug") is None

    def test_list_all_includes_predefined_and_custom(
        self, db_path: Path
    ) -> None:
        store = RoleTemplateStore(db_path)
        store.create(
            slug="extra",
            display_name="Extra",
            prompt="...",
            cli_kind="claude",
            default_model="sonnet",
        )
        slugs = {t.slug for t in store.list_all()}
        assert "architect" in slugs
        assert "extra" in slugs

    def test_update_changes_display_name_and_prompt(
        self, db_path: Path
    ) -> None:
        store = RoleTemplateStore(db_path)
        created = store.create(
            slug="updatable",
            display_name="Old Name",
            prompt="Old prompt.",
            cli_kind="claude",
            default_model="sonnet",
        )
        updated = store.update(
            created.id, display_name="New Name", prompt="New prompt."
        )
        assert updated.display_name == "New Name"
        assert updated.prompt == "New prompt."
        assert updated.updated_at >= created.updated_at

    def test_update_partial_leaves_other_fields_unchanged(
        self, db_path: Path
    ) -> None:
        store = RoleTemplateStore(db_path)
        created = store.create(
            slug="partial",
            display_name="Name",
            prompt="Prompt.",
            cli_kind="claude",
            default_model="sonnet",
        )
        updated = store.update(created.id, display_name="New Name")
        assert updated.display_name == "New Name"
        assert updated.prompt == "Prompt."
        assert updated.cli_kind == "claude"
        assert updated.default_model == "sonnet"

    def test_delete_removes_custom_template(self, db_path: Path) -> None:
        store = RoleTemplateStore(db_path)
        created = store.create(
            slug="deletable",
            display_name="Deletable",
            prompt="...",
            cli_kind="claude",
            default_model="sonnet",
        )
        store.delete(created.id)
        with pytest.raises(KeyError):
            store.get(created.id)

    def test_delete_predefined_architect_raises_value_error(
        self, db_path: Path
    ) -> None:
        store = RoleTemplateStore(db_path)
        architect = store.get_by_slug("architect")
        assert architect is not None
        with pytest.raises(ValueError, match="cannot delete predefined role template"):
            store.delete(architect.id)

    def test_delete_predefined_review_raises_value_error(
        self, db_path: Path
    ) -> None:
        store = RoleTemplateStore(db_path)
        review = store.get_by_slug("review")
        assert review is not None
        with pytest.raises(ValueError, match="cannot delete predefined role template"):
            store.delete(review.id)

    def test_delete_predefined_execute_raises_value_error(
        self, db_path: Path
    ) -> None:
        store = RoleTemplateStore(db_path)
        execute = store.get_by_slug("execute")
        assert execute is not None
        with pytest.raises(ValueError, match="cannot delete predefined role template"):
            store.delete(execute.id)

    def test_seeding_is_idempotent_across_multiple_instances(
        self, db_path: Path
    ) -> None:
        """Multiple RoleTemplateStore instances must not duplicate predefined rows."""
        RoleTemplateStore(db_path)
        RoleTemplateStore(db_path)
        store = RoleTemplateStore(db_path)
        predefined = [t for t in store.list_all() if t.predefined]
        slugs = [t.slug for t in predefined]
        assert slugs.count("architect") == 1
        assert slugs.count("review") == 1
        assert slugs.count("execute") == 1

    def test_predefined_templates_match_expected_count(
        self, db_path: Path
    ) -> None:
        """Exactly three predefined templates should exist after init."""
        store = RoleTemplateStore(db_path)
        predefined = [t for t in store.list_all() if t.predefined]
        assert len(predefined) == len(_PREDEFINED_TEMPLATES)
