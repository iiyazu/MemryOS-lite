#!/usr/bin/env python3
"""Validate RoomMem room JSON files (stdlib only).

Usage:
    python3 validate.py rooms/rm01.json [rooms/rm02.json ...]
    python3 validate.py            # validates every rooms/*.json next to this script
"""

import json
import os
import re
import sys
from glob import glob

KINDS = {"fact", "decision", "rule", "preference", "lesson"}
SCOPES = {"room", "project", "user"}
FIXED_SCOPE = {"rule": "project", "preference": "user"}
NOISE_TYPES = {
    "rejected_proposal",
    "hypothetical",
    "question",
    "chitchat",
    "agent_instruction",
    "restatement",
    "tentative",
    "plan_step",
}
ASKED_IN = {"same_room", "new_room_same_project"}
LANGS = {"en", "zh", "mixed"}
ROOM_RE = re.compile(r"^rm(\d{2})$")
TOPIC_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
MSG_RE = re.compile(r"^m(\d{2})$")

PROJECT_BY_NUM = {
    1: "atlas",
    2: "atlas",
    3: "atlas",
    4: "atlas",
    5: "beacon",
    6: "beacon",
    7: "beacon",
    8: "beacon",
    9: "cobalt",
    10: "cobalt",
    11: "cobalt",
    12: "cobalt",
}
LANG_BY_NUM = {
    1: "zh",
    2: "mixed",
    3: "en",
    4: "en",
    5: "zh",
    6: "mixed",
    7: "en",
    8: "en",
    9: "zh",
    10: "mixed",
    11: "en",
    12: "en",
}


def earliest_msg_num(memory):
    best = None
    for src in memory.get("sources") or []:
        mm = MSG_RE.match(str(src.get("message_id")))
        if mm:
            n = int(mm.group(1))
            if best is None or n < best:
                best = n
    return best


