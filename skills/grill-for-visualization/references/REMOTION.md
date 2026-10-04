# Remotion stack

React and [Remotion](https://www.remotion.dev). The template's `src/runtime/index.ts`
re-exports Remotion's primitives, so scenes are written exactly as in the license-free stack
and can move between the two unchanged.

## License

Remotion is free for individuals, non-profits, and for-profit organizations of up to three
people. Larger for-profit organizations need a paid Company License, and the rule is about the
organization, not the audience: an internal-only video still counts. Terms:
<https://www.remotion.dev/docs/license>.

If the user is doing this for work and has not said they hold a license, use
[FREE.md](FREE.md). Put a one-line license note in the generated README either way.

## Install

```bash
npm install --save-exact remotion @remotion/cli @remotion/google-fonts react react-dom
npm install --save-dev --save-exact typescript vitest @types/react @types/react-dom
```

The three Remotion packages must be the same version; check `package.json` after installing.

## Commands

| Command | Does |
|---|---|
| `npm run dev` | Remotion Studio preview |
| `npm run still -- out/stills/f<frame>.png --frame=<frame>` | One frame |
| `npm run render` | Full video to the path set in `package.json` |
| `npm test` | Your `src/logic/` tests |
| `npm run typecheck` | `tsc --noEmit` |

## Notes

- Fonts load through `@remotion/google-fonts` in `src/fonts.ts`.
- To use Remotion features beyond the shared surface (`Img`, `staticFile`, `Series`, audio),
  add them to the re-export in `src/runtime/index.ts`. Scenes that use them no longer port to
  the license-free stack, so say so in the README.
- Everything visible must be a function of `useCurrentFrame()`. No CSS transitions.
