# Learning a codebase

Naur: the real knowledge in a program is the *theory* in people's heads (purpose, why it is shaped this way, how it should change), and the source text is a lossy record of it. Goal is to rebuild that theory, not memorize files.

1. **Recon**: `python3 -I scripts/codemap.py <path>`. Reports languages, docs, manifests, entry points, largest files, git hotspots, contributors. These are facts; interpretation comes next.
2. **Orient**: read the docs it flagged. State in one sentence what the system is for and who uses it. Make the learner state it too.
3. **Run it** and watch behavior before deep reading. Build, run tests, use the thing.
4. **Trace one real flow end to end** (a request, a command, an event): the smallest flow touching the main layers. Give a `file:line` walk-through or a sequence diagram. Pick it from hotspots when possible.
5. **Name the architecture**: modules and boundaries, data model, where state lives, how parts communicate, what is configurable, the 3-5 central abstractions.
6. **Ask why**: what constraints produced this shape? what alternatives were plausible? Evidence: git history, ADRs, comments, tests. Label guesses as guesses.
7. **Predict, then verify**: before opening a file, the learner predicts what is in it or how a change would propagate. Check by reading or running.
8. **Make a small change**: a trivial fix, a log line, a test. Failing tests are the feedback loop.
9. **Teach-back**: learner draws or writes the architecture from memory; diff it against the code.
10. **Bank it**: cards such as "where does X state live and who mutates it?", "what happens between request and response?", "why is Y a separate module?"

Pitfalls: reading top to bottom; trusting stale docs over code; confusing the largest file with the most important; stopping at what, never reaching why. Hotspots and big files are leads, not verdicts.
