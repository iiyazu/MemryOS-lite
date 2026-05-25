"""@mention parser for agent routing.

Extracts target agent IDs from text content. Supports the xmuse agent
naming convention: @agent-id or @feature-id patterns.

Design reference: cat-cafe-tutorials/04-a2a-routing.md
- Multi-mention support (capped at MAX_MENTIONS_PER_MESSAGE)
- Source exclusion (agent can't @mention itself)
"""

from __future__ import annotations

import re

MAX_MENTIONS_PER_MESSAGE = 2

_MENTION_PATTERN = re.compile(r"@([\w][\w\-]{0,63})")


def parse_mentions(content: str, source_id: str | None = None) -> list[str]:
    """Extract @mention targets from content.

    Returns deduplicated list of target IDs, excluding source_id,
    capped at MAX_MENTIONS_PER_MESSAGE.
    """
    matches = _MENTION_PATTERN.findall(content)
    seen: set[str] = set()
    targets: list[str] = []
    for match in matches:
        target = match.lower()
        if target in seen:
            continue
        if source_id and target == source_id.lower():
            continue
        seen.add(target)
        targets.append(target)
        if len(targets) >= MAX_MENTIONS_PER_MESSAGE:
            break
    return targets
