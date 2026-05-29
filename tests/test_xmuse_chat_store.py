from pathlib import Path

from xmuse_core.chat.models import ProposalStatus
from xmuse_core.chat.store import ChatStore


def test_create_conversation_and_message(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "chat.db")
    conversation = store.create_conversation(title="xmuse MVP")
    message = store.add_message(
        conversation_id=conversation.id,
        author="human",
        role="human",
        content="Need a multi-GOD chat to lane flow.",
    )

    messages = store.list_messages(conversation.id)

    assert [item.id for item in messages] == [message.id]
    assert messages[0].content.startswith("Need a multi-GOD")


def test_accepting_proposal_creates_approved_resolution_snapshot(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "chat.db")
    conversation = store.create_conversation(title="xmuse MVP")
    proposal = store.create_proposal(
        conversation_id=conversation.id,
        author="architect-god",
        proposal_type="lane-plan",
        content="Split into chat, planner, execution, dashboard lanes.",
        references=[],
    )

    resolution = store.approve_proposal(
        proposal_id=proposal.id,
        approved_by=["human"],
        approval_mode="human",
        goal_summary="Build the MVP",
    )

    refreshed = store.get_proposal(proposal.id)
    assert refreshed.status is ProposalStatus.ACCEPTED
    assert resolution.status == "approved"
    assert resolution.version == 1


def test_resolution_versioning_supersedes_prior_snapshot(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "chat.db")
    conversation = store.create_conversation(title="xmuse MVP")
    proposal = store.create_proposal(
        conversation_id=conversation.id,
        author="architect-god",
        proposal_type="lane-plan",
        content="Initial plan",
        references=[],
    )

    first = store.approve_proposal(
        proposal_id=proposal.id,
        approved_by=["human"],
        approval_mode="human",
        goal_summary="v1",
    )
    second = store.create_resolution_version(
        prior_resolution_id=first.id,
        approved_by=["human"],
        approval_mode="human",
        goal_summary="v2",
    )

    assert store.get_resolution(first.id).status == "superseded"
    assert second.version == 2
