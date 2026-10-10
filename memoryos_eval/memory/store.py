"""Public composition root for MemoryOS Lite's SQLite authority.

The implementation is split by persistence responsibility.  This module keeps
the established imports and concrete ``MemoryStore`` entry point stable.
"""

from memoryos_eval.memory.store_archive import ArchiveStoreMixin
from memoryos_eval.memory.store_curator import CuratorStoreMixin
from memoryos_eval.memory.store_legacy import LegacyStoreMixin
from memoryos_eval.memory.store_models import EMBEDDING_DIM as EMBEDDING_DIM
from memoryos_eval.memory.store_models import (
    ArchivalChunkRecord as ArchivalChunkRecord,
)
from memoryos_eval.memory.store_models import (
    ArchivalDocumentRecord as ArchivalDocumentRecord,
)
from memoryos_eval.memory.store_models import (
    ArchivalPassageRecord as ArchivalPassageRecord,
)
from memoryos_eval.memory.store_models import (
    ArchiveAttachmentRecord as ArchiveAttachmentRecord,
)
from memoryos_eval.memory.store_models import (
    Base as Base,
)
from memoryos_eval.memory.store_models import (
    CuratedMemoryRecord as CuratedMemoryRecord,
)
from memoryos_eval.memory.store_models import (
    CuratorStateRecord as CuratorStateRecord,
)
from memoryos_eval.memory.store_models import (
    EmbeddingType as EmbeddingType,
)
from memoryos_eval.memory.store_models import (
    EpisodeRecord as EpisodeRecord,
)
from memoryos_eval.memory.store_models import (
    MessageRecord as MessageRecord,
)
from memoryos_eval.memory.store_models import (
    SessionRecord as SessionRecord,
)
from memoryos_eval.memory.store_models import (
    TraceRecord as TraceRecord,
)
from memoryos_eval.memory.store_runtime import StoreRuntimeMixin
from memoryos_eval.memory.store_sessions import SessionStoreMixin
from memoryos_lite.config import Settings


class MemoryStore(
    StoreRuntimeMixin,
    SessionStoreMixin,
    ArchiveStoreMixin,
    CuratorStoreMixin,
    LegacyStoreMixin,
):
    """Concrete, backward-compatible composition of persistence slices."""


def create_store(settings: Settings | None = None) -> MemoryStore:
    store = MemoryStore(settings)
    store.init_db()
    return store
