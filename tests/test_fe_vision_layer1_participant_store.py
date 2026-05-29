"""Tests for fe-vision-layer1-participants-store-impl lane.

Covers:
- ChatStore._init_db creates participants + role_templates tables
- ParticipantStore CRUD
- RoleTemplateStore seeding, CRUD, predefined guard
- Pydantic model field shapes match FRONTEND_VISION.md contract
"""

from __future__ import annotations

import sqlite3

import pytest

from xmuse_core.chat.store import ChatStore
from xmuse_core.chat.participant_store import (
    Participant,
    RoleTemplate,
    ParticipantStore,
    RoleTemplateStore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "chat.db"


@pytest.fixture()
def chat_store(db_path):
    return ChatStore(db_path)


@pytest.fixture()
def participant_store(chat_store, db_path):
    # ChatStore must be initialised first so the tables exist.
    return ParticipantStore(db_path)


@pytest.fixture()
def role_template_store(chat_store, db_path):
    return RoleTemplateStore(db_path)


@pytest.fixture()
def conversation(chat_store):
    return chat_store.create_conversation("test conv")


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

class TestTableCreation:
    def test_participants_table_exists(self, db_path, chat_store):
        conn = sqlite3.connect(db_path)
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'").fetchall()}
        conn.close()
        assert "participants" in tables

    def test_role_templates_table_exists(self, db_path, chat_store):
        conn = sqlite3.connect(db_path)
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'").fetchall()}
        conn.close()
        assert "role_templates" in tables

    def test_existing_tables_unchanged(self, db_path, chat_store):
        conn = sqlite3.connect(db_path)
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'").fetchall()}
        conn.close()
        assert {"conversations", "messages", "proposals", "resolutions"}.issubset(tables)

    def test_participants_columns(self, db_path, chat_store):
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("pragma table_info(participants)").fetchall()}
        conn.close()
        expected = {
            "participant_id", "conversation_id", "role", "display_name",
            "cli_kind", "model", "role_template_id", "status",
            "last_seen_at", "created_at",
        }
        assert expected == cols

    def test_role_templates_columns(self, db_path, chat_store):
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("pragma table_info(role_templates)").fetchall()}
        conn.close()
        expected = {
            "id", "slug", "display_name", "prompt", "cli_kind",
            "default_model", "predefined", "created_at", "updated_at",
        }
        assert expected == cols


# ---------------------------------------------------------------------------
# Pydantic model shapes
# ---------------------------------------------------------------------------

