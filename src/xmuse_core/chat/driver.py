"""Multi-GOD chat driver for xmuse.

Drives a poll-based group-chat conversation between human users and GOD
personas (architect, review). On each tick, the driver scans chat.db for
new human messages, routes them by @mention, spawns a one-shot GOD
subprocess (Codex by default for non-GOD work, Claude as fallback) for
the matching role, and writes the GOD's reply back into the conversation.

Runtime selection (``runtime`` arg or ``XMUSE_CHAT_DRIVER_RUNTIME`` env):
- ``codex`` (default for non-GOD work) — uses ``codex exec`` with the model
  named in ``XMUSE_NON_GOD_CODEX_MODEL`` (default ``gpt-5.4``).
- ``claude`` — uses ``claude -p --output-format json`` with ``model``.

This is the transitional bridge from "evolution-controller writes everything
itself" to "long-lived GOD sessions chat in real time". GodSessionLayer
integration will replace the per-tick subprocess once Phase 1 sessions are
hooked into the runtime.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from xmuse_core.chat.models import ChatMessage
from xmuse_core.chat.store import ChatStore

logger = logging.getLogger(__name__)


_ROLE_PROMPTS: dict[str, str] = {
    "architect": (
        "You are the Architect GOD of xmuse, a multi-agent autonomous "
        "delivery system. You participate in a group chat with a human "
        "operator and other GODs (review, etc).\n\n"
        "Your job: read the conversation, understand what the human or "
        "another GOD is asking for, and respond. You may:\n"
        "- ask a clarifying question\n"
        "- propose a concrete next step\n"
        "- @mention another GOD if their input is needed\n"
        "- emit a structured proposal that, when approved, becomes a lane "
        "graph the platform will execute\n\n"
        "Output format (strict): emit ONE of:\n"
        '  {"type": "message", "text": "<reply text>"}\n'
        '  {"type": "mention", "to": "review", "text": "<reply text>"}\n'
        '  {"type": "proposal", "summary": "<short>", "lanes": [{"feature_id": "...", '
        '"prompt": "...", "depends_on": [], "capabilities": ["code"], '
        '"feature_group": "..."}]}\n\n'
        "Always output ONLY the JSON object, no markdown fence, no commentary. "
        "If unsure, emit type=message asking for clarification."
    ),
    "review": (
        "You are the Review GOD of xmuse. You participate in the group "
        "chat to evaluate proposals from the architect or human.\n\n"
        "When you respond, emit ONE of:\n"
        '  {"type": "message", "text": "<reply text>"}\n'
        '  {"type": "verdict", "decision": "approve"|"narrow"|"reject", "rationale": "<short>"}\n\n'
        "Always output ONLY the JSON object, no markdown fence, no commentary."
    ),
}


@dataclass(frozen=True)
class ChatTickOutcome:
    conversation_id: str
    source_message_id: str
    god_role: str
    reply_message_id: str | None
    envelope_type: str | None
    skip_reason: str | None = None


class ChatDriver:
    def __init__(
        self,
        *,
        chat_db_path: Path | str,
        runtime: str | None = None,
        model: str | None = None,
        timeout_s: float = 60.0,
        codex_binary: str | None = None,
        claude_binary: str | None = None,
    ) -> None:
        self._store = ChatStore(chat_db_path)
        self._runtime = (
            runtime
            or os.environ.get("XMUSE_CHAT_DRIVER_RUNTIME")
            or "codex"
        ).lower()
        if self._runtime not in {"codex", "claude"}:
            raise ValueError(f"ChatDriver runtime must be codex|claude, got {self._runtime!r}")
        if model is not None:
            self._model = model
        elif self._runtime == "codex":
            self._model = os.environ.get("XMUSE_NON_GOD_CODEX_MODEL", "gpt-5.4")
        else:
            self._model = os.environ.get("XMUSE_CHAT_DRIVER_CLAUDE_MODEL", "haiku")
        self._timeout_s = timeout_s
        self._codex = codex_binary or shutil.which("codex") or "codex"
        self._claude = claude_binary or shutil.which("claude") or "claude"
        # cursor: conversation_id -> last processed human-message id
        self._cursor: dict[str, str] = {}

    def tick(self) -> list[ChatTickOutcome]:
        outcomes: list[ChatTickOutcome] = []
        for conv in self._store.list_conversations():
            outcomes.extend(self._process_conversation(conv.id))
        return outcomes

    def _process_conversation(self, conversation_id: str) -> list[ChatTickOutcome]:
        messages = self._store.list_messages(conversation_id)
        if not messages:
            return []
        cursor_id = self._cursor.get(conversation_id)
        # If we've never seen this conversation, set the cursor to the last
        # message and skip — the driver should only react to *new* human input.
        if cursor_id is None:
            self._cursor[conversation_id] = messages[-1].id
            return []
        new_messages = self._messages_after(messages, cursor_id)
        outcomes: list[ChatTickOutcome] = []
        for msg in new_messages:
            if msg.role != "human":
                # Skip silently — assistant/system messages are not GOD work.
                continue
            outcomes.append(self._handle_message(conversation_id, msg))
        if messages:
            self._cursor[conversation_id] = messages[-1].id
        return outcomes

    def _messages_after(
        self,
        messages: list[ChatMessage],
        cursor_id: str,
    ) -> list[ChatMessage]:
        seen = False
        out: list[ChatMessage] = []
        for msg in messages:
            if seen:
                out.append(msg)
            elif msg.id == cursor_id:
                seen = True
        return out

    def _handle_message(self, conversation_id: str, msg: ChatMessage) -> ChatTickOutcome:
        role = self._route(msg.content)
        try:
            raw = self._call_god(role, conversation_id, msg.content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat-driver: %s call failed: %s", role, exc)
            return ChatTickOutcome(
                conversation_id=conversation_id,
                source_message_id=msg.id,
                god_role=role,
                reply_message_id=None,
                envelope_type=None,
                skip_reason=f"call_failed:{exc}",
            )
        envelope = self._parse_envelope(raw)
        reply_text = self._envelope_to_text(envelope, raw)
        author = f"{role}-god"
        reply = self._store.add_message(
            conversation_id=conversation_id,
            author=author,
            role="assistant",
            content=reply_text,
        )
        return ChatTickOutcome(
            conversation_id=conversation_id,
            source_message_id=msg.id,
            god_role=role,
            reply_message_id=reply.id,
            envelope_type=envelope.get("type") if envelope else None,
        )

    def _route(self, content: str) -> str:
        lower = content.lower()
        if "@review" in lower or "@review-god" in lower:
            return "review"
        if "@architect" in lower or "@architect-god" in lower:
            return "architect"
        # Default per spec: architect handles unaddressed messages.
        return "architect"

    def _call_god(self, role: str, conversation_id: str, content: str) -> str:
        skill_prompt = _ROLE_PROMPTS[role]
        recent_messages = self._store.list_messages(conversation_id)[-12:]
        history = "\n".join(
            f"[{m.role}/{m.author}] {m.content}" for m in recent_messages
        )
        prompt = (
            f"{skill_prompt}\n\n"
            f"## Recent conversation\n\n{history}\n\n"
            f"## Latest message\n\n{content}\n\n"
            "Now reply with the strict JSON envelope described above."
        )
        if self._runtime == "codex":
            return self._call_codex(prompt)
        return self._call_claude(prompt)

    def _call_codex(self, prompt: str) -> str:
        cmd = [
            self._codex,
            "exec",
            "-m",
            self._model,
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self._timeout_s,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"codex exit {proc.returncode}: {proc.stderr.strip()[:300]}")
        return proc.stdout

    def _call_claude(self, prompt: str) -> str:
        cmd = [
            self._claude,
            "-p",
            "--bare",
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
            "--model",
            self._model,
            "--disallowedTools",
            "Bash",
        ]
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self._timeout_s,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude exit {proc.returncode}: {proc.stderr.strip()[:300]}")
        envelope = json.loads(proc.stdout)
        result = envelope.get("result")
        if not isinstance(result, str):
            raise ValueError("claude wrapper missing 'result' string")
        return result

    def _parse_envelope(self, raw: str) -> dict | None:
        text = raw.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        candidate = fence.group(1) if fence else text
        first = candidate.find("{")
        last = candidate.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return None
        try:
            obj = json.loads(candidate[first : last + 1])
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None

    def _envelope_to_text(self, envelope: dict | None, raw: str) -> str:
        if envelope is None:
            return raw.strip()[:4000]
        kind = envelope.get("type")
        if kind == "message":
            return str(envelope.get("text", "")).strip() or raw.strip()[:4000]
        if kind == "mention":
            target = envelope.get("to", "?")
            text = str(envelope.get("text", "")).strip()
            return f"@{target}-god {text}" if text else f"@{target}-god"
        if kind == "proposal":
            summary = str(envelope.get("summary", "")).strip()
            lanes = envelope.get("lanes", [])
            lane_count = len(lanes) if isinstance(lanes, list) else 0
            return (
                f"[proposal] {summary} ({lane_count} lane{'s' if lane_count != 1 else ''}). "
                f"Approve via POST /api/chat/proposals/<id>/approve."
            )
        if kind == "verdict":
            decision = str(envelope.get("decision", "?"))
            rationale = str(envelope.get("rationale", "")).strip()
            return f"[verdict: {decision}] {rationale}".strip()
        return raw.strip()[:4000]
