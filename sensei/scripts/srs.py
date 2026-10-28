#!/usr/bin/env python3
"""Learning state for the sensei skill: SM-2 cards, profile and log (stdlib only).

State lives in $LEARN_HOME/<topic>/ (default ~/.claude/learning):
  cards.json    spaced-repetition cards
  profile.json  goal, target, root, stage per sub-skill, solid/shaky, next, log
  map.md        the free-form concept map (written by the coach, not this script)

Cards
  srs.py add       <topic> "question" "answer" [--tag T] [--ref path:line]
  srs.py add-batch <topic>                      JSON list of {q,a,tag?,ref?} on stdin
  srs.py due       <topic> [--limit N] [--tag T]
  srs.py grade     <topic> <id> <0-5>           0-2 forgot, 3 hard, 4 good, 5 easy
  srs.py grade-batch <topic> 3:4,5:2,7:5        id:quality pairs, one write
  srs.py edit      <topic> <id> [--q Q] [--a A] [--tag T] [--ref R]
                                                (no flags: re-stamp a card verified against new code)
  srs.py suspend   <topic> <id>                 (unsuspend to undo)
  srs.py delete    <topic> <id>
  srs.py check-refs <topic>                     cards whose referenced code changed or vanished;
                                                code that only moved is re-pointed automatically

Profile
  srs.py profile <topic> [--goal G] [--target T] [--root DIR] [--stage SUB=N:note]
                         [--solid "a;b"] [--shaky "a;b"] [--next TEXT] [--log TEXT]
  srs.py map     <topic>                        print map.md path

Session
  srs.py resume   <topic>                       profile + stats + due cards in one call
  srs.py stats    <topic>
  srs.py overview                               every topic: due, recall, stage
  srs.py topics
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

HOME = Path(os.environ.get("LEARN_HOME", Path.home() / ".claude" / "learning"))
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
STAGES = {1: "unconscious incompetence", 2: "conscious incompetence",
          3: "conscious competence", 4: "unconscious competence", 5: "teaching from mastery"}
MATURE_DAYS = 21


def die(msg):
    sys.exit(f"srs: {msg}")


def tdir(topic):
    if not SLUG.match(topic):
        die(f"bad topic slug {topic!r}: use lowercase kebab-case")
    return HOME / topic


def today():
    return dt.date.today()


@contextmanager
def locked(topic):
    """Serialise writers per topic so concurrent sessions cannot drop each other's updates."""
    d = tdir(topic)
    d.mkdir(parents=True, exist_ok=True)
    with (d / ".lock").open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def read_json(p, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as e:
        die(f"{p} is corrupt ({e}); fix or move it aside")


def write_json(p, data):
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(p)


def load(topic):
    return read_json(tdir(topic) / "cards.json", [])


def save(topic, cards):
    write_json(tdir(topic) / "cards.json", cards)


def load_profile(topic):
    return read_json(tdir(topic) / "profile.json",
                     {"goal": "", "target": "", "root": "", "stages": {}, "solid": [],
                      "shaky": [], "next": "", "log": []})


def review(card, q):
    """SM-2: update interval, ease and repetitions for quality q in 0..5."""
    if q < 3:
        card["reps"] = 0
        card["interval"] = 1
    else:
        card["reps"] += 1
        if card["reps"] == 1:
            card["interval"] = 1
        elif card["reps"] == 2:
            card["interval"] = 6
        else:
            card["interval"] = round(card["interval"] * card["ease"])
    card["ease"] = max(1.3, card["ease"] + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    card["due"] = (today() + dt.timedelta(days=card["interval"])).isoformat()
    card["last"] = today().isoformat()
    card["history"].append([today().isoformat(), q])


def new_card(cards, q, a, tag="", ref=""):
    cid = max((c["id"] for c in cards), default=0) + 1
    card = {"id": cid, "q": q, "a": a, "tag": tag, "ease": 2.5, "interval": 0, "reps": 0,
            "due": today().isoformat(), "last": None, "history": [], "suspended": False}
    if ref:
        card["ref"] = ref
    cards.append(card)
    return cid


def find(cards, cid, topic):
    card = next((c for c in cards if c["id"] == cid), None)
    if card is None:
        die(f"no card {cid} in {topic}")
    return card


def due_cards(cards, tag=""):
    """Due cards, weakest first: recently failed, then most overdue, then lowest ease."""
    now = today().isoformat()
    due = [c for c in cards if c["due"] <= now and not c.get("suspended")
           and (not tag or c["tag"] == tag)]

    def key(c):
        failed = bool(c["history"]) and c["history"][-1][1] < 3
        return (not failed, c["due"], c["ease"])
    return sorted(due, key=key)


def stats(cards):
    now = today().isoformat()
    live = [c for c in cards if not c.get("suspended")]
    graded = [h[1] for c in live for h in c["history"]]
    return {
        "cards": len(live),
        "due_now": sum(c["due"] <= now for c in live),
        "mature": sum(c["interval"] >= MATURE_DAYS for c in live),
        "recall_rate": round(sum(q >= 3 for q in graded) / len(graded), 2) if graded else None,
    }


def brief(c):
    out = {k: c[k] for k in ("id", "q", "a", "tag", "due")}
    if c.get("ref"):
        out["ref"] = c["ref"]
    return out


def split_ref(ref):
    """'path:42' or 'path:42-50' -> (path, 42, 50); a bare path -> (path, None, None)."""
    m = re.match(r"^(.*?):(\d+)(?:-(\d+))?$", ref)
    if not m:
        return ref, None, None
    start = int(m.group(2))
    return m.group(1), start, int(m.group(3) or start)


def read_ref(root, path):
    """(hash, stripped lines) of a ref's file, or (None, None) if it is gone."""
    try:
        data = (Path(root).expanduser() / path).read_bytes()
    except OSError:
        return None, None
    return hashlib.sha1(data).hexdigest()[:12], [l.strip() for l in data.decode(errors="replace").splitlines()]


def anchor_at(lines, n):
    """The referenced line, extended over the next lines while it is too short to be
    distinctive (a lone brace, `else:`). Comparing this instead of the whole file means
    edits elsewhere in the file do not mark the card stale."""
    out = []
    for l in lines[n - 1:n + 4]:
        if l or out:
            out.append(l)
        if len(" ".join(out)) >= 16:
            break
    return out if any(out) else []


def find_anchor(lines, anchor):
    k = len(anchor)
    return [i + 1 for i in range(len(lines) - k + 1) if lines[i:i + k] == anchor]


def check_ref(root, card):
    """None if the card's code is unchanged, else {status, ...}. Statuses:
    moved (same code, new line; carries the corrected ref), changed, missing."""
    path, start, end = split_ref(card["ref"])
    h, lines = read_ref(root, path)
    out = {"id": card["id"], "ref": card["ref"]}
    if card.get("ref_anchor"):
        out["was"] = "\n".join(card["ref_anchor"])
    if h is None:
        return {**out, "status": "missing"}
    if h == card.get("ref_hash"):
        return None
    anchor = card.get("ref_anchor")
    if not anchor or start is None:
        return {**out, "status": "changed"} if card.get("ref_hash") else None
    hits = find_anchor(lines, anchor)
    if start in hits:
        return {**out, "status": "touched", "hash": h}  # file edited elsewhere; this code intact
    if hits:
        new = min(hits, key=lambda i: abs(i - start))
        span = f"-{new + end - start}" if end != start else ""
        return {**out, "status": "moved", "new_ref": f"{path}:{new}{span}", "hash": h}
    return {**out, "status": "changed"}


def parse_pairs(text):
    pairs = []
    for part in text.split(","):
        try:
            cid, q = part.split(":")
            cid, q = int(cid), int(q)
        except ValueError:
            die(f"bad pair {part!r}: expected id:quality")
        if not 0 <= q <= 5:
            die(f"quality {q} out of range 0-5")
        pairs.append((cid, q))
    return pairs


def cmd_profile(a):
    with locked(a.topic):
        p = load_profile(a.topic)
        for field in ("goal", "target", "root", "next"):
            v = getattr(a, field)
            if v is not None:
                p[field] = v
        for s in a.stage or []:
            m = re.match(r"^([^=]+)=([1-5])(?::(.*))?$", s)
            if not m:
                die(f"bad --stage {s!r}: expected SUB=N or SUB=N:note")
            p["stages"][m[1]] = {"stage": int(m[2]), "note": m[3] or "", "date": today().isoformat()}
        if a.solid is not None:
            p["solid"] = [x.strip() for x in a.solid.split(";") if x.strip()]
        if a.shaky is not None:
            p["shaky"] = [x.strip() for x in a.shaky.split(";") if x.strip()]
        if a.log:
            p["log"].append([today().isoformat(), a.log])
        write_json(tdir(a.topic) / "profile.json", p)
    print(json.dumps(p, indent=2))


def summary(topic):
    p, cards = load_profile(topic), load(topic)
    s = stats(cards)
    stages = {k: f"{v['stage']} {STAGES[v['stage']]}" for k, v in p["stages"].items()}
    return {"topic": topic, "goal": p["goal"], "target": p["target"], "stages": stages,
            "solid": p["solid"], "shaky": p["shaky"], "next": p["next"],
            "last_log": p["log"][-1] if p["log"] else None, **s}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cmd(name, *pos):
        sp = sub.add_parser(name)
        for x in pos:
            sp.add_argument(x)
        return sp

    s = cmd("add", "topic", "question", "answer")
    s.add_argument("--tag", default="")
    s.add_argument("--ref", default="")
    cmd("add-batch", "topic")
    s = cmd("due", "topic")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--tag", default="")
    s = cmd("grade", "topic")
    s.add_argument("id", type=int)
    s.add_argument("quality", type=int, choices=range(6))
    cmd("grade-batch", "topic", "pairs")
    s = cmd("edit", "topic")
    s.add_argument("id", type=int)
    for f in ("q", "a", "tag", "ref"):
        s.add_argument(f"--{f}")
    for name in ("suspend", "unsuspend", "delete"):
        s = cmd(name, "topic")
        s.add_argument("id", type=int)
    for name in ("check-refs", "stats", "resume", "map"):
        cmd(name, "topic")
    s = cmd("profile", "topic")
    for f in ("goal", "target", "root", "solid", "shaky", "next", "log"):
        s.add_argument(f"--{f}")
    s.add_argument("--stage", action="append")
    sub.add_parser("overview")
    sub.add_parser("topics")
    a = ap.parse_args()

    topics = sorted({p.parent.name for f in ("cards.json", "profile.json") for p in HOME.glob(f"*/{f}")}) \
        if HOME.exists() else []
    if a.cmd == "topics":
        print("\n".join(topics))
        return
    if a.cmd == "overview":
        for t in topics:
            sm = summary(t)
            print(json.dumps({k: sm[k] for k in ("topic", "stages", "cards", "due_now", "recall_rate", "next")}))
        return
    if a.cmd == "profile":
        return cmd_profile(a)
    if a.cmd == "map":
        print(tdir(a.topic) / "map.md")
        return

    # Read-only commands never create the topic directory.
    if a.cmd in ("due", "stats", "resume", "check-refs") and a.topic not in topics:
        die(f"no topic {a.topic!r}; known: {', '.join(topics) or '(none)'}")

    if a.cmd == "due":
        due = due_cards(load(a.topic), a.tag)
        print(json.dumps({"total_due": len(due), "cards": [brief(c) for c in due[:a.limit]]}))
    elif a.cmd == "stats":
        print(json.dumps(stats(load(a.topic))))
    elif a.cmd == "resume":
        cards = load(a.topic)
        due = due_cards(cards)
        print(json.dumps({**summary(a.topic), "total_due": len(due),
                          "cards": [brief(c) for c in due[:10]]}, indent=1))
    else:
        with locked(a.topic):
            cards = load(a.topic)
            root = load_profile(a.topic)["root"]

            def stamp(card):
                if card.get("ref") and root:
                    path, start, _ = split_ref(card["ref"])
                    h, lines = read_ref(root, path)
                    if h:
                        card["ref_hash"] = h
                        card.pop("ref_anchor", None)
                        if start and anchor_at(lines, start):
                            card["ref_anchor"] = anchor_at(lines, start)

            if a.cmd == "check-refs":
                # Mechanical repairs happen here, like a floorplan refresh carrying descriptions
                # over: code that only moved gets its ref updated, files edited elsewhere get
                # re-stamped. Only cards whose own code changed or vanished are reported.
                if not root:
                    die("no root set; run: srs.py profile <topic> --root <dir>")
                for c in cards:
                    if c.get("ref") and not c.get("suspended"):
                        r = check_ref(root, c)
                        if r is None:
                            continue
                        h = r.pop("hash", None)
                        if r["status"] == "touched":
                            c["ref_hash"] = h
                            continue
                        if r["status"] == "moved":
                            c["ref"], c["ref_hash"] = r["new_ref"], h
                        print(json.dumps(r))

            elif a.cmd == "add":
                cid = new_card(cards, a.question, a.answer, a.tag, a.ref)
                stamp(cards[-1])
                print(cid)
            elif a.cmd == "add-batch":
                try:
                    items = json.load(sys.stdin)
                    ids = [new_card(cards, i["q"], i["a"], i.get("tag", ""), i.get("ref", ""))
                           for i in items]
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    die(f"add-batch expects a JSON list of {{q,a,tag?,ref?}}: {e!r}")
                for c in cards[-len(ids):]:
                    stamp(c)
                print(json.dumps(ids))
            elif a.cmd == "grade":
                card = find(cards, a.id, a.topic)
                review(card, a.quality)
                print(f"card {card['id']}: next review {card['due']} (interval {card['interval']}d)")
            elif a.cmd == "grade-batch":
                pairs = parse_pairs(a.pairs)
                for cid, q in pairs:
                    find(cards, cid, a.topic)
                for cid, q in pairs:
                    review(find(cards, cid, a.topic), q)
                print(json.dumps(stats(cards)))
            elif a.cmd == "edit":
                card = find(cards, a.id, a.topic)
                for f in ("q", "a", "tag", "ref"):
                    if getattr(a, f) is not None:
                        card[f] = getattr(a, f)
                stamp(card)
                print(json.dumps(brief(card)))
            elif a.cmd in ("suspend", "unsuspend"):
                find(cards, a.id, a.topic)["suspended"] = a.cmd == "suspend"
                print(f"card {a.id}: {a.cmd}ed")
            elif a.cmd == "delete":
                find(cards, a.id, a.topic)
                cards = [c for c in cards if c["id"] != a.id]
                print(f"card {a.id}: deleted")
            save(a.topic, cards)


if __name__ == "__main__":
    main()
