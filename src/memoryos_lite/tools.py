"""LangChain tool definitions for the Agentic Memory Manager.

These tools allow a LangGraph agent to interact with the memory store:
search, read, write, patch, and list memory pages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import tool

if TYPE_CHECKING:
    from memoryos_lite.engine import MemoryOSService


def create_memory_tools(service: MemoryOSService, session_id: str):
    """Create bound memory tools for a specific session."""

    @tool
    def search_memory(query: str, top_k: int = 5) -> str:
        """Search memory pages by semantic relevance to the query.

        Args:
            query: Natural language search query.
            top_k: Maximum number of results to return.

        Returns:
            Formatted search results with page titles and summaries.
        """
        hits = service.search(query, top_k=top_k, session_id=session_id)
        if not hits:
            return "No relevant memory pages found."
        lines = []
        for hit in hits:
            lines.append(
                f"- [{hit.page.id}] {hit.page.title} (score={hit.score:.3f})\n"
                f"  Summary: {hit.page.summary[:150]}"
            )
        return "\n".join(lines)

    @tool
    def read_page(page_id: str) -> str:
        """Read the full content of a memory page by its ID.

        Args:
            page_id: The unique identifier of the page to read.

        Returns:
            Full page content including title, summary, facts, and metadata.
        """
        page = service.store.load_page(page_id)
        if page is None:
            return f"Page {page_id} not found."
        if page.session_id != session_id:
            return f"Page {page_id} belongs to a different session and cannot be read."
        facts_str = "\n".join(f"  - {f}" for f in page.facts) if page.facts else "  (none)"
        return (
            f"Title: {page.title}\n"
            f"Type: {page.page_type.value}\n"
            f"Summary: {page.summary}\n"
            f"Facts:\n{facts_str}\n"
            f"Confidence: {page.confidence:.0%}\n"
            f"Version: {page.version}\n"
            f"Updated: {page.updated_at.isoformat()}"
        )

    @tool
    def write_page(title: str, summary: str, facts: list[str]) -> str:
        """Create a new memory page with the given content.

        Args:
            title: Short descriptive title for the page.
            summary: Concise summary of the information.
            facts: List of discrete facts extracted from the content.

        Returns:
            Confirmation with the new page ID.
        """
        from memoryos_lite.schemas import MemoryPage, PageType

        page = MemoryPage(
            session_id=session_id,
            page_type=PageType.SOURCE_SUMMARY,
            title=title,
            summary=summary,
            facts=facts,
            version=1,
        )
        saved = service.store.save_page(page)
        return f"Created page {saved.id}: {saved.title}"

    @tool
    def patch_page(page_id: str, operation: str, old_text: str, new_text: str) -> str:
        """Update an existing memory page by applying a patch.

        Args:
            page_id: ID of the page to update.
            operation: One of 'replace', 'append', 'delete'.
            old_text: Text to find (for replace/delete operations).
            new_text: Replacement text (for replace/append operations).

        Returns:
            Confirmation of the patch application.
        """
        from memoryos_lite.schemas import MemoryPatch, PatchOperation

        op_map = {
            "replace": PatchOperation.REPLACE,
            "append": PatchOperation.ADD,
            "delete": PatchOperation.DELETE,
        }
        if operation not in op_map:
            return f"Invalid operation: {operation}. Use replace, append, or delete."
        if operation in ("replace", "delete") and not old_text:
            return f"old_text is required for {operation} operation."

        patch = MemoryPatch(
            target_page_id=page_id,
            operation=op_map[operation],
            old_text=old_text,
            new_text=new_text,
            reason=f"Agent patch: {operation} '{old_text}' -> '{new_text}'",
        )
        verified = service.commit_patch(session_id, patch)
        if not verified.verified:
            return f"Patch rejected for {page_id}: " + "; ".join(
                verified.errors or ["verification failed"]
            )
        applied = service.apply_patch(session_id, verified)
        if not applied:
            return f"Patch failed for {page_id}: could not apply to target page."
        return f"Patch applied to {page_id}: {operation} '{old_text}' -> '{new_text}'"

    @tool
    def list_pages() -> str:
        """List all memory pages in the current session.

        Returns:
            Formatted list of pages with IDs, titles, and types.
        """
        pages = service.store.list_pages(session_id)
        if not pages:
            return "No memory pages in this session."
        lines = [f"- [{p.id}] {p.title} ({p.page_type.value}, v{p.version})" for p in pages]
        return "\n".join(lines)

    return [search_memory, read_page, write_page, patch_page, list_pages]
