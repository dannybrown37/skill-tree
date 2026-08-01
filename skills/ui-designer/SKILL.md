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
