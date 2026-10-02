---
name: implement
description: "Implement a ticket or spec — \"build this\", \"implement the next ticket\", \"start working\". TDD by default at pre-agreed seams, typechecks regularly, and presents verified work for review. Human-in-the-loop by default; pass 'autonomous' to work the full frontier with guardrails."
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
   production code. Prefer existing seams. If the spec named seams, use those. If there's no
   sensible seam (see below), decide now what proof you'll show instead.

## Execution

### TDD loop (default)

TDD is the default, not a requirement. The goal is proof the code works; a test is usually the
best proof, but not always. Skip the test when it would only restate a taste call — copy,
spacing, colours, naming, a config value — or when it would pin implementation rather than
behaviour. Say so when you skip it, and name the proof you'll use instead (a screenshot, the
command's output, the rendered page).

For each unit of work, *make the change easy, then make the easy change* (Kent Beck):

0. **Make the change easy.** If the code resists the change, refactor it first — tests green
   before and after, no behaviour change — so the change itself becomes small and obvious.
   Keep that refactor separate from the change so each can be reviewed on its own.
1. **Write the test first.** The test describes the behaviour from the caller's perspective,
   at the agreed seam. Run it — it should fail.
2. **Write the minimum code to pass.** No more. Where it adds a module or grows an interface,
   aim for a **deep module** — lots of behaviour behind a small interface (see
   [[codebase-design]]). "Minimum" means minimal behaviour, not an interface that leaks it.
3. **Run the test.** If it fails, fix the code, not the test (unless the test was wrong).
4. **Typecheck.** Run the project's typechecker after each pass. Fix type errors before moving
   on — they compound.
5. **Refactor if warranted.** Only if the passing code has a clear smell. Don't refactor
   speculatively.

Run single test files as you go. Save the full suite for the end.

### Cadence

**Default (human-in-the-loop):** implement one ticket or one logical unit, then stop. Present:
- What was built and why
- The proof it works — tests, or the non-test evidence named above
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
4. **Invoke [[verify]]** on each done-claim. Run the thing, not just its tests — every claim
   in the summary ships with the check that could have refuted it and its output.
5. **Invoke [[two-axis-review]]** on the diff. Fix anything it finds before presenting to the user.
6. **Present the work.** Summary of what changed, the proof from step 4, the verification
   commands, and any open questions. Don't commit — the user does that.

## Integration

- **[[to-tickets]]** or **[[to-spec]]** produce the input this skill consumes
- **[[handoff]]** maintains session state as you work
- **[[verify]]** proves each done-claim at finish, and before writing it to the narrative
- **[[two-axis-review]]** runs at the end before presenting to the user
- **[[codebase-design]]** — deep-module vocabulary for any interface this work adds
- **[[domain-modeling]]** — use `CONTEXT.md` vocabulary in code, tests, and commit-ready summaries
