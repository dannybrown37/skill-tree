---
name: debug-ci
description: "Invoke when a GitHub Actions run has failed and you want it diagnosed and fixed locally — e.g. \"why did CI fail\", \"the build is red\", \"check the Actions run\", \"/debug-ci\". Fetches the failure logs via `gh`, diagnoses the root cause, and fixes it locally — never commits or pushes, the user reviews and pushes manually."
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash, Edit, Write
---

# Debug CI

Diagnose a failed GitHub Actions run from its real logs, fix it locally, stop before any
git write. Same human-in-the-loop boundary most repos hold — this skill invokes `gh`, not
`git commit`/`git push`.

## Steps

1. **Confirm `gh` auth first**: `gh auth status`. If it's not authenticated, tell the user
   and stop — don't attempt to fix auth yourself.

2. **Find the failing run.** Default to the current branch:
   ```
   gh run list --branch "$(git branch --show-current)" --status failure --limit 5
   ```
   If the user named a PR or run instead, use that. If more than one recent run failed,
   ask which one before proceeding — don't guess.

3. **Pull the real failure logs**, not just the summary:
   ```
   gh run view <run-id> --log-failed
   ```
   Read the actual error output. A red X with an unread log is not a diagnosis.

4. **Diagnose the root cause** from the log, not from guessing at the diff. If the log
   doesn't make the cause obvious, say so and ask rather than fixing the first plausible
   thing.

5. **Fix it following this repo's standing conventions** (see that repo's own CLAUDE.md,
   if any): TDD (test first where the failure is a code bug), discrete reviewable steps,
   invoke the relevant language skill/reference for the code being touched.

6. **Verify locally before reporting done.** Run the same check CI ran (test suite,
   pre-commit, lint) so "should pass now" is backed by a real local run, not an inference
   from the diff. If the `verify` skill is installed alongside this one, invoke it for the
   claim-by-claim version of this check.

7. **Stop. Show the diff. Do not `git add`/`commit`/`push`.** Report what was wrong, what
   changed, and the command the user ran to reproduce the local pass. Pushing and watching
   the re-run is manual, same as every other change.

## Notes

- This skill only ever reads CI state (`gh run`/`gh api`) and writes to the working tree —
  it has no git-write step to skip, by design. If a future version adds auto-push, that's a
  deliberate policy change requiring explicit sign-off, not a default.
- Multiple failing jobs in one run: fix and verify one at a time rather than batching blind
  fixes across unrelated failures.
