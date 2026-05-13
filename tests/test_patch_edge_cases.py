from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import MemoryPage, MemoryPatch, PatchOperation
from memoryos_lite.store import EMBEDDING_DIM, create_store


class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        value = float(len(text) % 10) / 10.0
        return [value] * EMBEDDING_DIM


class TestPatchEdgeCases:
    def _setup(self, tmp_path):
        settings = Settings(data_dir=tmp_path / ".memoryos")
        store = create_store(settings)
        store.reset()
        service = MemoryOSService(
            settings=settings,
            store=store,
            embedding_client=FakeEmbedder(),
        )
        session = service.create_session("test_patch_edges")
        return service, session

    def _save_page(
        self,
        service: MemoryOSService,
        session_id: str,
        *,
        title: str = "Patch Target",
        summary: str = "summary text",
        facts: list[str] | None = None,
        decisions: list[str] | None = None,
        open_questions: list[str] | None = None,
    ) -> MemoryPage:
        page = MemoryPage(
            session_id=session_id,
            title=title,
            summary=summary,
            facts=facts or [],
            decisions=decisions or [],
            open_questions=open_questions or [],
        )
        return service.store.save_page(page)

    def test_replace_rejects_empty_old_text(self, tmp_path):
        service, session = self._setup(tmp_path)
        page = self._save_page(service, session.id, summary="replace target")
        patch = MemoryPatch(
            operation=PatchOperation.REPLACE,
            target_page_id=page.id,
            old_text="",
            new_text="replacement",
            reason="empty old_text",
        )

        verified = service.commit_patch(session.id, patch)

        assert verified.verified is False
        assert any("old_text is required" in error for error in verified.errors)

    def test_delete_rejects_empty_old_text(self, tmp_path):
        service, session = self._setup(tmp_path)
        page = self._save_page(service, session.id, summary="delete target")
        patch = MemoryPatch(
            operation=PatchOperation.DELETE,
            target_page_id=page.id,
            old_text="",
            reason="empty old_text",
        )

        verified = service.commit_patch(session.id, patch)

        assert verified.verified is False
        assert any("old_text is required" in error for error in verified.errors)

    def test_add_rejects_missing_target_page(self, tmp_path):
        service, session = self._setup(tmp_path)
        patch = MemoryPatch(
            operation=PatchOperation.ADD,
            target_page_id="page_does_not_exist",
            new_text="new fact",
            reason="missing target",
        )

        verified = service.commit_patch(session.id, patch)

        assert verified.verified is False
        assert any("target page is required" in error for error in verified.errors)

    def test_add_rejects_empty_new_text(self, tmp_path):
        service, session = self._setup(tmp_path)
        page = self._save_page(service, session.id, summary="append target")
        patch = MemoryPatch(
            operation=PatchOperation.ADD,
            target_page_id=page.id,
            new_text="",
            reason="empty add",
        )

        verified = service.commit_patch(session.id, patch)

        assert verified.verified is False
        assert any("new_text is required" in error for error in verified.errors)

    def test_commit_patch_rejects_cross_session_page(self, tmp_path):
        service, session_a = self._setup(tmp_path)
        session_b = service.create_session("other_session")
        page = self._save_page(service, session_a.id, summary="session A page")
        patch = MemoryPatch(
            operation=PatchOperation.ADD,
            target_page_id=page.id,
            new_text="new fact from session B",
            reason="cross session",
        )

        verified = service.commit_patch(session_b.id, patch)

        assert verified.verified is False
        assert any("different session" in error for error in verified.errors)

    def test_replace_ignores_old_text_that_only_exists_in_title(self, tmp_path):
        service, session = self._setup(tmp_path)
        page = self._save_page(
            service,
            session.id,
            title="UNIQUE_TITLE",
            summary="summary without the token",
            facts=["fact without the token"],
            decisions=["decision without the token"],
            open_questions=["question without the token"],
        )
        patch = MemoryPatch(
            operation=PatchOperation.REPLACE,
            target_page_id=page.id,
            old_text="UNIQUE_TITLE",
            new_text="NEW_TITLE",
            reason="title is not modifiable by patches",
        )

        verified = service.commit_patch(session.id, patch)

        assert verified.verified is False

    def test_apply_patch_replaces_decisions(self, tmp_path):
        service, session = self._setup(tmp_path)
        page = self._save_page(
            service,
            session.id,
            decisions=["use postgres"],
        )
        patch = MemoryPatch(
            operation=PatchOperation.REPLACE,
            target_page_id=page.id,
            old_text="use postgres",
            new_text="use sqlite",
            reason="change storage decision",
        )

        verified = service.commit_patch(session.id, patch)
        applied = service.apply_patch(session.id, verified)
        updated = service.store.load_page(page.id)

        assert verified.verified is True
        assert applied is True
        assert updated is not None
        assert updated.decisions == ["use sqlite"]

    def test_apply_patch_returns_false_when_target_page_is_missing(self, tmp_path):
        service, session = self._setup(tmp_path)
        patch = MemoryPatch(
            operation=PatchOperation.ADD,
            target_page_id="page_does_not_exist",
            new_text="new fact",
            reason="missing target",
            verified=True,
        )

        assert service.apply_patch(session.id, patch) is False

    def test_apply_patch_returns_false_for_unverified_patch(self, tmp_path):
        service, session = self._setup(tmp_path)
        page = self._save_page(
            service,
            session.id,
            summary="original summary",
            facts=["original fact"],
        )
        patch = MemoryPatch(
            operation=PatchOperation.REPLACE,
            target_page_id=page.id,
            old_text="original fact",
            new_text="mutated fact",
            reason="bypass verifier",
            verified=False,
        )

        applied = service.apply_patch(session.id, patch)
        updated = service.store.load_page(page.id)

        assert applied is False
        assert updated is not None
        assert updated.facts == ["original fact"]
