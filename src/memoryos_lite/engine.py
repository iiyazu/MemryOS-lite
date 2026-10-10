from __future__ import annotations

import logging
from importlib.util import find_spec

from memoryos_lite.config import Settings, get_settings
from memoryos_lite.curator import CuratorLLM, build_curator_llm
from memoryos_lite.curator.curate import CurateRequest, CurateResponse
from memoryos_lite.observability import log_event, timed_core_operation
from memoryos_lite.recall import (
    Recaller,
    RecallRequest,
    RecallResponse,
    SimilarRequest,
    SimilarResponse,
)
from memoryos_lite.retrieval import EmbeddingClient
from memoryos_lite.tokenizer import TokenEstimator

__all__ = ["CurateUnavailableError", "MemoryOSService"]

logger = logging.getLogger(__name__)


class CurateUnavailableError(RuntimeError):
    """``/curate`` cannot run here; ``args[0]`` is a stable reason code."""

    @property
    def reason_code(self) -> str:
        return str(self.args[0])


class MemoryOSService:
    """The stateless service behind the HTTP API: ``/curate``, ``/recall``, ``/similar``.

    It keeps no state between requests and opens no database. The in-process
    session store the evaluations measure lives in ``memoryos_eval``.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        embedding_client: EmbeddingClient | None = None,
        curate_llm: CuratorLLM | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._curate_llm = curate_llm
        self._recaller: Recaller | None = None
        self.tokenizer = TokenEstimator()
        self.embedding_client = embedding_client or self._default_embedding_client()

    def _default_embedding_client(self) -> EmbeddingClient | None:
        provider = self.settings.memoryos_embedding_provider.strip().lower()
        if provider == "fastembed":
            try:
                from memoryos_lite.retrieval.providers.fastembed_client import (
                    FastEmbedClient,
                )

                return FastEmbedClient()
            except Exception:
                return None
        return None

    def _json_llm(self) -> CuratorLLM:
        """The JSON-mode LLM for ``/curate``, built on first use."""

        llm = self._curate_llm
        if llm is None:
            if not self.settings.chat_api_key:
                raise CurateUnavailableError("curator_llm_key_missing")
            try:
                llm = build_curator_llm(self.settings)
            except Exception as exc:
                raise CurateUnavailableError("curator_llm_init_error") from exc
            self._curate_llm = llm
        if llm is None:
            raise CurateUnavailableError("curator_llm_key_missing")
        return llm

    def curate(self, request: CurateRequest) -> CurateResponse:
        """Stateless module curation (``POST /curate``); see ``curator.curate``.

        Raises :class:`CurateUnavailableError` when no LLM or no LangGraph runtime
        is available, and lets :class:`CuratorLLMError` through on provider errors.
        """

        llm = self._json_llm()
        try:
            from memoryos_lite.curator.graph import run_curate
        except ImportError as exc:
            raise CurateUnavailableError("curate_requires_langgraph") from exc
        with timed_core_operation(component="engine", operation="curate", logger=logger):
            response = run_curate(request, llm)
        log_event(
            logger,
            logging.INFO,
            "curate_completed",
            scope_id=request.scope_id,
            window=len(request.window),
            memories=len(response.memories),
            unaccounted=len(response.unaccounted),
            repairs=response.diagnostics.repairs,
        )
        return response

    @property
    def recaller(self) -> Recaller:
        if self._recaller is None:
            self._recaller = Recaller(self.tokenizer, self.embedding_client)
        return self._recaller

    def recall(self, request: RecallRequest) -> RecallResponse:
        """Stateless, deterministic ranking (``POST /recall``); see ``recall``."""

        with timed_core_operation(component="engine", operation="recall", logger=logger):
            return self.recaller.recall(request)

    def similar(self, request: SimilarRequest) -> SimilarResponse:
        """Near-duplicate pairs (``POST /similar``); raises ``SimilarUnavailableError``."""

        with timed_core_operation(component="engine", operation="similar", logger=logger):
            return self.recaller.similar(request)

    def curate_ready(self) -> bool:
        """Whether ``/curate`` can run: an LLM (or its key) and the LangGraph runtime."""

        has_llm = self._curate_llm is not None or bool(self.settings.chat_api_key)
        return has_llm and find_spec("langgraph") is not None