def validate_room(path):
    errors = []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "path": path,
            "room_id": "?",
            "project": "?",
            "language": "?",
            "errors": [f"cannot load: {exc}"],
            "counts": {
                "messages": 0,
                "gold": 0,
                "noise": 0,
                "probes": 0,
                "new_room": 0,
                "superseded": 0,
                "multi_source": 0,
            },
        }

    stem = os.path.splitext(os.path.basename(path))[0]
    rid = data.get("room_id")
    if rid != stem:
        errors.append(f"room_id {rid!r} does not match file name {stem!r}")
    m = ROOM_RE.match(stem)
    if m is None:
        errors.append(f"file name {stem!r} is not of the form rmNN")
    else:
        num = int(m.group(1))
        if num in PROJECT_BY_NUM and data.get("project") != PROJECT_BY_NUM[num]:
            errors.append(
                f"project {data.get('project')!r} should be {PROJECT_BY_NUM[num]!r} for {stem}"
            )
        if num in LANG_BY_NUM and data.get("language") != LANG_BY_NUM[num]:
            errors.append(
                f"language {data.get('language')!r} should be {LANG_BY_NUM[num]!r} for {stem}"
            )
    if data.get("language") not in LANGS:
        errors.append(f"language {data.get('language')!r} not in {sorted(LANGS)}")

    # -- participants --
    parts = data.get("participants")
    if not isinstance(parts, list) or not parts:
        errors.append("participants must be a non-empty list")
        parts = []
    part_ids = []
    humans = agents = 0
    for i, p in enumerate(parts):
        pid = p.get("id")
        if not isinstance(pid, str) or not pid:
            errors.append(f"participants[{i}]: missing id")
            continue
        if pid in part_ids:
            errors.append(f"participants[{i}]: duplicate id {pid!r}")
        part_ids.append(pid)
        kind = p.get("kind")
        if kind == "human":
            humans += 1
            if not p.get("name"):
                errors.append(f"participants[{i}]: human {pid!r} needs a name")
        elif kind == "agent":
            agents += 1
            if not p.get("vendor"):
                errors.append(f"participants[{i}]: agent {pid!r} needs a vendor")
        else:
            errors.append(f"participants[{i}]: kind {kind!r} not in ('human','agent')")
    if humans != 1:
        errors.append(f"expected exactly 1 human participant, found {humans}")
    if not 2 <= agents <= 3:
        errors.append(f"expected 2-3 agent participants, found {agents}")

    # -- messages --
    msgs = data.get("messages")
    if not isinstance(msgs, list):
        errors.append("messages must be a list")
        msgs = []
    if not 30 <= len(msgs) <= 60:
        errors.append(f"message count {len(msgs)} not in 30-60")
    msg_text = {}
    for i, msg in enumerate(msgs):
        mid = msg.get("id")
        expected = f"m{i + 1:02d}"
        if mid != expected:
            errors.append(
                f"messages[{i}]: id {mid!r} should be {expected!r} (ids must be m01.. sequential)"
            )
            continue
        spk = msg.get("speaker")
        if spk not in part_ids:
            errors.append(f"message {mid}: speaker {spk!r} is not a participant id")
        text = msg.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"message {mid}: empty text")
            continue
        msg_text[mid] = text

    # -- gold memories --
    gold = data.get("gold_memories")
    if not isinstance(gold, list):
        errors.append("gold_memories must be a list")
        gold = []
    if not 6 <= len(gold) <= 12:
        errors.append(f"gold memory count {len(gold)} not in 6-12")
    gold_by_id = {}
    multi_source = 0
    for i, g in enumerate(gold):
        gid = g.get("id")
        if not isinstance(gid, str) or not gid:
            errors.append(f"gold_memories[{i}]: missing id")
            continue
        tag = gid
        if gid in gold_by_id:
            errors.append(f"{tag}: duplicate gold memory id")
        gold_by_id[gid] = g
        kind = g.get("kind")
        scope = g.get("scope")
        if kind not in KINDS:
            errors.append(f"{tag}: kind {kind!r} invalid")
        if scope not in SCOPES:
            errors.append(f"{tag}: scope {scope!r} invalid")
        if kind in FIXED_SCOPE and scope != FIXED_SCOPE[kind]:
            errors.append(
                f"{tag}: kind {kind!r} must have scope {FIXED_SCOPE[kind]!r}, got {scope!r}"
            )
        topic = g.get("topic_key")
        if not isinstance(topic, str) or not TOPIC_RE.match(topic):
            errors.append(f"{tag}: topic_key {topic!r} must be dotted lowercase")
        if not str(g.get("statement") or "").strip():
            errors.append(f"{tag}: empty statement")
        srcs = g.get("sources")
        if not isinstance(srcs, list) or not srcs:
            errors.append(f"{tag}: sources must be a non-empty list")
            srcs = []
        if len(srcs) > 1:
            multi_source += 1
        for j, src in enumerate(srcs):
            smid = src.get("message_id")
            quote = src.get("quote")
            if smid not in msg_text:
                errors.append(f"{tag}.sources[{j}]: message {smid!r} does not exist")
                continue
            if not isinstance(quote, str) or not quote:
                errors.append(f"{tag}.sources[{j}]: empty quote")
            elif quote not in msg_text[smid]:
                errors.append(
                    f"{tag}.sources[{j}]: quote is not an exact substring of {smid}: {quote[:60]!r}"
                )
        if "superseded_by" not in g:
            errors.append(f"{tag}: missing superseded_by field (use null when current)")

    # -- supersession --
    superseded = 0
    for gid, g in gold_by_id.items():
        tgt = g.get("superseded_by")
        if tgt is None:
            continue
        superseded += 1
        t = gold_by_id.get(tgt)
        if t is None:
            errors.append(f"{gid}: superseded_by {tgt!r} is not a gold memory in this room")
            continue
        if t is g:
            errors.append(f"{gid}: superseded_by points to itself")
            continue
        if t.get("topic_key") != g.get("topic_key"):
            errors.append(f"{gid}: superseded_by {tgt} has a different topic_key")
        e_self, e_tgt = earliest_msg_num(g), earliest_msg_num(t)
        if e_self is not None and e_tgt is not None and e_tgt <= e_self:
            errors.append(
                f"{gid}: earliest source of superseding memory {tgt} (m{e_tgt:02d}) "
                f"does not come later than its own earliest source (m{e_self:02d})"
            )

    # -- noise --
    noise = data.get("noise")
    if not isinstance(noise, list):
        errors.append("noise must be a list")
        noise = []
    if len(noise) < 6:
        errors.append(f"noise count {len(noise)} is below the minimum of 6")
    for i, n in enumerate(noise):
        mid = n.get("message_id")
        if mid not in msg_text:
            errors.append(f"noise[{i}]: message {mid!r} does not exist")
        ntype = n.get("type")
        if ntype not in NOISE_TYPES:
            errors.append(f"noise[{i}]: type {ntype!r} invalid")
        if not str(n.get("note") or "").strip():
            errors.append(f"noise[{i}]: empty note")

    # -- probes --
    probes = data.get("probes")
    if not isinstance(probes, list):
        errors.append("probes must be a list")
        probes = []
    if not 7 <= len(probes) <= 10:
        errors.append(f"probe count {len(probes)} not in 7-10")
    probe_ids = set()
    new_room = 0
    superseding_targets = {
        g.get("superseded_by") for g in gold_by_id.values() if g.get("superseded_by")
    }
    for i, p in enumerate(probes):
        pid = p.get("id")
        if not isinstance(pid, str) or not pid:
            errors.append(f"probes[{i}]: missing id")
            pid = f"probes[{i}]"
        elif pid in probe_ids:
            errors.append(f"{pid}: duplicate probe id")
        probe_ids.add(pid)
        if not str(p.get("question") or "").strip():
            errors.append(f"{pid}: empty question")
        asked = p.get("asked_in")
        if asked not in ASKED_IN:
            errors.append(f"{pid}: asked_in {asked!r} invalid")
        answers = p.get("answer_memory_ids")
        if not isinstance(answers, list) or not answers:
            errors.append(f"{pid}: answer_memory_ids must be a non-empty list")
            answers = []
        resolved = []
        for aid in answers:
            g = gold_by_id.get(aid)
            if g is None:
                errors.append(f"{pid}: answer memory {aid!r} does not exist")
                continue
            if g.get("superseded_by") is not None:
                errors.append(
                    f"{pid}: answer memory {aid!r} is superseded and must not be an answer"
                )
            resolved.append(g)
        if asked == "new_room_same_project":
            new_room += 1
            for g in resolved:
                if g.get("scope") not in ("project", "user"):
                    errors.append(
                        f"{pid}: new_room_same_project probe references {g.get('id')!r} "
                        f"with scope {g.get('scope')!r}; only project/user scope allowed"
                    )
        mc = p.get("must_contain")
        if (
            not isinstance(mc, list)
            or not mc
            or not all(isinstance(x, str) and x.strip() for x in mc)
        ):
            errors.append(f"{pid}: must_contain must be a non-empty list of strings")
            mc = []
        mnc = p.get("must_not_contain")
        if not isinstance(mnc, list) or not all(isinstance(x, str) and x.strip() for x in mnc):
            errors.append(f"{pid}: must_not_contain must be a list of strings")
            mnc = []
        if any(aid in superseding_targets for aid in answers) and not mnc:
            errors.append(
                f"{pid}: answer memory supersedes another memory, "
                f"so must_not_contain must list the stale value(s)"
            )
        low_mnc = {x.lower() for x in mnc}
        for x in mc:
            if x.lower() in low_mnc:
                errors.append(f"{pid}: {x!r} appears in both must_contain and must_not_contain")

    return {
        "path": path,
        "room_id": rid if isinstance(rid, str) else "?",
        "project": data.get("project", "?"),
        "language": data.get("language", "?"),
        "errors": errors,
        "counts": {
            "messages": len(msgs),
            "gold": len(gold),
            "noise": len(noise),
            "probes": len(probes),
            "new_room": new_room,
            "superseded": superseded,
            "multi_source": multi_source,
        },
    }


