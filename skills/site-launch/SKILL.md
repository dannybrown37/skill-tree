---
name: site-launch
description: "Invoke before a website goes live, or when auditing one that already is — \"is this ready to ship\", \"why does my link look blank when I share it\", \"the site has no analytics\", \"add an RSS feed\". The checklist of things a site needs that aren't visible on the page itself."
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash
---

# Site Launch

Everything a site needs that you can't see by looking at it. `ui-designer` owns how the page
looks; this owns what happens when someone shares it, subscribes to it, or searches for it.

The through-line: **a page that renders correctly is not a site that has shipped.** Each item
below is missing by default in every framework and every starter template — none of them
break the build, so none of them get noticed until someone links the site somewhere.

Stack-agnostic on purpose: the requirement is stated, the implementation is whatever the
project already uses. Check what's in the repo before reaching for a new dependency.

## Run the checker first

`site-launch check <build-dir>` answers the mechanical half of this list from the built
output, so the reading below is spent on what actually failed rather than on crawling HTML:

```bash
skill-tree site-launch                 # checks the current directory
skill-tree site-launch ./dist          # the built output, not src/; `check` is implied
skill-tree site-launch ./dist --json   # same verdicts, machine-readable
```

Exit `0` = nothing failed, `1` = at least one FAIL, `2` = nothing there to check. Each item
comes back `PASS`, `FAIL`, `NA` (the site doesn't have that thing), or **`MANUAL`** — items
5, 8, and 9 can only be answered against the deployed origin, so it prints the command to run
instead of guessing from disk. Redirect stubs and `404.html` are exempted from the page-level
checks, and a sitemap index's own entries aren't miscounted as pages.

If `skill-tree` isn't on `PATH` in a tool call, run the script directly:
`"${CLAUDE_PLUGIN_ROOT:-${SKILL_TREE_DIR:-$HOME/projects/skill-tree}}/skills/site-launch/scripts/site-launch"`.

The checker is deliberately narrower than the list: it proves absence, not adequacy. It can
tell you an `og:image` tag is missing, not that the image is any good.

## Checklist

### 1. The site knows its own absolute URL.

Feeds, share cards, canonical tags, and sitemaps all need absolute URLs, and every one of
them silently emits broken relative paths until the base URL is configured in one place
(`site:` in the framework config, `PUBLIC_SITE_URL`, whatever the stack calls it). Set it
first — the rest of this list depends on it.

**Check:** grep the built output for `href="/` or `content="/` inside `<link rel="canonical">`,
feed items, and `og:` tags. A leading slash where a domain belongs means the base URL never
reached that template.

### 2. Every page declares a title and a description.

Not a template default repeated on every page. The title is what a tab, a bookmark, a search
result, and a shared link all show; the description is the only prose you control in a search
result. They belong in the shared layout as required parameters, so a new page can't be added
without supplying them.

**Check:** crawl the built output and count distinct `<title>` values against the number of
pages. Fewer distinct titles than pages means some page is wearing the layout's default.

### 3. A shared link renders a card.

Open Graph (`og:title`, `og:description`, `og:image`, `og:url`, `og:type`) plus
`twitter:card` = `summary_large_image`. Without them, a link pasted into Slack, iMessage, or
anywhere else is a bare URL — the single most common thing missing from a hand-built site.

The image is the part people skip. It must be an absolute URL, ~1200×630, and it must exist
at build time. Generating one per page from the page's own title beats one static image for
the whole site, but one static image beats none by a wide margin.

**Check:** don't eyeball the tags — request the deployed URL and confirm the `og:image` URL
returns 200 with an image content-type. A card that references a 404 renders as no card at
all, and the tags look perfectly correct in the source.

### 4. Content that updates has a feed.

Anything appended to over time — a blog, a changelog, release notes — gets an RSS or Atom
feed. It's the one way to follow a site that doesn't route through someone's algorithm, and
it costs one route.

Two halves, and the second is the one that gets forgotten: the feed itself, *and* the
`<link rel="alternate" type="application/rss+xml">` in `<head>` so readers can discover it
from any page. A visible link in the footer as well, since discovery from `<head>` alone
assumes the reader already uses a client that looks.

**Check:** fetch the feed URL and confirm it parses as XML with absolute item links and real
dates. Then confirm the `<head>` link exists on a page that *isn't* the feed's index.

### 5. Analytics that don't require a cookie banner.

Ship something, or you're guessing about every decision after launch. Prefer a
privacy-preserving, no-cookie option — it keeps the site out of consent-banner territory
entirely, which is both a legal and a design win.

Load it deferred, and confirm it does nothing when blocked: a tracker that throws on an
ad-blocked client can take real page scripts down with it.

**Check:** load the site with the tracker's domain blocked and watch the console. Then load it
unblocked and confirm the hit actually lands in the dashboard — a misconfigured site ID fails
completely silently.

### 6. `robots.txt` and a sitemap.

`robots.txt` pointing at an absolute `Sitemap:` URL, and a sitemap listing every page worth
indexing. Generate the sitemap from the same route data the site builds from; a hand-written
one is stale the day after it's written.

If there are preview or staging deployments on a public host, they need their own
`robots.txt` disallowing everything — otherwise the staging copy competes with production in
search results.

**Check:** fetch `/robots.txt` and `/sitemap.xml` on the deployed site. Then check that the
sitemap's URL count matches the number of routes actually built.

### 7. A favicon and a 404 page.

Both are defaults that ship as someone else's: the framework's placeholder icon in every tab,
and the host's generic error page on every bad link. The favicon wants an `.svg` plus an
`.ico` fallback; the 404 wants the site's own layout and a route back to somewhere real.

**Check:** request a URL you know doesn't exist and confirm you get the site's own 404 — and
that it responds with status 404, not 200. A soft-404 gets indexed.

### 8. The response carries security headers.

Frameworks and hosts ship almost none of these — a fresh deploy typically sends `strict-transport-security` and nothing else. The four that cost nothing and need no per-site tuning:
`x-content-type-options: nosniff`, `referrer-policy: strict-origin-when-cross-origin`,
`x-frame-options: DENY`, and `content-security-policy: frame-ancestors 'none'` (the modern
half of the framing pair; send both, old browsers only honour the former).

**Stop there unless the site needs more.** A full CSP with `script-src` has to enumerate the
framework's own inline bootstrap scripts, and getting it wrong doesn't degrade — it blanks the
page. `frame-ancestors` alone has no such failure mode.

`nosniff` is the one with a real side effect: it makes every response's declared
`Content-Type` binding. Check the non-HTML routes — feeds, sitemaps, an XSLT stylesheet, font
and download endpoints — actually declare the right type, or they stop working.

**Check:** `curl -sI` the **deployed** origin, not the dev server, and not within a couple of
minutes of a push — a check against a still-building deploy reports the previous version's
headers and looks like your config didn't apply. Then re-check one non-HTML route.

### 9. It works before you announce it.

Load the deployed site — not the dev server — on a phone-width viewport, cold, with cache
disabled. Confirm: no console errors, no horizontal scroll, external links open correctly,
and forms actually submit somewhere. Then run Lighthouse against the deployed URL and read
the accessibility and SEO panels specifically; they catch missing `lang`, missing `alt`, and
unlabeled controls that no amount of looking at the page will surface.

**Check:** the dev server hides broken absolute URLs, missing build-time assets, and
redirect misconfiguration — all three of which are exactly what this list is about. Every
verification here runs against the deployed origin.

## Applying this to an existing site

Work the list in order and report what's missing before changing anything — items 1 and 2 are
upstream of most of the rest, and fixing 3 before 1 produces share cards pointing at relative
paths. When a site already satisfies an item, say so and move on; don't swap a working
implementation for a different one just because it isn't the one you'd have picked.
