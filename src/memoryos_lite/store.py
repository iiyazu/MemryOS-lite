"""Public composition root for MemoryOS Lite's SQLite authority.

The implementation is split by persistence responsibility.  This module keeps
the established imports and concrete ``MemoryStore`` entry point stable.
"""

from memoryos_lite.config import Settings
from memoryos_lite.store_archive import ArchiveStoreMixin
from memoryos_lite.store_legacy import LegacyStoreMixin
from memoryos_lite.store_models import EMBEDDING_DIM as EMBEDDING_DIM
from memoryos_lite.store_models import (
    ArchivalChunkRecord as ArchivalChunkRecord,
)
from memoryos_lite.store_models import (
    ArchivalDocumentRecord as ArchivalDocumentRecord,
)
from memoryos_lite.store_models import (
    ArchivalMemoryHistoryRecord as ArchivalMemoryHistoryRecord,
)
from memoryos_lite.store_models import (
    ArchivalMemoryRecord as ArchivalMemoryRecord,
)
from memoryos_lite.store_models import (
    ArchivalPassagePage as ArchivalPassagePage,
)
from memoryos_lite.store_models import (
    ArchivalPassageRecord as ArchivalPassageRecord,
)
from memoryos_lite.store_models import (
    ArchiveAttachmentRecord as ArchiveAttachmentRecord,
)
from memoryos_lite.store_models import (
    Base as Base,
)
from memoryos_lite.store_models import (
    ContextPolicyCandidateRecord as ContextPolicyCandidateRecord,
)
from memoryos_lite.store_models import (
    CoreMemoryBlockRecord as CoreMemoryBlockRecord,
)
from memoryos_lite.store_models import (
    CoreMemoryHistoryRecord as CoreMemoryHistoryRecord,
)
from memoryos_lite.store_models import (
    EmbeddingType as EmbeddingType,
)
from memoryos_lite.store_models import (
    EpisodeRecord as EpisodeRecord,
)
from memoryos_lite.store_models import (
    ItemRecord as ItemRecord,
)
from memoryos_lite.store_models import (
    MaintenanceAdvisoryRecord as MaintenanceAdvisoryRecord,
)
from memoryos_lite.store_models import (
    MessageRecord as MessageRecord,
)
from memoryos_lite.store_models import (
    PageRecord as PageRecord,
)
from memoryos_lite.store_models import (
    PatchRecord as PatchRecord,
)
from memoryos_lite.store_models import (
    PromotionCandidateRecord as PromotionCandidateRecord,
)
from memoryos_lite.store_models import (
    SessionRecord as SessionRecord,
)
from memoryos_lite.store_models import (
    TraceRecord as TraceRecord,
)
from memoryos_lite.store_runtime import StoreRuntimeMixin
from memoryos_lite.store_sessions import SessionStoreMixin


class MemoryStore(
    StoreRuntimeMixin,
    SessionStoreMixin,
    ArchiveStoreMixin,
    LegacyStoreMixin,
):
    """Concrete, backward-compatible composition of persistence slices."""


def create_store(settings: Settings | None = None) -> MemoryStore:
    store = MemoryStore(settings)
    store.init_db()
    return store