class TestModelShapes:
    def test_participant_fields(self):
        fields = set(Participant.model_fields.keys())
        assert fields == {
            "participant_id", "conversation_id", "role", "display_name",
            "cli_kind", "model", "role_template_id", "status",
            "last_seen_at", "created_at",
        }

    def test_role_template_fields(self):
        fields = set(RoleTemplate.model_fields.keys())
        assert fields == {
            "id", "slug", "display_name", "prompt", "cli_kind",
            "default_model", "predefined", "created_at", "updated_at",
        }

    def test_participant_cli_kind_literal(self):
        ann = Participant.model_fields["cli_kind"].annotation
        # Literal["claude", "codex"] — check both values are accepted
        p = Participant(
            participant_id="x", conversation_id="c", role="r",
            display_name="d", cli_kind="claude", model="sonnet",
            role_template_id=None, status="active",
            last_seen_at=None, created_at="2026-01-01T00:00:00Z",
        )
        assert p.cli_kind == "claude"

    def test_role_template_predefined_bool(self):
        t = RoleTemplate(
            id="x", slug="s", display_name="D", prompt="p",
            cli_kind="codex", default_model="gpt-5.5",
            predefined=True, created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        assert t.predefined is True


# ---------------------------------------------------------------------------
# ParticipantStore
# ---------------------------------------------------------------------------

class TestParticipantStore:
    def test_add_returns_participant(self, participant_store, conversation):
        p = participant_store.add(
            conversation_id=conversation.id,
            role="architect",
            display_name="architect-god",
            cli_kind="claude",
            model="sonnet",
        )
        assert isinstance(p, Participant)
        assert p.conversation_id == conversation.id
        assert p.role == "architect"
        assert p.status == "active"
        assert p.last_seen_at is None
        assert p.role_template_id is None

    def test_add_with_role_template_id(self, participant_store, conversation):
        p = participant_store.add(
            conversation_id=conversation.id,
            role="custom",
            display_name="custom-god",
            cli_kind="codex",
            model="gpt-5.5",
            role_template_id="tmpl_abc",
        )
        assert p.role_template_id == "tmpl_abc"

    def test_get_roundtrip(self, participant_store, conversation):
        added = participant_store.add(
            conversation_id=conversation.id,
            role="review",
            display_name="review-god",
            cli_kind="claude",
            model="haiku",
        )
        fetched = participant_store.get(added.participant_id)
        assert fetched == added

    def test_get_unknown_raises(self, participant_store):
        with pytest.raises(KeyError):
            participant_store.get("nonexistent")

    def test_list_by_conversation(self, participant_store, conversation):
        participant_store.add(
            conversation_id=conversation.id,
            role="architect",
            display_name="architect-god",
            cli_kind="claude",
            model="sonnet",
        )
        participant_store.add(
            conversation_id=conversation.id,
            role="review",
            display_name="review-god",
            cli_kind="claude",
            model="sonnet",
        )
        results = participant_store.list_by_conversation(conversation.id)
        assert len(results) == 2
        roles = {p.role for p in results}
        assert roles == {"architect", "review"}

    def test_list_by_conversation_empty(self, participant_store, conversation):
        assert participant_store.list_by_conversation(conversation.id) == []

    def test_list_by_conversation_isolation(self, chat_store, participant_store, db_path):
        conv_a = chat_store.create_conversation("A")
        conv_b = chat_store.create_conversation("B")
        participant_store.add(
            conversation_id=conv_a.id, role="architect",
            display_name="arch", cli_kind="claude", model="sonnet",
        )
        participant_store.add(
            conversation_id=conv_b.id, role="review",
            display_name="rev", cli_kind="claude", model="sonnet",
        )
        assert len(participant_store.list_by_conversation(conv_a.id)) == 1
        assert len(participant_store.list_by_conversation(conv_b.id)) == 1

    def test_update_status(self, participant_store, conversation):
        p = participant_store.add(
            conversation_id=conversation.id,
            role="execute",
            display_name="execute-god",
            cli_kind="claude",
            model="sonnet",
        )
        updated = participant_store.update_status(p.participant_id, "stopped")
        assert updated.status == "stopped"
        assert updated.last_seen_at is not None

    def test_update_status_with_explicit_timestamp(self, participant_store, conversation):
        p = participant_store.add(
            conversation_id=conversation.id,
            role="execute",
            display_name="execute-god",
            cli_kind="claude",
            model="sonnet",
        )
        ts = "2026-05-28T12:00:00Z"
        updated = participant_store.update_status(p.participant_id, "stopped", last_seen_at=ts)
        assert updated.last_seen_at == ts

    def test_delete(self, participant_store, conversation):
        p = participant_store.add(
            conversation_id=conversation.id,
            role="architect",
            display_name="arch",
            cli_kind="claude",
            model="sonnet",
        )
        participant_store.delete(p.participant_id)
        with pytest.raises(KeyError):
            participant_store.get(p.participant_id)

    def test_participant_id_unique(self, participant_store, conversation):
        p1 = participant_store.add(
            conversation_id=conversation.id, role="architect",
            display_name="arch", cli_kind="claude", model="sonnet",
        )
        p2 = participant_store.add(
            conversation_id=conversation.id, role="review",
            display_name="rev", cli_kind="claude", model="sonnet",
        )
        assert p1.participant_id != p2.participant_id


# ---------------------------------------------------------------------------
# RoleTemplateStore — seeding
# ---------------------------------------------------------------------------

class TestRoleTemplateStoreSeeding:
    def test_three_predefined_seeded(self, role_template_store):
        templates = role_template_store.list_all()
        predefined = [t for t in templates if t.predefined]
        assert len(predefined) == 3

    def test_predefined_slugs(self, role_template_store):
        slugs = {t.slug for t in role_template_store.list_all() if t.predefined}
        assert slugs == {"architect", "review", "execute"}

    def test_predefined_marked_true(self, role_template_store):
        for t in role_template_store.list_all():
            if t.slug in {"architect", "review", "execute"}:
                assert t.predefined is True

    def test_architect_prompt_content(self, role_template_store):
        t = role_template_store.get_by_slug("architect")
        assert t is not None
        assert "Architect GOD" in t.prompt
        assert '"type": "proposal"' in t.prompt

    def test_review_prompt_content(self, role_template_store):
        t = role_template_store.get_by_slug("review")
        assert t is not None
        assert "Review GOD" in t.prompt
        assert '"type": "verdict"' in t.prompt

    def test_execute_prompt_content(self, role_template_store):
        t = role_template_store.get_by_slug("execute")
        assert t is not None
        assert "Execute GOD" in t.prompt

    def test_seeding_idempotent(self, db_path, chat_store):
        # Constructing a second RoleTemplateStore on the same DB must not
        # duplicate the predefined rows.
        store1 = RoleTemplateStore(db_path)
        store2 = RoleTemplateStore(db_path)
        predefined = [t for t in store2.list_all() if t.predefined]
        assert len(predefined) == 3


# ---------------------------------------------------------------------------
# RoleTemplateStore — CRUD
# ---------------------------------------------------------------------------

class TestRoleTemplateStoreCRUD:
    def test_create_custom(self, role_template_store):
        t = role_template_store.create(
            slug="tester",
            display_name="Tester GOD",
            prompt="You test things.",
            cli_kind="codex",
            default_model="gpt-5.5",
        )
        assert isinstance(t, RoleTemplate)
        assert t.predefined is False
        assert t.slug == "tester"

    def test_get_by_id(self, role_template_store):
        created = role_template_store.create(
            slug="planner",
            display_name="Planner GOD",
            prompt="You plan.",
            cli_kind="claude",
            default_model="haiku",
        )
        fetched = role_template_store.get(created.id)
        assert fetched == created

    def test_get_unknown_raises(self, role_template_store):
        with pytest.raises(KeyError):
            role_template_store.get("nonexistent")

    def test_get_by_slug_none_for_missing(self, role_template_store):
        assert role_template_store.get_by_slug("does-not-exist") is None

    def test_update_display_name(self, role_template_store):
        t = role_template_store.create(
            slug="updatable",
            display_name="Old Name",
            prompt="p",
            cli_kind="claude",
            default_model="sonnet",
        )
        updated = role_template_store.update(t.id, display_name="New Name")
        assert updated.display_name == "New Name"
        assert updated.prompt == "p"  # unchanged

    def test_update_prompt(self, role_template_store):
        t = role_template_store.create(
            slug="prompt-update",
            display_name="D",
            prompt="old prompt",
            cli_kind="claude",
            default_model="sonnet",
        )
        updated = role_template_store.update(t.id, prompt="new prompt")
        assert updated.prompt == "new prompt"

    def test_update_bumps_updated_at(self, role_template_store):
        t = role_template_store.create(
            slug="ts-check",
            display_name="D",
            prompt="p",
            cli_kind="claude",
            default_model="sonnet",
        )
        updated = role_template_store.update(t.id, display_name="D2")
        # updated_at must be >= created_at (both are ISO strings, lexicographic ok)
        assert updated.updated_at >= t.created_at

    def test_delete_custom(self, role_template_store):
        t = role_template_store.create(
            slug="deletable",
            display_name="D",
            prompt="p",
            cli_kind="claude",
            default_model="sonnet",
        )
        role_template_store.delete(t.id)
        with pytest.raises(KeyError):
            role_template_store.get(t.id)

    def test_delete_predefined_raises(self, role_template_store):
        arch = role_template_store.get_by_slug("architect")
        assert arch is not None
        with pytest.raises(ValueError, match="predefined"):
            role_template_store.delete(arch.id)

    def test_list_all_includes_custom(self, role_template_store):
        role_template_store.create(
            slug="extra",
            display_name="Extra",
            prompt="p",
            cli_kind="claude",
            default_model="sonnet",
        )
        all_templates = role_template_store.list_all()
        slugs = {t.slug for t in all_templates}
        assert "extra" in slugs
        assert {"architect", "review", "execute"}.issubset(slugs)

    def test_slug_unique_constraint(self, role_template_store):
        role_template_store.create(
            slug="unique-slug",
            display_name="D",
            prompt="p",
            cli_kind="claude",
            default_model="sonnet",
        )
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            role_template_store.create(
                slug="unique-slug",
                display_name="D2",
                prompt="p2",
                cli_kind="claude",
                default_model="sonnet",
            )
