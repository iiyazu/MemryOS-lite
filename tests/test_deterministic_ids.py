from __future__ import annotations

import json
from pathlib import Path

from memoryos_lite.roommem import load_rooms, run_roommem
from memoryos_lite.schemas import deterministic_ids, new_id

ROOMS = Path(__file__).resolve().parents[1] / "benchmarks" / "roommem" / "rooms"


def test_deterministic_ids_repeat_inside_the_block_and_stay_random_outside() -> None:
    with deterministic_ids("seed"):
        first = [new_id("msg"), new_id("cmem")]
    with deterministic_ids("seed"):
        second = [new_id("msg"), new_id("cmem")]
    with deterministic_ids("other"):
        other = new_id("msg")

    assert first == second
    assert first[0].startswith("msg_") and first[1].startswith("cmem_")
    assert other != first[0]
    assert new_id("msg") != new_id("msg")


class _RecordingCuratorLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete_json(self, system: str, user: str) -> dict[str, object]:
        self.prompts.append(user)
        return {"memories": []}


def test_reruns_render_identical_curator_prompts(tmp_path) -> None:
    rooms = load_rooms(ROOMS, room_ids=["rm01"])
    recorders: list[_RecordingCuratorLLM] = []

    def factory(_settings):
        recorder = _RecordingCuratorLLM()
        recorders.append(recorder)
        return recorder

    for index in range(2):
        run_roommem(
            rooms,
            out_dir=tmp_path / f"out{index}",
            arms=["curated"],
            fake_llm=True,
            curated_llm_factory=factory,
            scratch_root=tmp_path / f"scratch{index}",
        )

    assert len(recorders) == 2
    assert recorders[0].prompts and recorders[0].prompts == recorders[1].prompts
    assert json.dumps(recorders[0].prompts).count("msg_") > 0
