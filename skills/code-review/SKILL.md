---
name: code-review
description: "Two-axis review of changes since a fixed point (commit, tag, HEAD~N, or default HEAD~1): Standards (does the code follow this repo's conventions?) and Spec (does the code do what it should?). Axes run as parallel sub-agents so neither masks the other. Use when the user says \"review\", \"code review\", \"check my changes\", or before pushing."
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash, Agent
---

# Code Review

Two-axis review: **Standards** and **Spec**, run in parallel so one can't mask the other.

A change can pass one axis and fail the other:
- Code that follows every standard but implements the wrong thing -> Standards pass, Spec fail.
- Code that does exactly what was asked but breaks conventions -> Spec pass, Standards fail.

## Process

### 1. Pin the fixed point

Use whatever the user said as the fixed point (a commit SHA, branch, tag, `HEAD~5`, etc.).
If they didn't specify one, default to `HEAD~1` (the last commit). For uncommitted work,
diff against `HEAD`.

Capture the diff once:

```
git diff <fixed-point>...HEAD    # committed changes
git diff HEAD                    # if reviewing uncommitted work
```

Also note commits: `git log <fixed-point>..HEAD --oneline`.

Verify the fixed point resolves (`git rev-parse`) and the diff is non-empty. A bad ref or
empty diff should fail here, not inside the sub-agents.

### 2. Identify the spec source

Look for what the changes are *supposed* to do, in this order:

1. A path the user passed as an argument ("review against docs/spec.md").
2. Issue references in commit messages (`#123`, `Closes #45`), fetched via `gh issue view`.
3. A spec file under `docs/`, `specs/`, or `.scratch/` matching the branch name or feature.

If nothing is found, ask the user. If they say there isn't one, skip the Spec axis entirely
and note it in the final report.

### 3. Identify the standards sources

Anything in the repo that documents how code should be written:

- `CLAUDE.md`, `.claude/CLAUDE.md` (project instructions)
- `CODING_STANDARDS.md`, `CONTRIBUTING.md`
- Linter configs (`.ruff.toml`, `.eslintrc`, `mypy.ini`, etc.) — note these exist but don't
  re-check what the linter already enforces

On top of repo-documented standards, always carry the **smell baseline** below: Fowler code
smells (Refactoring, ch.3) that apply even when a repo documents nothing. Two rules:

- **The repo overrides.** A documented repo standard always wins; where it endorses something
  the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"),
  never a hard violation. Skip anything tooling already enforces.

#### Smell baseline

Each entry: what it is -> how to fix.

- **Mysterious Name**: name doesn't reveal what it does or holds -> rename; if no honest name
  comes, the design is murky.
- **Duplicated Code**: same logic shape in more than one hunk/file -> extract, call from both.
- **Feature Envy**: method reaches into another object's data more than its own -> move the
  method onto the data it envies.
- **Data Clumps**: same few fields/params keep travelling together -> bundle into one type.
- **Primitive Obsession**: a primitive standing in for a domain concept -> give the concept
  its own small type.
- **Repeated Switches**: same switch/if-cascade on the same type recurs -> replace with
  polymorphism or one shared map.
- **Shotgun Surgery**: one logical change forces scattered edits across many files -> gather
  what changes together into one module.
- **Divergent Change**: one file edited for several unrelated reasons -> split so each module
  changes for one reason.
- **Speculative Generality**: abstraction/params/hooks added for needs that don't exist yet ->
  delete; inline until a real need shows.
- **Message Chains**: long `a.b().c().d()` navigation -> hide the walk behind one method.
- **Middle Man**: class/function that mostly just delegates -> cut it, call the real target.
- **Refused Bequest**: subclass that ignores most of what it inherits -> drop inheritance,
  use composition.

### 4. Spawn both sub-agents in parallel

Use the `Agent` tool to launch both at the same time.

**Standards sub-agent** prompt must include:
- The full diff (command and output, or the output directly if small enough).
- The commit list.
- The standards sources found in step 3, plus the smell baseline pasted in full.
- The brief: "Report, per file/hunk where relevant: (a) every place the diff violates a
  documented standard — cite the standard (file + rule); (b) any baseline smell you spot —
  name it and quote the hunk. Distinguish hard violations from judgement calls:
  documented-standard breaches are hard, baseline smells are always judgement calls, and a
  documented repo standard overrides the baseline. Skip anything tooling enforces.
  Under 400 words."

**Spec sub-agent** prompt must include:
- The diff and commit list.
- The spec contents (path or fetched issue body).
- The brief: "Report: (a) requirements the spec asked for that are missing or partial;
  (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look
  implemented but where the implementation looks wrong. Quote the spec line for each finding.
  Under 400 words."

If no spec was found, skip the Spec sub-agent and note it in the final report.

### 5. Aggregate

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly
cleaned. **Do not merge or rerank** — the axes are deliberately separate.

End with a one-line summary: total findings per axis and the worst issue within each.
Don't pick a single winner across axes.
