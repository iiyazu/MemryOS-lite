from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import (
    ArchivalChunk,
    ArchivalDocument,
    ArchivalPassage,
    SourceRef,
    SourceSpan,
)


@dataclass(frozen=True)
class ArchiveRAGIngestRequest:
    document_id: str
    archive_id: str | None
    title: str
    content: str | bytes
    source_refs: list[SourceRef]
    source_id: str | None = None
    file_id: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    producer: str = "explicit_document"


@dataclass(frozen=True)
class ArchiveParsedDocument:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArchiveTextSpan:
    text: str
    start: int
    end: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArchiveRAGDiagnostic:
    event_type: str
    reason_code: str
    item_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArchiveRAGIngestResult:
    document: ArchivalDocument
    chunks: list[ArchivalChunk] = field(default_factory=list)
    passages: list[ArchivalPassage] = field(default_factory=list)
    diagnostics: list[ArchiveRAGDiagnostic] = field(default_factory=list)


class ArchiveDocumentParser(Protocol):
    def parse(self, request: ArchiveRAGIngestRequest) -> ArchiveParsedDocument: ...


class ArchiveTextSplitter(Protocol):
    def split(self, document: ArchiveParsedDocument) -> list[ArchiveTextSpan]: ...


class ArchivePassageIndexer(Protocol):
    def index_passages(
        self,
        passages: list[ArchivalPassage],
    ) -> list[ArchiveRAGDiagnostic]: ...


class PlainTextArchiveParser:
    def parse(self, request: ArchiveRAGIngestRequest) -> ArchiveParsedDocument:
        content = request.content
        if isinstance(content, bytes):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("archive parser requires UTF-8 bytes") from exc
        else:
            text = content
        return ArchiveParsedDocument(text=text, metadata={"parser": "plain_text"})


class FixedWindowArchiveSplitter:
    def __init__(self, *, max_chars: int = 1200, overlap_chars: int = 0) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be greater than zero")
        if overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be non-negative and smaller than max_chars")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def split(self, document: ArchiveParsedDocument) -> list[ArchiveTextSpan]:
        if not document.text:
            return []
        spans: list[ArchiveTextSpan] = []
        start = 0
        while start < len(document.text):
            end = min(len(document.text), start + self.max_chars)
            spans.append(
                ArchiveTextSpan(
                    text=document.text[start:end],
                    start=start,
                    end=end,
                    metadata={"splitter": "fixed_window"},
                )
            )
            if end == len(document.text):
                break
            start = end - self.overlap_chars
        return spans


class MemoryOSArchiveRAG:
    """MemoryOS-owned archive ingestion boundary for external RAG components."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        parser: ArchiveDocumentParser | None = None,
        splitter: ArchiveTextSplitter | None = None,
        indexer: ArchivePassageIndexer | None = None,
    ) -> None:
        self.store = store
        self.parser = parser or PlainTextArchiveParser()
        self.splitter = splitter or FixedWindowArchiveSplitter()
        self.indexer = indexer

    def ingest(self, request: ArchiveRAGIngestRequest) -> ArchiveRAGIngestResult:
        if not request.source_refs:
            raise ValueError("archive RAG ingest requires source_refs")
        parsed = self.parser.parse(request)
        spans = self.splitter.split(parsed)
        self._validate_spans(parsed.text, spans)
        document = self._document(request, parsed)
        chunks = [
            self._chunk(request, span, index)
            for index, span in enumerate(spans)
        ]
        passages = [
            self._passage(request, chunk, span, index)
            for index, (chunk, span) in enumerate(zip(chunks, spans, strict=True))
        ]

        document = self.store.create_archival_document(document)
        chunks = [self.store.create_archival_chunk(chunk) for chunk in chunks]
        passages = [
            self.store.create_archival_passage(passage) for passage in passages
        ]
        diagnostics: list[ArchiveRAGDiagnostic] = []
        if self.indexer is not None and passages:
            try:
                diagnostics.extend(self.indexer.index_passages(passages))
            except Exception as exc:
                diagnostics.append(
                    ArchiveRAGDiagnostic(
                        event_type="archive_index_unavailable",
                        reason_code="indexer_error",
                        metadata={"error": str(exc)},
                    )
                )
        return ArchiveRAGIngestResult(
            document=document,
            chunks=chunks,
            passages=passages,
            diagnostics=diagnostics,
        )

    def _document(
        self,
        request: ArchiveRAGIngestRequest,
        parsed: ArchiveParsedDocument,
    ) -> ArchivalDocument:
        metadata = dict(request.metadata)
        if parsed.metadata:
            metadata["parser_metadata"] = dict(parsed.metadata)
        return ArchivalDocument(
            id=request.document_id,
            archive_id=request.archive_id,
            title=request.title,
            text=parsed.text,
            source_id=request.source_id,
            file_id=request.file_id,
            tags=list(request.tags),
            source_refs=list(request.source_refs),
            producer=request.producer,
            metadata=metadata,
        )

    def _chunk(
        self,
        request: ArchiveRAGIngestRequest,
        span: ArchiveTextSpan,
        index: int,
    ) -> ArchivalChunk:
        return ArchivalChunk(
            id=self._chunk_id(request.document_id, index),
            document_id=request.document_id,
            archive_id=request.archive_id,
            text=span.text,
            start=span.start,
            end=span.end,
            tags=list(request.tags),
            source_refs=list(request.source_refs),
            metadata={"splitter_metadata": dict(span.metadata)},
        )

    def _passage(
        self,
        request: ArchiveRAGIngestRequest,
        chunk: ArchivalChunk,
        span: ArchiveTextSpan,
        index: int,
    ) -> ArchivalPassage:
        return ArchivalPassage(
            id=self._passage_id(request.document_id, index),
            document_id=request.document_id,
            chunk_id=chunk.id,
            archive_id=request.archive_id,
            text=span.text,
            citation=SourceSpan(start=span.start, end=span.end),
            source_id=None if request.archive_id else request.source_id,
            file_id=None if request.archive_id else request.file_id,
            tags=list(request.tags),
            source_refs=list(request.source_refs),
            metadata={
                "producer": request.producer,
                "splitter_metadata": dict(span.metadata),
            },
        )

    @staticmethod
    def _validate_spans(document_text: str, spans: list[ArchiveTextSpan]) -> None:
        for span in spans:
            if span.start < 0 or span.end < span.start or span.end > len(document_text):
                raise ValueError("splitter span range is outside document text")
            if document_text[span.start:span.end] != span.text:
                raise ValueError("splitter span text must match document text")

    @staticmethod
    def _chunk_id(document_id: str, index: int) -> str:
        return f"achunk_{document_id}_{index:04d}"

    @staticmethod
    def _passage_id(document_id: str, index: int) -> str:
        return f"apsg_{document_id}_{index:04d}"
