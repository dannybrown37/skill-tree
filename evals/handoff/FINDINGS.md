# Findings — 2026-09-28

Writer/resumer `claude-opus-5-5`, judge `claude-opus-5-5`. 42 valid runs: run1 (fixtures
01–04, 2 runs/arm) + run3 (05–06, 3 runs/arm). Run1's 05 was discarded because of a fixture
bug, and run2 was discarded after hitting the usage limit.

| arm | transfer (run1 01–04) | transfer (run3 05–06) | on disk | anchor | status | hallucinations* |
|---|---|---|---|---|---|---|
| skill | 0.93 | 0.91 | 14/14 | 14/14 | 12/12 | 0 |
| baseline-file | 0.93 | 0.95 | 14/14 | 7/14 | 3/12 | 4 |
| baseline | 0.83 | 0.84 | 12/14 | 5/14 | 3/12 | 12 |

\*The judge prompt changed between runs (run3 no longer counts claims verified from the repo),
so compare within a run, not across runs.

## What the skill buys

- **It always persists.** Plain `baseline` put the handoff in chat only in 2/14 runs (both
  03-multi-repo runs). After `/clear`, that means zero transfer.
- **Anchor and status.** Every skill handoff had the real HEAD sha and a correct `**Status:**`,
  which is what the SessionStart hook and `handoff status` key on. Baselines only got this
  when an existing handoff showed the format (fixture 06).
- **No invented next steps.** In 05-awaiting-review, the baselines planned PRs, `/code-review`,
  and HTTP-date fixes the user never asked for. The skill's `awaiting-review` status held the
  line.

## What it doesn't buy (at this difficulty)

- **Content transfer is the same as "save it to a file."** Opus captures ~100% of facts
  either way. These transcripts are ~60–100 lines, and long, messy sessions (the skill's
  real target) aren't covered.
- **Cost:** about 20–30% more $ per run, and ~1.5x the words of `baseline-file`.

## Weak spots in SKILL.md (1 and 2 applied to Resuming; not re-evaluated)

1. **Resume step 3 overreacts to evidence that can't run.** In 06, the resumer re-ran the
   done-evidence without the dev Redis, saw it fail, and then doubted or dropped the
   committed middleware (2 of 3 skill runs). Suggested wording: *"If evidence can't run here
   (service down, env missing), say so and keep the claim; only a real failure invalidates
   it."*
2. **The resumer never looks at the backlog.** Deferred items were written to `BACKLOG.md`
   correctly but dropped from 2/2 briefings in 01. It did no harm (no trap fired), but a
   one-line "skim `handoff backlog` titles" in Resuming would make deferred work visible.
3. **The handoff counter was sometimes omitted** (1/3 in 05). Minor.

## Harness caveats

- One judge model, n = 2–3 per cell, so differences under ~0.05 are noise.
- The resumer is asked for a briefing, not to do the work. Traps measure intent, not actions.
- Next fixture worth adding: a long (300+ line) session with 3–4 tasks and a
  superseded plan.
