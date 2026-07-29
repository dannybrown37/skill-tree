---
name: verify
description: "Invoke before answering whether something works, is gone, is used, or is correct — and whenever the user says \"can you confirm\", \"are you sure\", \"did that actually work\", or reports something is \"still\" broken. Produces the answer plus the evidence that would have falsified it."
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash
---

# Verify

Answer, then prove the answer. Every claim ships with the check that could have refuted it
and the output that didn't.

If this repo already gates lint/tests on changed files (a Stop hook, pre-commit, CI), this
skill covers the claims no hook can check for you.

## The rule

**Reading code is not verification.** A diff shows intent; only execution shows behavior.
Every "it works now" must be backed by running the thing.

## Steps

1. **Answer first**, in one or two sentences. Don't pre-hedge — the verification pass is what
   earns or removes the hedge.

2. **Split it into atomic claims.** One falsifiable assertion each. "The TUI no longer
   references the 12-week year" is one claim; "and the CLI doesn't either" is a second.

3. **For each claim, pick a check that could fail.** This is the step that gets skipped. A
   check that restates the claim is not a check — you must be able to name its failure mode
   before running it.

   | Claim shape | Check that actually falsifies it |
   |---|---|
   | "X works now" | Run X. Capture real output. |
   | "X is gone / unused" | Search every surface it could hide in — source, tests, config, docs, generated files, other entry points. Absence from the file you edited proves nothing. |
   | "X is called from Y" | Grep the call site *and* confirm the path is reachable, not dead code behind a flag. |
   | "The fix handles case Z" | Construct Z and run it. A green happy path is not evidence about Z. |
   | "Nothing else uses this" | Search by symbol, by string, and by dynamic access (`getattr`, dict lookup, template interpolation). |
   | "The suite passes" | Run the whole suite. Report the command and the count. |

4. **Run them.** Real commands, real output. Never describe a check you did not execute.

5. **Report a table**: claim, check, result, verdict — where verdict is confirmed, refuted,
   or **unverified**.

6. **Surface what you could not check.** An unverified claim stays flagged in the answer. If
   the answer rests on one, lead with that rather than with the answer.

## Failure modes this exists to stop

- Calling a fix done without ever running/rendering it, then re-litigating "still not
  working" across several follow-up rounds.
- Answering a scope question ("is X gone / eliminated?") from the one file just edited,
  instead of searching every surface it could hide in.
- Reporting work as done while lint, tests, or CI would have failed on it.
