---
name: implement
description: "Implement a ticket or spec — \"build this\", \"implement the next ticket\", \"start working\". Drives TDD at pre-agreed seams, typechecks regularly, and presents work for review. Human-in-the-loop by default; pass 'autonomous' to work the full frontier with guardrails."
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Skill
---

# Implement

Execute a piece of work described by a spec, ticket, or conversation. This is the *doing*
skill — it assumes the thinking (grill, spec, tickets) already happened.

## Preflight

Before writing code, check:

1. **Is there a spec or ticket?** If the user said "build X" with no spec, ask whether they
   want to go straight or run [[to-spec]] / [[to-tickets]] first. Don't refuse — some work
   doesn't need a spec. But name the tradeoff.
2. **Is there a handoff?** If `CURRENT.md` exists for this branch, read it. If it points at
   this work, resume from where it left off. If it points at something else, ask.
3. **What's the test seam?** Identify where this work will be tested before writing any
   production code. Prefer existing seams. If the spec named seams, use those.

## Execution

### TDD loop

For each unit of work:

1. **Write the test first.** The test describes the behaviour from the caller's perspective,
   at the agreed seam. Run it — it should fail.
2. **Write the minimum code to pass.** No more.
3. **Run the test.** If it fails, fix the code, not the test (unless the test was wrong).
4. **Typecheck.** Run the project's typechecker after each pass. Fix type errors before moving
   on — they compound.
5. **Refactor if warranted.** Only if the passing code has a clear smell. Don't refactor
   speculatively.

Run single test files as you go. Save the full suite for the end.

### Cadence

**Default (human-in-the-loop):** implement one ticket or one logical unit, then stop. Present:
- What was built and why
- The tests that prove it works
- The command to verify (`pytest path`, `npm test -- path`, etc.)

Wait for user feedback before continuing to the next ticket.

**Autonomous mode** (user explicitly says "autonomous", "work the frontier", "keep going"):
work through tickets in dependency order. Stop on:
- An ambiguity the spec or tickets don't resolve
- A test that fails and the fix isn't obvious within two attempts
- A decision that would be hard to reverse
- Completion of the frontier

Even in autonomous mode, don't commit — present the full body of work for review.

### Handoff maintenance

If a /handoff exists for this branch, keep it current as you work — this is not optional:

- After each ticket/unit: update `CURRENT.md` (next action, acceptance check) and append the
  done-claim to `NARRATIVE.md` with evidence
- When work surfaces that isn't next: `handoff add` it, don't park it in your head
- Set status: `in-progress` while working, `awaiting-review` when presenting to the user

If no handoff exists, don't create one — the user will if they want one.

## Finishing

When the work is complete (one ticket in default mode, the frontier in autonomous):

1. **Run the full test suite.** Fix anything that broke.
2. **Run the typechecker.** Clean.
3. **Run `pre-commit`** (or `prek`) if the project has it. Fix what it reports.
4. **Invoke [[code-review]]** on the diff. Fix anything it finds before presenting to the user.
5. **Present the work.** Summary of what changed, the verification commands, and any open
   questions. Don't commit — the user does that.

## Integration

- **[[to-tickets]]** or **[[to-spec]]** produce the input this skill consumes
- **[[handoff]]** maintains session state as you work
- **[[verify]]** shores up done-claims before writing them to the narrative
- **[[code-review]]** runs at the end before presenting to the user
- **[[domain-modeling]]** — use `CONTEXT.md` vocabulary in code, tests, and commit-ready summaries
