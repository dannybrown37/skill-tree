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

2. **Fetch and trim the logs in one step.** `gh run view --log-failed` dumps every line of
   every failed job; this extracts only the error regions, per job and step:
   ```
   "${CLAUDE_PLUGIN_ROOT:-${SKILL_TREE_DIR:-$HOME/projects/skill-tree}}/skills/debug-ci/scripts/debug-ci"
   ```
   With no arguments it takes the newest failing run on the current branch. Useful flags:
   `<run-id>` positionally, `--branch`, `--repo owner/name`, `--context N` (lines kept
   before each error), `--max-lines N` (ceiling per step), `--json`.

   Exit codes: `0` extracted, `1` no failing run on that branch, `2` unusable (`gh` missing,
   unauthenticated, or the run isn't readable) — in that case report it and stop, don't try
   to fix auth yourself.

3. **Read what it kept, and mind the elisions.** Every gap is marked
   `... N lines omitted ...`. If the kept region doesn't contain the cause, re-run with a
   larger `--context`/`--max-lines`, or fall back to the raw
   `gh run view <run-id> --log-failed` rather than guessing. If the CLI reports other
   failing runs on the branch, ask the user which one matters instead of assuming.

4. **Diagnose the root cause** from the log, not from guessing at the diff. If the log
   doesn't make the cause obvious, say so and ask rather than fixing the first plausible
   thing.

5. **Fix it following this repo's standing conventions** (see that repo's own CLAUDE.md,
   if any): TDD (test first where the failure is a code bug), discrete reviewable steps,
   invoke the relevant language skill/reference for the code being touched.

6. **Verify locally before reporting done.** Run the same check CI ran (test suite,
   prek/pre-commit, lint) so "should pass now" is backed by a real local run, not an inference
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
- On older `gh` (seen on 2.23.0), `run view --log-failed` exits 0 and prints *nothing*. The
  CLI detects that empty answer and refetches via the REST jobs/logs API, so an empty log is
  never reported as a clean run.
