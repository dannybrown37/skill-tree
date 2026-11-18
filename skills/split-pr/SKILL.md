---
name: split-pr
description: "Break a large branch into small, atomic, reviewable PRs, usually stacked. Use when the user says \"this branch is huge\", \"split this PR\", \"break this into atomic PRs\", \"stack these\", or \"/split-pr\". Plans the cut, waits for approval, then builds the branches, verifies each one, and opens the stacked PRs."
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash, Edit, Write
---

# Split PR

Turn one large branch into a chain of small PRs. Each PR has one purpose, builds and passes tests by itself, and can be reviewed in about 15 minutes.

```
inventory ──► group into slices ──► order (stack/parallel) ──► [user approves plan]
                                                                   │
 report ◄── open PRs ◄── push ◄── verify each slice ◄── build branches ◄┘
```

## Step 1: Inventory (read-only)

```bash
base=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
git fetch -q origin "$base"
git status --short                                  # must be clean; else ask to commit or stash
git --no-pager log --oneline "origin/$base"..HEAD
git --no-pager diff --stat "origin/$base"...HEAD | tail -1
git --no-pager diff --dirstat=files,5 "origin/$base"...HEAD
```

Also look for planning artifacts that already define the cut: ticket files
(`docs/planning/**/tickets/NN-*.md`), a spec with a dependency graph, and the
Jira epic's child tickets. **If tickets exist, slice along tickets**: one
PR per ticket (or sub-ticket `02a`, `02b`) and put the Jira key in the branch
name and the PR title.

Before you start, record the original head as a safety tag: `git tag split-pr/backup-$(date +%Y%m%d%H%M) HEAD`.

## Step 2: Group into slices

Classify every changed file. A file can be split by hunk (`git add -p` or
`git checkout -p`), but avoid that unless the file mixes unrelated concerns.

Default slice order (skip empty ones):

| # | Slice | Typical contents | Why first |
|---|---|---|---|
| 0 | Docs / design | specs, ADRs, planning docs, READMEs | Reviewers learn the plan before the code; no risk |
| 1 | Prep refactors | renames, moves, extracted helpers, no behavior change | Big diff, trivial review; removes noise from later PRs |
| 2 | Contracts | API schema (swagger/OpenAPI), types, DB schema, migrations | Everything downstream depends on them |
| 3 | Infra | Tofu/Terraform modules, stacks, IAM, CI config | Often owned or reviewed by DevOps; separate approver |
| 4 | Walking skeleton | thinnest end-to-end path, behind a flag if needed | Proves the wiring |
| 5+ | Features | one behavior per PR, with its tests | The actual review |
| last | Cleanup | dead-code removal, flag removal | Only after the features land |

Rules for a good slice:
- **One sentence purpose.** If the title needs "and", split it.
- **Green on its own.** It lints, type-checks, and passes tests with only its ancestors applied.
- **Tests travel with code.** Never put "add tests" in a separate PR.
- **Size target:** at most about 400 changed lines of non-generated code. Generated files, lockfiles, and snapshots don't count, but call them out in the PR body.
- **No dead ends.** Code added in PR N is used by PR N or exercised by its tests, or the PR body says which PR uses it.

## Step 3: Choose the topology

- **Stacked** (`base ← A ← B ← C`) when slices depend on each other. This is the default.
- **Parallel** (each one off `base`) when slices are independent. Prefer this when possible; parallel PRs merge in any order.
- Mixed is fine: docs and infra are often parallel, and features stack on contracts.

Branch names: `<ticket-or-topic>/<NN>-<slug>`, e.g. `wcp-10047/01-api-contract`.
If a branch name already exists on the remote, stop and ask.

## Step 4: Present the plan, then pause

Show a table and a stack diagram:

```
| # | Branch | Base | Purpose | Files | ~Lines | Ticket |
```

Also list any file split by hunk, any slice that breaks the size target, and any slice you doubt is green alone. Wait for approval unless the user said "go" or autopilot is on. A plan is cheap to change; a pushed stack is not.

## Step 5: Build the branches

Build from the original branch's final tree so nothing is lost:

```bash
orig=$(git branch --show-current)
git switch -c <slice-1> "origin/$base"
git checkout "$orig" -- <paths for slice 1>   # or: git checkout -p "$orig" -- <file>
# commit with a clear message (repo conventions; Co-authored-by trailer)
git switch -c <slice-2> <slice-1>
...
```

Deleted files: `git rm <path>` in the slice that owns the deletion.

- Use real commits (one or a few per slice), not a squash of unrelated work.
- Work in the main checkout, **not a worktree**: repo pre-commit hooks often
  fail in worktrees. If a hook fails only in a worktree, treat it as an
  environment problem and not a regression, but say so in the report.
- Never use `--no-verify` without telling the user.

**Completeness check (required):** the tip of the stack must match the original branch.

```bash
git --no-pager diff "$orig" <last-slice> --stat   # must be empty
```

With parallel slices, use a temporary octopus merge or compare the union of the file lists. Any difference is a lost or extra change; fix it before
you push.

## Step 6: Verify each slice

For each branch in stack order, run the repo's cheapest real gate (`just`
recipe, `npm test`, `uv run pytest`, lint, type check, `tofu validate`).
Long runs go to the background, and you build the next slice meanwhile. A slice
that is red only because it lacks a descendant has the wrong cut. Move the
missing piece down the stack; don't paper over it.

## Step 7: Push and open PRs

```bash
git push -u origin <slice>                                   # each branch
gh pr create --base <parent-branch> --head <slice> --draft \
  --title "<TICKET>: <purpose>" --body-file <tmp>
```

The PR body has:
- **Purpose** (one sentence) and the Jira link.
- **Stack** section listing every PR in order with 👉 on this one; edit all
  bodies after every PR exists so the links resolve.
- **Review focus**: what to read closely and what's mechanical or generated.
- **Depends on / unblocks.**

Open as draft unless the user says otherwise. Don't request reviewers unless asked.

## Keeping the stack healthy

- After a change on PR N, rebase every descendant in order:
  `git rebase --update-refs <N>` from the tip branch (git ≥ 2.38) updates
  all intermediate branches at once. Then `git push --force-with-lease` each one.
- When the bottom PR merges (squash), rebase the next one onto `base`:
  `git rebase --onto origin/$base <old-bottom-branch> <next>`, then
  `gh pr edit <next> --base $base`.
- Remind the user of the rebase each time you edit a lower PR.

## Final report

- Stack diagram with PR URLs, sizes, and verify result per PR.
- Completeness check output (empty diff).
- Hunk-split files, oversized slices, and skipped hooks, with reasons.
- Backup tag name and how to delete it once the stack has merged.
