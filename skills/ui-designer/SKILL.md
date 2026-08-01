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
