---
name: grill-for-planning
description: "Stress-test a vague plan, decision, or idea before it's written down — \"grill me on this\", \"poke holes in this idea\", \"help me think this through\". Round-based interview that maps the idea into a decision tree and works it to a shared understanding. For prepping a specific artifact (RFC/PR/promo packet) against a review panel, use skill-tree:grill-for-quality instead."
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, WebFetch
---

# Grill For Planning

Interview the user relentlessly about a plan, decision, or idea until you reach a shared
understanding. Map this as a **design tree**: every decision branches into the decisions that
hang off it.

## Process

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already
settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask
the whole frontier in one round: number each question and give your recommended answer. Then
wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree: settled decisions push the frontier outward and
unblock questions that depended on them. Recompute the frontier and ask the next round. A
question whose answer depends on another question still open in this round belongs to a _later_
round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the
environment (filesystem, repo state, a URL), go look it up yourself — don't ask the user for
anything you could find. **Claude:** dispatch a `fork` or other subagent for exploration that
doesn't need to block the round, so a running lookup only holds up the questions downstream of
it while the rest of the frontier is asked now. **No subagent available:** look it up inline
before asking that question, and just don't block the rest of the frontier on it. The
_decisions_ are the user's: put each to them and wait.

When a frontier question reveals an ambiguous or overloaded term, don't define it inline — point
at [domain-modeling](../domain-modeling/SKILL.md) to resolve it in `CONTEXT.md`, then resume.
A grilling round should never have to invent vocabulary that the rest of the project won't share.

The session is done when the frontier is empty: every branch of the design tree visited, nothing
left silently assumed. Do not act on it until the user confirms you have reached a shared
understanding.
