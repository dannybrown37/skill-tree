# CONTEXT.md Format

```markdown
# Context

Domain vocabulary for [project name]. Use these terms exactly in code, docs, specs, and
conversation. When a term here disagrees with casual usage, the term here wins.

## Terms

### <Term>

One-paragraph definition. What it IS, precisely.

- **Examples**: 2-3 concrete usages that are correct
- **Not**: what this term does NOT mean — the terms or meanings people confuse it with
- **In code**: where this concept lives (`Type` in `src/module/`)
- **See also**: links to related terms or ADRs
```

## Rules

- **Anti-examples are mandatory.** The "Not" line is where ambiguity actually gets resolved.
  If you can't say what the term is *not*, the definition isn't sharp enough.
- **Link to code.** Ground each term in the codebase. If there's no code yet, say so — that's
  a signal the concept is speculative.
- **Cross-reference.** Link terms to each other. Domain concepts form a graph, not a list.
- **No implementation details.** CONTEXT.md is a glossary. Decisions about *how* go in ADRs.
  Architecture goes in specs. This file answers "what do we call things and what do they mean."
