from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "xmuse"))
from xmuse_main import load_lanes


def test_load_lanes(tmp_path):
    lanes_file = tmp_path / "lanes.json"
    lanes_file.write_text(json.dumps({"lanes": [
        {"feature_id": "f1", "task_type": "execute", "prompt": "do it",
         "worktree": "/tmp/wt", "branch": "feat/f1", "capabilities": ["code"]},
        {"feature_id": "f2", "task_type": "execute", "prompt": "do other",
         "worktree": "/tmp/wt2", "branch": "feat/f2", "capabilities": ["code"],
         "status": "done"},
    ]}))
    lanes = load_lanes(lanes_file)
    assert len(lanes) == 1
    assert lanes[0].feature_id == "f1"
    assert lanes[0].worktree == "/tmp/wt"


def test_load_lanes_empty(tmp_path):
    lanes_file = tmp_path / "lanes.json"
    lanes_file.write_text(json.dumps({"lanes": []}))
    lanes = load_lanes(lanes_file)
    assert lanes == []
