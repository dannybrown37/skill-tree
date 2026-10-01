# Evals

Behavioural evals for skills. Unit tests cover each skill's CLI. These cover what the model
does with the playbook.

```bash
just eval                                      # pick a suite (fzf), or lists them off a TTY
just eval ui-designer                          # 2 cases, ~2.5 min, ~$0.55–0.70
just eval debug-ci                             # 3 cases, ~1.5 min, ~$0.60
just eval repo-audit                           # 5 cases
just eval handoff                              # 6 fixtures, skill arm only
just eval debug-ci --runs 3                    # more samples per case
just eval ui-designer --ablation with-without  # also run without the plugin, report the delta
```

| Suite | Runner | What it checks |
|---|---|---|
| `debug-ci` | `claude plugin eval` | diagnose from the CI log, fix, verify locally, no git writes |
| `ui-designer` | `claude plugin eval` | the skill's design rules, as greppable checks on a built page and a review |
| `repo-audit` | `claude plugin eval` | runs the checker, read-only, report format, catches the seeded gaps |
| `handoff` | `handoff/run.py` | write a handoff, resume it in a fresh session, judge what survived |

For `claude plugin eval` suites, the recipe defaults to one run per case, no baseline arm,
and a local-only report. Flags you pass override those. A case scoring below 1.0 makes the
command exit 1.

`handoff` needs three sessions (writer, resumer, judge), which `claude plugin eval` can't
express, so it has its own runner. The recipe's quick default is the skill arm, 1 run, and
a Sonnet judge. See `handoff/README.md` for the full comparison and what its metrics mean.
Its scores have no pass bar. It exits 1 only if a run didn't complete.

## Layout

- `<skill>/<NN-case>/case.yaml`: one case. Its `scaffold.sh`, if any, builds the workspace.
- `debug-ci/fixtures/`: `repo.sh` builds the repo every debug-ci case starts from. When given
  a fixture name, it copies that fixture's canned `gh` responses into the workspace's
  `.git/eval-gh/`.
- `../scripts/eval-bin/gh`: a stand-in `gh` the recipe puts first on `PATH`. It answers from
  `.git/eval-gh/`, or reports "not logged in" if that folder isn't there.
- `handoff/`: `run.py`, plus `fixtures/<name>/` (`setup.sh`, `transcript.md`,
  `fixture.json` with the facts and traps the judge grades against).

## Gotchas

- `file_exists` only sees files *created* during the run. Edits to existing files are
  invisible to it. To assert "not edited", check that the original content is still there
  with a regex on `{ source: file, path: ... }`.
- Regex `target: files` matches the list of new paths, not their contents. To grep content,
  pin the filename in the prompt and use `target: { source: file, path: ... }`.
- `tool_used` defaults to `min: 1`. A "never call this" grader needs `min: 0` and `max: 0`.
- Only `EVAL_*` keys are allowed in `execution.env`, which is why `PATH` comes from the recipe.
- The sandbox hides all of `evals/` from the agent's Bash, so it can't read graders. Anything
  the agent has to execute or read (the stand-in `gh`, its fixtures) must live elsewhere
  under the plugin root, or be copied into the workspace by the scaffold.
- Bash inside the sandbox needs `bubblewrap` and `socat` installed.
- The sandbox refuses to grant Bash if `~/.docker` contains a symlink (Docker Desktop on WSL
  creates these). For suites that need Bash, the recipe moves `~/.docker` to
  `~/.docker.eval-bak` for the run and restores it on exit, Ctrl-C, or termination. If a
  run is killed hard, the next run refuses to start until you move the backup back. Docker
  commands in other terminals see no config while a run is in progress.
- Skills with `disable-model-invocation: true` (repo-audit) can't trigger themselves.
  Their cases use the slash command as the prompt and check that the skill's first step
  ran, not that the skill fired.
- Fake secrets in a scaffold (repo-audit/04) need a `.gitleaksignore` fingerprint. The
  gitleaks hook only scans staged files, so prek passes on an unstaged file and the
  commit fails later.