def main(argv):
    args = argv[1:]
    if args:
        paths = args
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        paths = sorted(glob(os.path.join(here, "rooms", "*.json")))
        if not paths:
            print("no room files found under rooms/")
            return 1
    total_errors = 0
    t_msgs = t_gold = t_noise = t_probes = t_new = t_super = t_multi = 0
    for path in paths:
        res = validate_room(path)
        name = os.path.basename(path)
        errs = res["errors"]
        total_errors += len(errs)
        c = res["counts"]
        t_msgs += c["messages"]
        t_gold += c["gold"]
        t_noise += c["noise"]
        t_probes += c["probes"]
        t_new += c["new_room"]
        t_super += c["superseded"]
        t_multi += c["multi_source"]
        if errs:
            print(f"{name}: {len(errs)} error(s)")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"{name}: OK")
        print(
            f"  room {res['room_id']} ({res['project']}, {res['language']}): "
            f"messages={c['messages']}, gold={c['gold']}, noise={c['noise']}, "
            f"probes={c['probes']} (new_room_same_project={c['new_room']})"
        )
    print(f"== totals across {len(paths)} file(s) ==")
    print(f"  messages: {t_msgs}")
    print(f"  gold memories: {t_gold} (superseded: {t_super}, multi-source: {t_multi})")
    print(f"  noise entries: {t_noise}")
    print(f"  probes: {t_probes} (new_room_same_project: {t_new})")
    print(f"  errors: {total_errors}")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
