# Design It Twice

When the user wants to explore alternative interfaces for a chosen deepening candidate, use this
parallel-agent pattern. Based on "Design It Twice" (Ousterhout): your first idea is unlikely to
be the best.

Uses the vocabulary in [SKILL.md](../SKILL.md): **module**, **interface**, **seam**, **adapter**,
**leverage**.

## Process

### 1. Frame the problem space

Before spawning agents, write a user-facing explanation of the problem space for the chosen
candidate:

- The constraints any new interface would need to satisfy
- The dependencies it would rely on, and which category they fall into (see
  [DEEPENING.md](DEEPENING.md))
- A rough illustrative code sketch to ground the constraints, not a proposal, just a way to make
  the constraints concrete

Show this to the user, then immediately proceed to Step 2. The user reads and thinks while the
agents work in parallel.

### 2. Spawn agents

**Claude:** spawn 3+ agents in parallel via the `Agent` tool (fresh, not forks — each needs to
reach an independent design, not inherit yours). **No parallel-agent tool available:** produce
each design yourself in sequence instead, deliberately switching constraint between passes so
they stay radically different rather than converging on your first instinct.

Each design must be **radically different** from the others. Prompt each with a separate
technical brief (file paths, coupling details, dependency category from
[DEEPENING.md](DEEPENING.md), what sits behind the seam). The brief is independent of the
user-facing problem-space explanation in Step 1. Give each a different design constraint:

- Design 1: "Minimize the interface: aim for 1–3 entry points max. Maximise leverage per entry
  point."
- Design 2: "Maximise flexibility: support many use cases and extension."
- Design 3: "Optimise for the most common caller: make the default case trivial."
- Design 4 (if applicable): "Design around ports & adapters for cross-seam dependencies."

Include the [SKILL.md](../SKILL.md) vocabulary and the project's own domain vocabulary (a
glossary doc, ADRs, or established naming in the area) in each brief so every design names
things consistently.

Each design should produce:

1. Interface (types, methods, params, plus invariants, ordering, error modes)
2. Usage example showing how callers use it
3. What the implementation hides behind the seam
4. Dependency strategy and adapters (see [DEEPENING.md](DEEPENING.md))
5. Trade-offs: where leverage is high, where it's thin

### 3. Present and compare

Present designs sequentially so the user can absorb each one, then compare them in prose.
Contrast by **depth** (leverage at the interface), **locality** (where change concentrates), and
**seam placement**.

After comparing, give your own recommendation: which design you think is strongest and why. If
elements from different designs would combine well, propose a hybrid. Be opinionated: the user
wants a strong read, not a menu.
