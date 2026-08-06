---
name: cli-ergonomics
description: "Invoke when writing, reviewing, or extending any command-line entrypoint a human will run — a new CLI, a new subcommand, a script promoted out of one-off use. Covers the argument-handling ladder (help over error, TTY-guarded prompts, fzf selection, echoing the replayable command) and the hard `--version` requirement. Not for pure-library or single-purpose CI-only scripts."
user-invocable: true
---

# CLI Ergonomics

A CLI that only works when invoked perfectly is a CLI that only its author can use. Every
requirement below removes a way the user can get stuck without being told how to get unstuck.

Two independent parts: a **hard requirement** every versioned CLI must satisfy, and a
**progressive ladder** for argument handling where each level is optional but strictly better
than the one below it.

The ladder's governing constraint: **every interactive affordance must have a non-interactive
equivalent.** Interactivity is a convenience layered on top of a scriptable CLI, never a
replacement for one. A CLI that can only be driven by a human is as broken as one that can
only be driven by a script.

## Hard requirement: `--version`

**Every versioned CLI exposes `--version`.** No exceptions, including internal tools and
wrappers around other tools.

It prints the version and exits 0 — no side effects, no config loading, no network, no auth.
It must work on a broken install, because "what version am I running" is the first question
of every bug report and every upgrade, and an answer that requires a working config can't be
obtained precisely when it's needed most.

Report the CLI's *own* version. A wrapper that shells out and prints the wrapped tool's
version answers the wrong question; print both, clearly labeled, if both are useful.

Derive the string from one source of truth — the package metadata (`importlib.metadata.version`,
`package.json`, `Cargo.toml`, a build-stamped variable) — never a hand-maintained constant that
drifts from the release it claims to be.

**Check:** run `<cli> --version` from a directory with no config present and, if the tool
authenticates, with credentials unset. It must still print and exit 0. Then compare the output
against the packaging metadata; equal strings, or the constant has drifted.

## The argument ladder

Levels 1 and 2 are the baseline for anything a human runs. Levels 3–5 are worth it in
proportion to how often the CLI is run interactively.

### Level 1 — No arguments prints help, not an error

A bare invocation is how people explore an unfamiliar CLI. Answering it with
`error: missing required arguments, use --help` spends the user's first interaction telling
them to do a second one, when the help text was right there.

When required arguments are missing and there's nothing better to do (see Level 2), print the
usage/help output. Exit non-zero if you like — the behavior at issue is *what gets printed*,
not the status code.

**Check:** run the entrypoint with no arguments. If the output is a one-line error whose
content is "run --help", it fails. Usage text passes.

### Level 2 — Prompt, but guard the TTY

Better than printing help: ask for what's missing.

```console
$ my_cli
Enter environment: test
Enter target_id: abc123
Processing...
```

This introduces the failure mode that makes prompting dangerous — in CI, a prompt reads EOF or
blocks, and the job hangs until it times out with no useful log line. So prompting carries two
non-negotiable obligations:

1. **A non-interactive entrypoint exists.** Every prompted value is also settable as an
   argument or flag: `my_cli test abc123` must work with no prompting at all.
2. **Prompting fails loudly off a TTY.** Check before reading; raise a clear error rather than
   blocking or silently taking a default.

```python
def prompt(text: str) -> str:
    if not sys.stdin.isatty():
        raise RuntimeError("Not in a TTY.")
    return input(text)
```

Route every prompt through one such helper, so the guard can't be forgotten at a new call
site. The error message should name the flag the caller should have passed.

**Check:** run the command with stdin closed (`my_cli < /dev/null`) and confirm it errors
promptly instead of hanging or consuming a default. Then run the fully-argumented form and
confirm no prompt appears.

### Level 3 — Select from an enum instead of typing it

When a missing argument has a known, enumerable set of valid values, present them for
selection (fzf, or whatever picker the environment has) rather than asking the user to type a
value blind.

Free-text prompting for a constrained value just moves the validation error later; the user
types a plausible-but-wrong value and learns it was wrong after the round trip. A picker makes
the invalid value unrepresentable and doubles as documentation of what the valid ones are.

**Check:** confirm the enum feeding the picker is the same source the non-interactive path
validates against. Two hand-maintained lists will diverge, and the picker will be the stale one.

### Level 4 — Later options narrow by earlier ones

When one argument's valid values depend on a previous argument's — target IDs within the
chosen environment, tables within the chosen database — fetch the dependent set after the
first selection and offer only what's actually valid.

The real constraint here is cost, not capability: this turns argument parsing into a query. If
it's slow, hits a rate limit, or loads a production database, the latency lands on every
interactive invocation and it isn't worth it. Judge per case; when the query is expensive,
stay at Level 3 and validate after the fact.

**Check:** time the dependent lookup. If it's not comfortably sub-second on a realistic
dataset, don't ship it as an interactive step.

### Level 5 — Echo the replayable command

After an interactive run completes, print the equivalent fully-argumented invocation.

```console
Complete! Run again with:
  my_cli dev abc123
```

Interactive selection is excellent once and tedious on the fourth deploy-and-test iteration.
Echoing the command converts one guided run into a copy-pasteable one-liner for every run
after it — and gives the user something to paste into a script, a runbook, or a bug report.

Print it on failure too. A run that failed is the one most likely to be repeated.

**Check:** copy the echoed line, paste it, run it. It must reproduce the same invocation with
no prompting. Quote it correctly — a value containing a space or glob character that the echo
prints unquoted produces a line that looks right and runs wrong.

## Applying this

Adding a CLI: `--version` and Level 1 are table stakes. Add Level 2 the moment any argument is
required. Go further only where the CLI is genuinely run by hand, often.

Reviewing an existing CLI: report what's missing before changing anything, and don't rewrite a
working interaction into a different one just because it sits at a lower level than it could.
Climbing a level is only an improvement if the non-interactive path stays intact — check that
first, at every level.
