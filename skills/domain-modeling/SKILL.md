---
name: domain-modeling
description: "Build and sharpen a project's domain model. Invoke when discussing codebase terminology, writing or editing a CONTEXT.md, or recording or editing an ADR — \"what do we mean by X\", \"define our terms\", \"write an ADR for this\"."
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Domain Modeling

Actively build and sharpen the project's domain model as you design. This is the *active*
discipline: challenging terms, inventing edge-case scenarios, and writing the glossary and
decisions down the moment they crystallize. (Merely *reading* `CONTEXT.md` for vocabulary is
not this skill — any skill can do that. This skill is for when you're changing the model.)

## File structure

Most repos have a single context:

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

If a `CONTEXT-MAP.md` exists at the root, the repo has multiple bounded contexts. The map
points to where each one lives, each with its own `CONTEXT.md` and `docs/adr/`.

Create files lazily: only when you have something to write.

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with `CONTEXT.md`, call it out immediately. "Your
glossary defines 'cancellation' as X, but you seem to mean Y. Which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying
'account' — do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent
edge cases that force the user to be precise about boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a
contradiction, surface it: "Your code cancels entire Orders, but you just said partial
cancellation is possible. Which is right?"

### Update CONTEXT.md inline

When a term is resolved, update `CONTEXT.md` right there — don't batch. Use the format in
[references/CONTEXT-FORMAT.md](references/CONTEXT-FORMAT.md).

`CONTEXT.md` is a glossary and nothing else. No implementation details, no specs, no scratch
notes.

### Offer ADRs sparingly

Only offer to create an ADR when all three are true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for
   specific reasons

If any of the three is missing, skip the ADR. Use the format in
[references/ADR-FORMAT.md](references/ADR-FORMAT.md).

## Integration with other skills

- **[[grill-for-planning]]**: When a grilling round surfaces ambiguous terms, invoke this skill
  to resolve them before continuing.
- **[[to-spec]]**: Specs use CONTEXT.md vocabulary exactly. New terms go in the glossary first.
- **[[codebase-design]]**: That glossary is *structural* (Module, Seam, Interface). This one is
  *domain* (Account, Order, Identity). They don't overlap.
