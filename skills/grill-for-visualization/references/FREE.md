# License-free stack

React, Vite, and a small frame runtime that ships in the template (`src/runtime/`). Rendering
is Playwright stepping a headless Chromium through each frame and piping screenshots to
`ffmpeg`. Everything is MIT or Apache licensed, so it is safe for work use.

## Requirements

- Node 22.18 or newer (the render script is TypeScript run directly by Node).
- `ffmpeg` on `PATH`. Check with `ffmpeg -version`; if it is missing, tell the user how to
  install it for their platform instead of working around it.

## Install

```bash
npm install --save-exact react react-dom @fontsource/inter
npm install --save-dev --save-exact vite @vitejs/plugin-react typescript vitest playwright \
  @types/react @types/react-dom @types/node
npx playwright install chromium
```

## Commands

| Command | Does |
|---|---|
| `npm run dev` | Preview in the browser: play/pause (space), scrub bar, arrow keys step one frame |
| `npm run still -- <frame>` | One frame to `out/stills/f<frame>.png` |
| `npm run render` | Full video to the path set in `package.json` |
| `npm test` | Runtime maths plus your `src/logic/` tests |
| `npm run typecheck` | `tsc --noEmit` |

A 25 second 1080p video renders in roughly a minute and a half.

## Runtime API

Import from `./runtime` (or `../runtime` inside `components/` and `scenes/`):

| Export | Use |
|---|---|
| `useCurrentFrame()` | Frame number, relative to the enclosing `Sequence` |
| `useVideoConfig()` | `{fps, width, height, durationInFrames}` |
| `interpolate(input, inRange, outRange, options?)` | Piecewise-linear map. Options: `extrapolateLeft` / `extrapolateRight` (`'extend'` or `'clamp'`), `easing` |
| `Easing` | `linear`, `quad`, `cubic`, and the wrappers `in`, `out`, `inOut` |
| `spring({frame, fps, config?, durationInFrames?})` | 0 to 1. `config`: `damping`, `mass`, `stiffness`. `damping: 200` gives a smooth rise with no overshoot; around 12 gives a pop |
| `Sequence` | `from`, `durationInFrames`; children see a local frame and are unmounted outside the window |
| `AbsoluteFill` | Full-bleed flex column |

That is the whole surface. There is no `Img`, `staticFile`, audio, or `Series`: use a plain
`<img>` with a Vite import for assets, and compose longer timelines from `Sequence`.

## Rules that keep frames deterministic

- Everything visible must be a function of the frame number. No CSS transitions or
  animations, no `Date.now()`, no `Math.random()` without a fixed seed.
- Fonts come from `@fontsource/*` imports in `src/fonts.ts`, never a CDN. To change typeface,
  install the matching `@fontsource` package and update that file.
- Draw with DOM and SVG. Screenshots capture the page, so anything that renders in Chromium
  works; video and canvas elements driven by their own clocks do not.
