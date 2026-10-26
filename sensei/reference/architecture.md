# Learning architecture and design

Teach **decisions and trade-offs**, not catalogs of patterns.

1. **Anchor** in a concrete scenario the learner cares about (their own system, a known product). Abstract pattern names without a problem don't stick.
2. **Forces first**: requirements, constraints, scale, team size, failure modes, what is likely to change. A pattern is an answer; make them feel the question.
3. **Let them choose, then critique**: they pick an approach and justify it before you reveal alternatives.
4. **Compare 2-3 alternatives on the same axes**: consistency, latency, complexity, operability, cost, team skill, reversibility. Say what each costs, and when it is the wrong choice.
5. **Stress it**: 10x load, a dependency down, a new requirement, a security incident, an on-call engineer at 3am.
6. **Decision rules**: end with "I'd choose A over B when ...". Add it as a card.
7. **Reverse check**: "what would make you change this decision?" and "what would you want to measure first?"
8. **Write it down**: a short ADR (context, options, decision, consequences) as a teach-back artifact. See the `engineering:architecture` and `engineering:system-design` skills for the full versions.

Good exercises: critique an existing design; evolve a design across a new requirement; compare two real systems that made opposite choices; draw the data flow and the failure modes from memory.
