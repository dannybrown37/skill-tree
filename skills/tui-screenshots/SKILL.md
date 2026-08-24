---
name: tui-screenshots
description: Invoke when generating, refreshing, or fixing screenshots of a terminal UI for docs or a README — "regenerate the screenshots", "the README screenshots are stale", "get a picture of the TUI", "screenshot every tab", "capture the app for the docs". Covers driving a Textual/TUI app headlessly against seeded fake data and exporting SVG. Not for reading a screenshot the user took — that is `screenshot`.
---

# TUI screenshots

Docs screenshots of a terminal app go stale silently. Nothing fails, nothing lints — the
README just shows an app that no longer exists. This is the workflow that makes regenerating
them a single command instead of an afternoon.

Do not reach for a desktop screen capture. Photographing a real terminal window bakes in the
user's font, theme, window size, and whatever real data was on screen. Drive the app instead.

## The shape

Four pieces, in order. Skipping any one of them is where these efforts usually fail:

1. **A fake data source.** Never screenshot real data — it is the user's private life, and it
   also produces a different picture every run.
2. **A headless driver.** Run the app in-process at a fixed terminal size.
3. **An export step.** Write a vector image per screen.
4. **A drift guard.** Something that fails when a new screen exists and no one screenshotted it.

### 1. Fake data, in a real store

The tempting shortcut is to mock the data layer. Resist it: a mock screenshots the mock, not
the app, and it drifts from the real schema without telling you.

Seed a **real but separate store** instead — a demo database, a scratch directory, a throwaway
namespace. Then point the app at it with the same environment variable a real user would set.
The app has no idea it is being screenshotted, so the picture is honest.

Rules for the seed script:

- It must **never** write to the real store. Take the real store's ID only to find out where to
  put the sibling demo one.
- Cache the demo store's ID in a **gitignored** file, so a rerun reseeds rather than piling up
  a new demo store every time.
- Make the fake data cover **every screen**, including the empty and the crowded case. A tab
  that is empty in the demo data screenshots as a blank box, which teaches the reader nothing.
- Fictional names only. "Call Rachel about the mortgage" is fine; a real contact is not.

### 2. Driving it headlessly

For **Textual**, the test harness is the driver — no extra dependency:

```python
app = MyApp()
async with app.run_test(size=(130, 45)) as pilot:
    await pilot.pause(2)          # let async/threaded data loads land
    tabs = app.query_one('#tabs', TabbedContent)
    for tab_id, name in TABS:
        tabs.active = tab_id
        await pilot.pause(0.5)
        Path(f'docs/screenshots/{name}.svg').write_text(
            app.export_screenshot(title='app'),
        )
```

Two failure modes account for nearly every bad capture:

- **Screenshotting before the data arrives.** Anything loading on a worker thread or a network
  call is still a spinner at frame zero. Pause generously once after mount, and again after
  each navigation. A slow script is cheaper than eight screenshots of a loading state.
- **A variable terminal size.** Pin it. `size=(130, 45)` is a good wide-docs default. If the
  size changes between runs, every image in the diff churns and review becomes useless.

For a **non-Textual** TUI, the equivalents are `asciinema rec` + `agg` for a moving picture, or
`termtosvg` for a still. Prefer the app's own harness whenever it has one — anything that
records a real terminal reintroduces the font and theme problem.

### 3. Export SVG, not PNG

SVG is text, so a diff shows what actually changed, it stays sharp at any width, and the
reader can select the text. GitHub renders it inline in a README via `<img src="...">`.

One caveat: GitHub strips scripts and external references from SVG. Textual's export is
self-contained, so this is fine — but do not hand-edit an exported file to pull in a font.

### 4. The drift guard

This is the part everyone skips, and it is the reason the screenshots were stale in the first
place. A hardcoded list of screens **will** fall behind the app.

Best: **derive the screen list from the app**, not from a constant. Query the real widget tree
for the tabs and iterate whatever is there. A new tab then screenshots itself.

If a hardcoded list is unavoidable, add a test that asserts the list matches the app's actual
screens, so adding a screen fails the suite until someone captures it.

## Wiring it up

Two scripts, chained by an ID the first one prints:

```
seed_demo_data.py  ──prints demo store id──▶  capture_screenshots.py  ──▶  docs/screenshots/*.svg
```

Keep them as two commands, not one. Seeding hits the network hard and rarely needs redoing;
capture gets rerun over and over while you fix a layout.

Document the chain in the repo's own `CLAUDE.md` or a project skill, including the exact
environment variables. The whole point is that the next person does not have to rediscover it.

## Before you finish

- Look at the images. Read one of the SVGs, or open the directory — a capture that "succeeded"
  can still be eight pictures of an empty tab.
- Check the README references every image, and every image is referenced.
- Say plainly in the README that the data is fictional.
