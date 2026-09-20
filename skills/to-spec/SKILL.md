---
name: to-spec
description: "Invoke when a conversation has settled on what to build and it's time to turn that into a written spec — \"turn this into a spec\", \"write this up\", \"spec this out\". Synthesis only: no interview. Pairs well with skill-tree:grill-for-planning, which is where the settled understanding usually comes from."
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Write
---

# To Spec

Turn the current conversation into a spec. Do **not** interview the user — that's
[grill-for-planning](../grill-for-planning/SKILL.md)'s job. This skill only synthesizes what's already been
discussed (plus what you can find in the repo) into a written artifact.

If the conversation hasn't actually settled the open questions yet — decisions still hedged,
contradictory, or missing — say so and point at `grill-for-planning` rather than papering over the gaps
with a spec that looks more decided than it is.

## Process

1. **Ground it in the repo.** Explore the codebase to understand current state, if you haven't
   already. Use the project's own domain vocabulary throughout the spec, and respect any ADRs or
   established conventions in the area being touched.

2. **Sketch the test seams.** Identify where this feature will actually be tested. Prefer
   existing seams to new ones, and the highest seam possible — fewer seams across the codebase is
   better; one is ideal. If a new seam is genuinely needed, propose it at the highest point you
   can. Check with the user that the seams match their expectations before writing them into the
   spec.

3. **Find out where the spec lives.** Don't assume an issue tracker — ask, or check the repo for
   an existing convention (a `docs/specs/` or `docs/handoffs/`-style directory, a GitHub/Linear
   issue template, an ADR folder). If nothing exists, default to a local file and ask the user
   where they want it.

4. **Write the spec** using the template below, then put it where step 3 established. If
   publishing to an external tracker (GitHub issue, Linear, Jira), confirm with the user before
   posting — this repo's human-in-the-loop rule applies to anything visible outside the local
   working tree, not just git.

<spec-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A LONG, numbered list of user stories. Each user story should be in the format of:

1. As an \<actor\>, I want a \<feature\>, so that \<benefit\>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

This list of user stories should be extremely extensive and cover all aspects of the feature.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very
quickly.

Exception: if a prototype (see [prototype](../prototype/SKILL.md)) produced a snippet that
encodes a decision more precisely than prose can (state machine, reducer, schema, type shape),
inline it within the relevant decision and note briefly that it came from a prototype. Trim to
the decision-rich parts, not a working demo, just the important bits.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation
  details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Out of Scope

A description of the things that are out of scope for this spec.

## Further Notes

Any further notes about the feature.

</spec-template>
