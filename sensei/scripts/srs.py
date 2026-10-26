#!/usr/bin/env python3
"""Spaced-repetition store for the learn skill (SM-2, stdlib only).

Cards live in $LEARN_HOME/<topic>/cards.json (default ~/.claude/learning).

  srs.py add   <topic> "question" "answer" [--tag T]
  srs.py due   <topic> [--limit N]        cards due today, as JSON lines
  srs.py grade <topic> <id> <0-5>         0-2 forgot, 3 hard, 4 good, 5 easy
  srs.py stats <topic>
  srs.py topics
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

HOME = Path(os.environ.get("LEARN_HOME", Path.home() / ".claude" / "learning"))


def path(topic):
    return HOME / topic / "cards.json"


def load(topic):
    p = path(topic)
    return json.loads(p.read_text()) if p.exists() else []


def save(topic, cards):
    p = path(topic)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cards, indent=2))
    tmp.replace(p)


def today():
    return dt.date.today()


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


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("topic"), a.add_argument("question"), a.add_argument("answer")
    a.add_argument("--tag", default="")
    d = sub.add_parser("due")
    d.add_argument("topic")
    d.add_argument("--limit", type=int, default=10)
    g = sub.add_parser("grade")
    g.add_argument("topic"), g.add_argument("id", type=int)
    g.add_argument("quality", type=int, choices=range(6))
    s = sub.add_parser("stats")
    s.add_argument("topic")
    sub.add_parser("topics")
    args = ap.parse_args()

    if args.cmd == "topics":
        for p in sorted(HOME.glob("*/cards.json")):
            print(p.parent.name)
        return

    cards = load(args.topic)
    if args.cmd == "add":
        cid = max((c["id"] for c in cards), default=0) + 1
        cards.append({"id": cid, "q": args.question, "a": args.answer, "tag": args.tag,
                      "ease": 2.5, "interval": 0, "reps": 0, "due": today().isoformat(),
                      "last": None, "history": []})
        save(args.topic, cards)
        print(cid)
    elif args.cmd == "due":
        now = today().isoformat()
        due = sorted((c for c in cards if c["due"] <= now), key=lambda c: c["due"])
        for c in due[: args.limit]:
            print(json.dumps({k: c[k] for k in ("id", "q", "a", "tag", "due")}))
    elif args.cmd == "grade":
        card = next((c for c in cards if c["id"] == args.id), None)
        if card is None:
            sys.exit(f"no card {args.id} in {args.topic}")
        review(card, args.quality)
        save(args.topic, cards)
        print(f"card {card['id']}: next review {card['due']} (interval {card['interval']}d)")
    elif args.cmd == "stats":
        now = today().isoformat()
        graded = [h[1] for c in cards for h in c["history"]]
        print(json.dumps({
            "cards": len(cards),
            "due_now": sum(c["due"] <= now for c in cards),
            "mature": sum(c["interval"] >= 21 for c in cards),
            "recall_rate": round(sum(q >= 3 for q in graded) / len(graded), 2) if graded else None,
        }))


if __name__ == "__main__":
    main()
