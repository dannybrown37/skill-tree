# ADR Format

File naming: `docs/adr/NNNN-<slug>.md`, zero-padded to 4 digits. Glob `docs/adr/[0-9]*.md`
to find the next number.

```markdown
# NNNN — <Title>

**Status**: proposed | accepted | deprecated | superseded by [NNNN](NNNN-slug.md)

**Date**: YYYY-MM-DD

## Context

What forces are at play? What's the problem or trigger? State facts, not opinions.

## Decision

What we decided and why. Name the alternatives considered and why they lost.

## Consequences

What becomes easier. What becomes harder. What we'll have to live with.
```

## Rules

- **Append-only.** Never edit an accepted ADR's Decision or Context. To reverse a decision,
  write a new ADR that supersedes it.
- **Consequences are honest.** Every decision has downsides. If the Consequences section is
  pure upside, it's marketing.
- **Link from CONTEXT.md.** When an ADR resolves a naming question or defines a concept, link
  the glossary entry to the ADR.
