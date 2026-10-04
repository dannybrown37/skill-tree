---
name: grill-for-visualization
description: "Turn an idea into a polished coded video (product showcase or system/concept explainer) — \"make an animation of how X works\", \"visualize this for a demo\", \"grill me for a visualization\". Round-based interview about what to show, a storyboard the user approves, then a React project that renders an MP4, with the source kept editable. For stress-testing a plan with no video at the end, use skill-tree:grill-for-planning instead."
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, WebFetch
---

# Grill For Visualization

Interview the user until you know exactly what the video must say, get a storyboard approved,
then build it. The output is a self-contained project directory: a rendered MP4 plus the React
source that produced it, runnable with `npm install` and two scripts.

Read [references/BRIEF.md](references/BRIEF.md) before the first round. It is the creative
standard for everything below: composition, motion, typography, and the review checklist.

## 1. Grill

Use the round format and frontier rule from
[grill-for-planning](../grill-for-planning/SKILL.md): ask every question whose prerequisites
are settled in one numbered round, give a recommended answer for each, wait, recompute. Look
facts up yourself (repo, docs, brand assets on disk); put decisions to the user.

The design tree, roughly in dependency order:

- **Purpose.** What is being visualized, and is it a product showcase or an explainer of how
  something works? Who watches it, and where (meeting screen, phone, embedded in a doc)? What
  is the one thing they should understand afterwards?
- **Stack.** Is this for personal use or for work at a for-profit company of more than three
  people? This picks the stack in step 3, so ask it in the first round.
- **Truth.** The actual rules, thresholds, steps, and numbers. Limitations and caveats that
  must be shown honestly. Anything that must not appear (confidential details, competitor
  names, unreleased features).
- **Form.** Duration, aspect ratio, available assets (logo, screenshots, brand colors, fonts),
  mood or reference pieces, tone of the copy, the closing line.

Keep going for as many rounds as the tree needs. Stop when the frontier is empty, not when
the answers start to feel sufficient.

Never invent functionality, customer claims, or metrics to fill a gap: ask. If the user says
to just go, stop asking, make the remaining calls yourself, and list every assumption beside
the storyboard so each one can be corrected.

## 2. Storyboard

Present one table, one row per scene: what the viewer sees, what they should understand, the
on-screen copy, approximate duration, and how it hands off to the next scene. Under it, list
assumptions and anything illustrative rather than factual.

Do not create files until the user approves the storyboard. Changes loop back here.

## 3. Scaffold

Pick the stack from the answer in step 1 and read its reference:

- Personal use, or the user confirms they hold a Remotion license:
  [references/REMOTION.md](references/REMOTION.md).
- Work, or any doubt: [references/FREE.md](references/FREE.md). Same authoring API, no
  license requirement.

Scenes import from `./runtime` in both stacks, so everything in the brief applies to either.

Create the project in `./<slug>/` (or the current directory if it is empty), where `<slug>` is
a short kebab-case name for the piece:

```bash
T="${CLAUDE_PLUGIN_ROOT:-${SKILL_TREE_DIR:-$HOME/projects/skill-tree}}/skills/grill-for-visualization/templates"
mkdir -p <slug> && cp -r "$T/shared/." "$T/<free|remotion>/." <slug>/
```

Then set `name` and the output filename in `package.json` to the slug, and install with the
commands in the stack reference. Dependencies are installed with `--save-exact` at their
current versions; the templates carry none.

## 4. Build

1. **Logic first, test first.** Every number or state shown on screen comes from a pure
   function in `src/logic/` with a parametrized test beside it. A hand-typed figure in a
   scene drifts from the facts the moment the user edits one of them.
2. **Content.** Copy, colors, and timing go in `content.ts` under `src/`; add each scene to
   `timing` and `SCENE_ORDER`, and to the component map in `Video.tsx`. Total duration
   derives from these.
3. **Sequence, then polish.** Get every scene on screen in order with final copy before
   refining any one of them. Shared pieces go in `src/components/`.
4. Run `npm test` and `npm run typecheck`.

## 5. Review

Render one still for every beat of every scene (each point where something has just appeared
or settled), and open each image. Check them against the checklist at the end of the brief:
clipping, overlap, text size, one focal point per frame, an ending that holds. Fix and render
again until a full pass is clean. Then render the MP4.

Looking at the frames is the step that makes the result good. Passing tests say nothing about
whether a label sits on top of a vehicle.

## 6. Deliver

Write `README.md` in the project:

- Length, resolution, frame rate, and the commands (`npm install`, `npm run dev`,
  `npm run render`, `npm test`).
- The storyboard as built.
- A "change X in file Y" table: copy, colors, facts and thresholds, scene timing, assets,
  aspect ratio.
- Assumptions and anything illustrative.
- For the Remotion stack, the license note from its reference.

Tell the user where the MP4 is, what you assumed, and anything in the storyboard that changed
during the build.
