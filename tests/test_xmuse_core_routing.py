"""Tests for xmuse_core.routing — worklist, mentions, callbacks."""

from __future__ import annotations

import threading

from xmuse_core.routing.callbacks import CallbackCredentials, CallbackRouter
from xmuse_core.routing.mentions import parse_mentions
from xmuse_core.routing.worklist import DispatchChain, Worklist


class TestMentionParser:
    def test_basic_mention(self):
        assert parse_mentions("请 @archive-rag 检查") == ["archive-rag"]

    def test_multiple_mentions_capped(self):
        text = "@agent-a @agent-b @agent-c"
        result = parse_mentions(text)
        assert len(result) == 2
        assert result == ["agent-a", "agent-b"]

    def test_self_exclusion(self):
        result = parse_mentions("@master-god 完成", source_id="master-god")
        assert result == []

    def test_dedup(self):
        result = parse_mentions("@slave-a 然后 @slave-a 再次")
        assert result == ["slave-a"]

    def test_case_insensitive(self):
        result = parse_mentions("@Master-God hello", source_id="master-god")
        assert result == []

    def test_no_mentions(self):
        assert parse_mentions("普通消息没有 mention") == []

    def test_invalid_chars_split_mentions(self):
        result = parse_mentions("@inv@lid not a mention")
        assert "inv" in result
        assert "lid" in result


class TestDispatchChain:
    def test_initial_can_dispatch(self):
        chain = DispatchChain()
        assert chain.can_dispatch()
        assert chain.depth == 0

    def test_depth_limit(self):
        chain = DispatchChain(depth=15, max_depth=15)
        assert not chain.can_dispatch()

    def test_abort_propagates(self):
        parent = DispatchChain()
        child = parent.child()
        assert child.can_dispatch()
        parent.abort()
        assert not child.can_dispatch()
        assert child.aborted

    def test_child_increments_depth(self):
        chain = DispatchChain(depth=3)
        child = chain.child()
        assert child.depth == 4


class TestWorklist:
    def test_enqueue_and_consume(self):
        wl = Worklist()
        assert wl.enqueue("archive-rag", source_id="master-god")
        entry = wl.consume()
        assert entry is not None
        assert entry.target_id == "archive-rag"
        assert entry.source_id == "master-god"

    def test_dedup_rejects_duplicate(self):
        wl = Worklist()
        assert wl.enqueue("agent-a", source_id="master")
        assert not wl.enqueue("agent-a", source_id="master")
        assert wl.pending() == 1

    def test_depth_limit_blocks_enqueue(self):
        chain = DispatchChain(depth=15, max_depth=15)
        wl = Worklist(chain=chain)
        assert not wl.enqueue("target", source_id="src")

    def test_abort_blocks_consume(self):
        wl = Worklist()
        wl.enqueue("target", source_id="src")
        wl.chain.abort()
        assert wl.consume() is None

    def test_snapshot(self):
        wl = Worklist()
        wl.enqueue("a", source_id="s")
        wl.enqueue("b", source_id="s")
        wl.consume()
        snap = wl.snapshot()
        assert snap["pending"] == 1
        assert "a" in snap["seen"]
        assert "b" in snap["seen"]
        assert len(snap["history"]) == 1

    def test_thread_safety(self):
        wl = Worklist()
        results: list[bool] = []

        def enqueue_many(prefix: str):
            for i in range(50):
                results.append(wl.enqueue(f"{prefix}-{i}", source_id="t"))

        t1 = threading.Thread(target=enqueue_many, args=("a",))
        t2 = threading.Thread(target=enqueue_many, args=("b",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert sum(results) == 100
        assert wl.pending() == 100


class TestCallbackRouter:
    def test_post_message_enqueues(self):
        wl = Worklist()
        router = CallbackRouter(wl)
        creds = CallbackCredentials(
            invocation_id="inv-1",
            callback_token="tok-1",
            agent_id="slave-a",
            loop_id="xmuse",
        )
        router.register(creds)
        result = router.post_message("inv-1", "tok-1", "完成了 @master-god 请审核")
        assert result["ok"]
        assert "master-god" in result["enqueued"]
        assert wl.pending() == 1

    def test_invalid_credentials_rejected(self):
        wl = Worklist()
        router = CallbackRouter(wl)
        result = router.post_message("bad-id", "bad-tok", "@target hello")
        assert not result["ok"]
        assert result["error"] == "invalid_credentials"

    def test_revoke_prevents_further_calls(self):
        wl = Worklist()
        router = CallbackRouter(wl)
        creds = CallbackCredentials(
            invocation_id="inv-2",
            callback_token="tok-2",
            agent_id="slave-b",
            loop_id="xmuse",
        )
        router.register(creds)
        router.revoke("inv-2")
        result = router.post_message("inv-2", "tok-2", "@target hi")
        assert not result["ok"]

    def test_self_mention_excluded(self):
        wl = Worklist()
        router = CallbackRouter(wl)
        creds = CallbackCredentials(
            invocation_id="inv-3",
            callback_token="tok-3",
            agent_id="slave-c",
            loop_id="xmuse",
        )
        router.register(creds)
        result = router.post_message("inv-3", "tok-3", "@slave-c 自言自语")
        assert result["ok"]
        assert result["enqueued"] == []
        assert wl.pending() == 0
