---
name: ui-designer
description: "Design or restyle a web UI — landing pages, dashboards, docs sites, app chrome — or when the user asks why a site \"looks generic\", \"looks like a template\", or wants it to feel intentional. A running list of design lessons learned, applied as rules rather than suggestions."
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

### 9. Pin every element to an edge.

A receipt has no separators and almost no whitespace: names left-aligned, prices right-aligned,
two edges holding everything together. Only what nobody needs to read is centered. Screens work
the same way — every element sits on an edge, and in compact UI (cards, list rows, chat inputs,
sidebars) almost everything sits on two or more.

When a container feels empty, don't add content to fill it; find or make an edge. A card has
four for free. A row that puts the avatar, name, and actions on one line creates a new edge for
everything below it, and each list row is the edge for the next. Too many buttons to align is
a content problem — cut them rather than stretching them or burying them in an overflow menu.
Right-align numeric columns so digits line up by place value.

An edge does the job people reach for nested containers to do. A single column rule or divider
is a card edge without the frame; prefer it to cards-in-cards with stacked borders and radii.
Edges also only hold across a short span — a row stretched across a wide screen keeps every
edge and still falls apart, so cap the width.

**Check:** name the edge each element sits on. "None" or "centered in leftover space" is a
miss. Then count nested bordered containers — framing three deep is doing an edge's job.

### 10. Density is fine. Uniformity isn't.

Nobody reads a screen top to bottom; they arrive with one question and scan for the answer. A
screen that resists scanning is rarely too full — it's too homogeneous. More whitespace helps a
little and makes everything slower. Differentiate instead: group by the key the user hunts with
(due date, owner, status), and break up runs of text with avatars, icons, and chips.

Show, don't describe. A mark the user already knows — an avatar, a status dot, a stop sign — is
understood before any text is read. When something is unclear, the instinct is to add a label,
a hint, a comparison; each one is more information and makes the screen harder to read. Reach
for a recognizable mark first and words last.

Let the data pick the form. A fixed set of values (department, status) is a chip, not a string.
Time-ordered data is a timeline or a chart, not a timestamp column to hunt through. Dim
inactive rows; truncate long text so it stops starving the columns beside it.

**Check:** blur the text and look again. If groups and states can't be told apart without
reading, it's uniform. Then look for enum values rendered as plain text, and tables whose only
real order is time.

### 11. Accent is contrast with neighbors, not a property.

Lesson 3 picks the accent; this is where it goes. An unchecked checkbox is a bare outline —
color is the signal that something changed, so nobody colors the off state. Hold everything
else to the same rule: defaults are neutral, and only what's non-default, urgent, or the one
primary action gets color or weight. Six chips all blue in their default state are six
checkboxes that turn blue when off. In a dashboard, color comes from the data (red means act
on this), never from decoration.

Because accent is a difference, quieting the surroundings emphasizes an element as well as
coloring it does.

**Check:** list every accented element. Each should be non-default, urgent, or the primary
action. If stripping its color loses no information, it was decoration.

### 12. Hide the secondary. Then design what's hidden.

Progressive disclosure is hierarchy by what's shown versus hidden. Place each action on a
spectrum of explicitness — labeled button, bare icon, revealed on hover/focus, inside a popover
or menu — by how often and how much it matters. Share lives in a popover, not a permanent
column; remove appears on row hover. A new feature rarely needs its own page, just the right
spot on that spectrum. Onboarding is the same idea over time: one tooltip on the most important
action, then the next — not a six-bullet modal that's forgotten the moment it's dismissed.

Hiding isn't a fix for too many primary actions (lesson 9) — those get cut, not tucked away.

The hidden UI is real work and often most of it: hover actions, copy affordances, comment
indicators, empty and error states, tooltips. Every icon-only control gets a tooltip and an
`aria-label`; assume nobody understands the icon. Hover-revealed has to mean focus-revealed too
(`:hover, :focus-within`), and under `@media (hover: none)` it's simply shown — otherwise
keyboard and touch users never find it (lesson 6).

**Check:** grep icon-only buttons with no `aria-label` or tooltip. Then tab through a row:
every action that appears on hover must also appear on focus.
