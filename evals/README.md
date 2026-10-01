# Evals

Behavioural evals for skills, run with `claude plugin eval`. Unit tests cover each skill's
CLI. These cover what the model does with the playbook.

```bash
just eval                                      # pick a suite (fzf), or lists them off a TTY
just eval ui-designer                          # 2 cases, ~2.5 min, ~$0.55–0.70
just eval debug-ci                             # 3 cases
just eval debug-ci --runs 3                    # more samples per case
just eval ui-designer --ablation with-without  # also run without the plugin, report the delta
```

The recipe defaults to one run per case, no baseline arm, and a local-only report. Flags you
pass override those.

## Layout

- `<skill>/<NN-case>/case.yaml`: one case. Its `scaffold.sh`, if any, builds the workspace.
- `debug-ci/fixtures/`: `repo.sh` builds the repo every debug-ci case starts from. When given
  a fixture name, it copies that fixture's canned `gh` responses into the workspace's
  `.git/eval-gh/`.
- `../scripts/eval-bin/gh`: a stand-in `gh` the recipe puts first on `PATH`. It answers from
  `.git/eval-gh/`, or reports "not logged in" if that folder isn't there.

## Gotchas

- Regex `target: files` matches the list of changed paths, not their contents. To grep
  content, pin the filename in the prompt and use `target: { source: file, path: ... }`.
- Only `EVAL_*` keys are allowed in `execution.env`, which is why `PATH` comes from the recipe.
- The sandbox hides all of `evals/` from the agent's Bash, so it can't read graders. Anything
  the agent has to execute or read (the stand-in `gh`, its fixtures) must live elsewhere
  under the plugin root, or be copied into the workspace by the scaffold.
- The sandbox refuses to grant Bash if `~/.docker` contains a symlink (Docker Desktop on WSL
  creates these). Cases that need Bash (all of debug-ci) can't run on such a machine. The
  recipe only grants Bash to suites that ask for it, so the other suites still run.
