# Techniques, ranked by evidence

Evidence notes come from Dunlosky et al. (2013) as summarized in secondary sources, Ericsson on deliberate practice, and Naur. Primary papers were not re-checked here.

| Technique | Evidence | Use |
|---|---|---|
| Retrieval practice (self-testing) | High | Ask before telling. End every session with 3-5 no-peeking questions |
| Spaced practice / successive relearning | High | Cards in `srs.py`; review at expanding intervals; long gaps beat cramming |
| Deliberate practice | Strong in skill domains | Specific goal, full attention, immediate feedback, edge of ability. The product is better mental representations (patterns experts see and novices don't) |
| Elaborative "why" questions, self-explanation | Moderate | "Why does this work? What would break if...?" |
| Interleaving, varied examples | Moderate, weaker in what was reviewed | Mix related problem types so they must choose the method, not just apply it |
| Feynman technique (explain simply) | Plausible, not directly reviewed | Teach-back exposes gaps; fuzzy words mean a gap |
| Rereading, highlighting, passive watching | Low | Avoid as the main method |

## Exercise formats (pick the one that exercises the target skill)

- **Predict**: "What does this print / where does this request go / what breaks?" Then verify by running or reading.
- **Find the bug / smell**: show wrong or fragile code or design, ask what is off.
- **Fill the gap**: remove the key step from a worked example.
- **Build small**: the smallest thing that uses the idea, with tests as the feedback loop.
- **Change and explain**: "modify X; which other parts are affected?"
- **Design then critique**: they design from requirements; stress it (10x load, a component fails, a new requirement).
- **Contrast cases**: two near-identical things, "what's the difference and when does it matter?"
- **Teach-back / draw from memory**: explain or diagram without looking, then diff against reality.
- **Blank floorplan**: before seeing any structure, sketch the parts of a system and the arrows between them; later, diff against the real map. Missing parts and wrong arrows become cards.
- **Next hop**: walk a real flow one step at a time; at each step they predict where control or data goes next, then you reveal the `file:line`.
- **Plain words**: name each part by what it does for the user in one sentence, not by its technology or folder. A part they can only name by its stack is a gap.
- **Rubber-duck reverse**: you play a confused junior; they must unconfuse you.

## Good cards

One idea per card. Ask for a prediction, a reason, or a decision rule, not a definition. Include the context needed to answer unambiguously. Re-write cards that are failed repeatedly.
