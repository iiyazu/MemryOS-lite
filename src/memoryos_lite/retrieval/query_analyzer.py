from dataclasses import dataclass
from enum import StrEnum


class QueryKind(StrEnum):
    TEMPORAL = "temporal"
    ASSISTANT_SOURCE = "assistant_source"
    MULTI_SESSION = "multi_session"
    GENERAL = "general"


@dataclass(frozen=True)
class QueryAnalysis:
    kind: QueryKind


class QueryAnalyzer:
    def analyze(self, query: str) -> QueryAnalysis:
        normalized = query.lower()
        if any(
            marker in normalized
            for marker in ("last time", "you recommend", "you suggested", "you said")
        ):
            return QueryAnalysis(QueryKind.ASSISTANT_SOURCE)
        if any(
            marker in normalized
            for marker in ("before", "after", "first", "how many days", "when")
        ):
            return QueryAnalysis(QueryKind.TEMPORAL)
        if any(marker in normalized for marker in ("session", "conversation", "chat")):
            return QueryAnalysis(QueryKind.MULTI_SESSION)
        return QueryAnalysis(QueryKind.GENERAL)
