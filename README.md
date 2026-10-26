# sensei

A Claude Code skill that coaches you to real mastery of any topic: a codebase, an architecture, a library, a concept.

- Diagnoses your stage per sub-skill (four stages of competence), then teaches the next step only.
- Drives deliberate practice, retrieval and teach-back instead of passive explanation.
- Remembers you: spaced-repetition cards (SM-2) and a progress profile persist across sessions.
- Codebase recon script: languages, docs, entry points, largest files, git hotspots.

## Install

```sh
mkdir -p ~/.claude/skills && cp -r sensei ~/.claude/skills/
```

Then say "teach me X", "quiz me", "explain this codebase", or run `/sensei`.

State is stored in `~/.claude/learning/<topic>/` (override with `LEARN_HOME`). Scripts need only Python 3.

Based on https://scottjeffrey.com/four-stages-of-learning/ plus further research. The stage model's origin is disputed; it is used as a heuristic, and the evidence-backed techniques are listed in `sensei/reference/techniques.md`.
