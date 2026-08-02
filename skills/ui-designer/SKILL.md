---
name: ui-designer
description: "Invoke when designing or restyling a web UI — landing pages, dashboards, docs sites, app chrome — or when the user asks why a site \"looks generic\", \"looks like a template\", or wants it to feel intentional. A running list of design lessons learned, applied as rules rather than suggestions."
user-invocable: true
---

# UI Designer

Accumulated design lessons, applied as rules. The through-line: **a default is a decision
someone else made for you.**

## Lessons

### 1. Bundle fonts. Never ship system defaults.

A system stack (`system-ui`, `-apple-system`, `Arial`) renders as "nobody chose this," and
differently on every machine. Type is the biggest lever on how a site feels — don't leave it
to the OS.

**Let the user pick.** Unless they've explicitly delegated the choice, build a sample page
first: the real content in 3–4 candidate pairings, with buttons to switch between them live,
and let them choose. Don't just pick one and move on.

Then self-host the winner — `woff2` in the repo, `@font-face`, `font-display: swap`, one or
two families, few weights, license clears self-hosting (SIL OFL is safe). No CDN link: it's a
third-party request, a privacy liability, and outright blocked under an artifact's CSP (inline
as a `data:` URI there). A system stack may appear only as the fallback tail.

**Check:** grep for `system-ui`, `-apple-system`, `Arial`, bare `sans-serif` as the *primary*
family. Each hit is a lesson not yet applied.

### 2. Spacing is a scale, not a guess.

`padding: 13px` next to `margin: 22px` is how a page reads as assembled rather than designed.
Pick one scale up front — a 4px base, or a modular ratio — declare it as custom properties
(`--space-1` … `--space-8`), and use nothing else for margin, padding, and gap.

**Check:** grep length values in `margin`/`padding`/`gap`. Anything off the scale, or any raw
px where a token exists, is a guess.

### 3. One hue with intent. Never pure black on pure white.

`#000` on `#fff` is the visual equivalent of `system-ui`. Use a near-black with a hue cast, a
slightly tinted surface, and one accent that carries meaning — not the framework default blue.
Name them as semantic tokens (`--surface`, `--text-muted`, `--accent`) so use sites never
reference raw hex.

For chart and data-viz palettes, defer to the `dataviz` skill — it owns categorical,
sequential, and diverging color, and this skill must not contradict it.

**Check:** grep `#000`, `#fff`, `#007bff`/`#337ab7`. Then count distinct hex literals — more
than about a dozen means there's no system, just accumulation.

### 4. Default to the boring layout. Earn the fancy one.

Most pages want one column, generous whitespace, and a hierarchy strong enough to skim. The
specific shape to avoid — because it's the unprompted default output, not just a bad choice —
is *hero + three feature cards with icons + gradient*. A multi-column grid, a carousel, or a
sticky sidebar has to be justified by the content, not reached for to fill space.

**Check:** if a card grid holds three items that are really just a list, it's a list.

### 5. Resolve the theme before first paint.

If a page supports dark mode, the stored preference has to be applied by a render-blocking
inline script in `<head>` — not a module, not deferred, not an import. Anything that runs after
first paint flashes the wrong background at every user who chose the non-default. This is the
one place where inlining a duplicate of logic that lives elsewhere is correct; comment it as
deliberate so nobody "cleans it up" into an import.

Three states, not two: light / dark / **system**. A boolean can't express "follow my OS," so a
two-state toggle permanently strands anyone whose OS switches on a schedule. Store the
*setting* and resolve it at paint — icon choice keys off the setting, the `dark` class off the
resolved result.

With a client-side router, `<html>`'s attributes are replaced by the incoming document's on
every navigation, dropping both the class and the attribute. Re-apply on the swap event or the
theme silently reverts on page two.

**Check:** set dark, hard-reload, watch for a white flash. Then navigate and confirm it holds.
Then see whether the toggle can get back to "system" at all.

### 6. Style `:focus-visible`, never `:focus`.

One global rule with an `outline` and an `outline-offset` covers an entire site — outlines
follow the element's own `border-radius`, so nothing needs per-element tuning. `:focus` rings
mouse clicks too, which is *why* people reach for `outline: none`; `:focus-visible` fires only
for keyboard, so there's nothing to suppress. `outline: none` with no replacement is the most
common accessibility defect on a hand-built site.

Pair it with a skip link as the first child of `<body>`, visually hidden until focused. It has
to out-stack a sticky header, or it renders underneath the thing it exists to skip past. Give
the target container `tabindex="-1"` so activating the link moves *focus*, not just scroll
position.

**Check:** grep `outline:\s*(none|0)`. Then tab through a cold page load — every stop visible,
and the first stop is the skip link.

### 7. Expand hit areas without moving the layout.

A text link in a nav is a ~16px-tall tap target. Pad it and the row grows around it. Negative
margins equal-and-opposite to the padding (`-my-4 py-4`, `-mx-3 px-3`) grow the hit area into
space the container already had — the text doesn't move and the row height doesn't change.

**Check:** hover the space just above and below a nav link. If the cursor isn't a pointer
there, the target is only as tall as the glyphs.

### 8. Continuous animation is opt-out and off-screen-paused.

Anything that loops indefinitely repaints indefinitely, including while scrolled out of view.
Gate it on an `IntersectionObserver`, check `prefers-reduced-motion: reduce` before it starts,
and wrap the animated region in `contain: paint` so its repaints don't re-composite the rest
of the page on every scroll frame.

Decorative motion on hover is fine behind `motion-safe:`. Motion that conveys state is not
decorative — it needs a static equivalent for anyone who opted out.

**Check:** scroll the animation off screen and watch the performance panel. Frames still being
painted means it never stopped.
