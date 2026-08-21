#!/usr/bin/env python3
"""Deterministic half of the site-launch checklist, over built output.

Every check here answers from files on disk. The checks the skill insists
must run against the *deployed* origin -- header responses, whether the
og:image actually 200s, soft-404s -- are reported as MANUAL with the
command to run, because a dev-server answer to those is worse than none.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from html.parser import HTMLParser
from pathlib import Path

HTML_SUFFIXES = frozenset({'.html', '.htm'})

# Where a leading `/` means the base URL never reached the template.
ABSOLUTE_REQUIRED_META = ('og:url', 'og:image')
ABSOLUTE_REQUIRED_LINKS = ('canonical',)


class Status(Enum):
    """Outcome of one checklist item."""

    PASS = 'pass'  # noqa: S105
    FAIL = 'fail'
    NA = 'n/a'
    MANUAL = 'manual'


@dataclass(frozen=True)
class CheckResult:
    """One checklist item's verdict, with what to do about it."""

    number: int
    title: str
    status: Status
    detail: str


@dataclass
class Head:
    """The parts of a `<head>` this checklist cares about."""

    title: str | None = None
    lang: str | None = None
    is_redirect: bool = False
    meta: dict[str, str] = field(default_factory=dict)
    links: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Page:
    """A built HTML file and its parsed head."""

    path: Path
    head: Head


class _HeadParser(HTMLParser):
    """Collects head metadata, tolerating whatever a builder emitted.

    `convert_charrefs` is on, so titles come back as text rather than as
    entities -- a duplicate-title check comparing `&mdash;` against `-'
    would report differences nobody made.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.head = Head()
        self.title_parts: list[str] = []
        self._in_head = True
        self._in_title = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {name: value or '' for name, value in attrs}

        if tag == 'meta' and values.get('http-equiv', '').lower() == 'refresh':
            self.head.is_redirect = True

        if tag == 'html':
            self.head.lang = values.get('lang') or None
        elif tag == 'body':
            self._in_head = False
        elif tag == 'title' and self._in_head:
            self._in_title = True
        elif tag == 'meta':
            key = values.get('name') or values.get('property')
            if key:
                self.head.meta[key] = values.get('content', '')
        elif tag == 'link':
            href = values.get('href')
            if href:
                for rel in values.get('rel', '').split():
                    self.head.links.setdefault(rel.lower(), []).append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == 'title':
            self._in_title = False
        elif tag == 'head':
            self._in_head = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)


def parse_head(html: str) -> Head:
    """Parse a page's head. Malformed input yields an empty Head."""
    parser = _HeadParser()
    parser.feed(html)
    parser.close()
    if parser.title_parts:
        parser.head.title = ''.join(parser.title_parts).strip()
    return parser.head


def find_pages(root: Path) -> list[Page]:
    """Every built HTML page under `root`, sorted, path relative to it."""
    return [
        Page(
            path=path.relative_to(root),
            head=parse_head(path.read_text(errors='replace')),
        )
        for path in sorted(root.rglob('*'))
        if path.is_file() and path.suffix.lower() in HTML_SUFFIXES
    ]


def _is_relative(url: str) -> bool:
    """A URL that needed a domain and didn't get one."""
    return url.startswith('/')


def check_absolute_base_url(pages: list[Page]) -> CheckResult:
    """1. The site knows its own absolute URL."""
    if not pages:
        return CheckResult(
            1,
            'Absolute base URL',
            Status.NA,
            'No pages found.',
        )

    offenders: list[str] = []
    for page in pages:
        for key in ABSOLUTE_REQUIRED_META:
            value = page.head.meta.get(key, '')
            if value and _is_relative(value):
                offenders.append(f'{page.path}: {key}={value}')
        for rel in ABSOLUTE_REQUIRED_LINKS:
            offenders.extend(
                f'{page.path}: rel={rel} href={href}'
                for href in page.head.links.get(rel, [])
                if _is_relative(href)
            )

    if offenders:
        return CheckResult(
            1,
            'Absolute base URL',
            Status.FAIL,
            'Relative where a domain belongs:\n  ' + '\n  '.join(offenders),
        )
    return CheckResult(
        1,
        'Absolute base URL',
        Status.PASS,
        'Canonical and og: URLs are absolute.',
    )


def check_titles_and_descriptions(pages: list[Page]) -> CheckResult:
    """2. Every page declares a distinct title and description."""
    pages = landing_pages(pages)
    if not pages:
        return CheckResult(
            2,
            'Titles and descriptions',
            Status.NA,
            'No pages found.',
        )

    problems: list[str] = []
    by_title: dict[str, list[Path]] = defaultdict(list)

    for page in pages:
        if page.head.title:
            by_title[page.head.title].append(page.path)
        else:
            problems.append(f'{page.path}: no <title>')
        if not page.head.meta.get('description', '').strip():
            problems.append(f'{page.path}: no meta description')

    problems.extend(
        f'duplicate title {title!r}: ' + ', '.join(str(path) for path in paths)
        for title, paths in by_title.items()
        if len(paths) > 1
    )

    if problems:
        return CheckResult(
            2,
            'Titles and descriptions',
            Status.FAIL,
            'Problems:\n  ' + '\n  '.join(problems),
        )
    return CheckResult(
        2,
        'Titles and descriptions',
        Status.PASS,
        f'{len(pages)} pages, {len(by_title)} distinct titles.',
    )


class SiteLaunchError(Exception):
    """The build directory can't be checked at all."""


CARD_META = (
    'og:title',
    'og:description',
    'og:image',
    'og:url',
    'og:type',
)
TWITTER_CARD = 'summary_large_image'

FEED_SUFFIXES = frozenset({'.xml'})
FEED_STEMS = frozenset({'feed', 'atom', 'rss', 'index'})
FEED_MIME = 'application/rss+xml'
FEED_MIMES = (FEED_MIME, 'application/atom+xml')

NOT_A_ROUTE = frozenset({Path('404.html')})
ICON_RELS = ('icon', 'shortcut', 'apple-touch-icon')
FAVICON_STEMS = ('favicon',)

# Feeds and sitemaps are read with regexes rather than an XML parser: the
# only things wanted are `<loc>`, item links, and dates, and a regex can't
# be walked into entity expansion by a file some generator produced.
LOC_RE = re.compile(r'<loc>\s*([^<\s]+)\s*</loc>', re.IGNORECASE)
SITEMAP_INDEX_RE = re.compile(r'<sitemapindex\b', re.IGNORECASE)
ITEM_RE = re.compile(r'<(item|entry)\b.*?</\1>', re.IGNORECASE | re.DOTALL)
LINK_TEXT_RE = re.compile(r'<link[^>]*>\s*([^<\s]+)\s*</link>', re.IGNORECASE)
LINK_HREF_RE = re.compile(r'<link[^>]*\bhref=["\']([^"\']+)', re.IGNORECASE)
DATE_RE = re.compile(
    r'<(pubDate|published|updated|dc:date)\b[^>]*>\s*\S',
    re.IGNORECASE,
)


def check_share_card(pages: list[Page]) -> CheckResult:
    """3. A shared link renders a card."""
    pages = landing_pages(pages)
    if not pages:
        return CheckResult(3, 'Share card', Status.NA, 'No pages found.')

    problems: list[str] = []
    for page in pages:
        missing = [key for key in CARD_META if not page.head.meta.get(key)]
        if missing:
            problems.append(f'{page.path}: missing {", ".join(missing)}')

        image = page.head.meta.get('og:image', '')
        if image and _is_relative(image):
            problems.append(f'{page.path}: og:image is relative ({image})')

        card = page.head.meta.get('twitter:card', '')
        if card != TWITTER_CARD:
            problems.append(
                f'{page.path}: twitter:card is {card or "absent"!r}, '
                f'want {TWITTER_CARD!r}',
            )

    if problems:
        return CheckResult(
            3,
            'Share card',
            Status.FAIL,
            'Problems:\n  ' + '\n  '.join(problems),
        )
    return CheckResult(
        3,
        'Share card',
        Status.PASS,
        'Card tags present on every page. Confirm the og:image URL 200s '
        'on the deployed origin -- a card pointing at a 404 renders as no '
        'card at all, and the tags look correct in the source.',
    )


def find_feeds(root: Path) -> list[Path]:
    """Files that look like a syndication feed, by name and by root tag."""
    return [
        path
        for path in sorted(root.rglob('*'))
        if path.is_file()
        and path.suffix.lower() in FEED_SUFFIXES
        and path.stem.lower() in FEED_STEMS
        and re.search(r'<(rss|feed)\b', path.read_text(errors='replace'))
    ]


def check_feed(root: Path, pages: list[Page]) -> CheckResult:
    """4. Content that updates has a feed."""
    feeds = find_feeds(root)
    if not feeds:
        return CheckResult(
            4,
            'Feed',
            Status.NA,
            'No feed in the build. Required only if something here is '
            'appended to over time (blog, changelog, release notes).',
        )

    problems: list[str] = []
    for feed in feeds:
        text = feed.read_text(errors='replace')
        items = ITEM_RE.findall(text)
        entries = ITEM_RE.finditer(text)
        if not items:
            problems.append(f'{feed.name}: no items')
            continue
        for entry in entries:
            body = entry.group(0)
            link_match = LINK_TEXT_RE.search(body) or LINK_HREF_RE.search(body)
            link = link_match.group(1) if link_match else ''
            if not link:
                problems.append(f'{feed.name}: an item has no link')
            elif not link.startswith(('http://', 'https://')):
                problems.append(
                    f'{feed.name}: item link is not absolute ({link})',
                )
            if not DATE_RE.search(body):
                problems.append(f'{feed.name}: an item has no date')

    if not any(_advertises_feed(page) for page in pages):
        problems.append(
            'no page carries <link rel="alternate" '
            f'type="{FEED_MIME}"> in <head>',
        )

    if problems:
        return CheckResult(
            4,
            'Feed',
            Status.FAIL,
            'Problems:\n  ' + '\n  '.join(problems),
        )
    return CheckResult(
        4,
        'Feed',
        Status.PASS,
        f'{len(feeds)} feed(s), absolute item links and dates, discoverable '
        'from <head>.',
    )


def _advertises_feed(page: Page) -> bool:
    """Whether this page's head points a reader at a feed.

    Matched on the whole `<link rel="alternate">` set rather than on href,
    because the type attribute is what a reader keys off and the href may
    be absolute, root-relative, or a sibling path.
    """
    return bool(page.head.links.get('alternate'))


def landing_pages(pages: list[Page]) -> list[Page]:
    """Pages a visitor actually lands on.

    Redirect stubs (`<meta http-equiv="refresh">`) are build plumbing --
    holding them to a title, a description, and a share card reports work
    nobody should do, and counting them as routes makes the sitemap look
    permanently short.
    """
    return [page for page in pages if not page.head.is_redirect]


def _indexable(pages: list[Page]) -> list[Page]:
    """Pages that belong in a sitemap."""
    return [
        page for page in landing_pages(pages) if page.path not in NOT_A_ROUTE
    ]


def check_robots_and_sitemap(root: Path, pages: list[Page]) -> CheckResult:
    """6. robots.txt and a sitemap."""
    robots = root / 'robots.txt'
    sitemaps = sorted(root.glob('sitemap*.xml'))
    problems: list[str] = []

    if not robots.is_file():
        problems.append('no robots.txt')
    else:
        directives = [
            line.split(':', 1)[1].strip()
            for line in robots.read_text(errors='replace').splitlines()
            if line.lower().startswith('sitemap:')
        ]
        if not directives:
            problems.append('robots.txt has no Sitemap: directive')
        else:
            problems.extend(
                f'robots.txt Sitemap: is not absolute ({directive})'
                for directive in directives
                if not directive.startswith(('http://', 'https://'))
            )

    if not sitemaps:
        problems.append('no sitemap.xml')
    else:
        # A sitemap index's <loc>s are sitemap URLs, not page URLs --
        # counting them makes the build look one page short per index.
        listed = {
            loc
            for sitemap in sitemaps
            for text in [sitemap.read_text(errors='replace')]
            if not SITEMAP_INDEX_RE.search(text)
            for loc in LOC_RE.findall(text)
        }
        routes = _indexable(pages)
        if len(listed) != len(routes):
            problems.append(
                f'sitemap lists {len(listed)} URL(s) but the build has '
                f'{len(routes)} page(s)',
            )

    if problems:
        return CheckResult(
            6,
            'robots.txt and sitemap',
            Status.FAIL,
            'Problems:\n  ' + '\n  '.join(problems),
        )
    return CheckResult(
        6,
        'robots.txt and sitemap',
        Status.PASS,
        'robots.txt points at an absolute Sitemap: URL, and the sitemap '
        'matches the built routes.',
    )


def check_favicon_and_404(root: Path, pages: list[Page]) -> CheckResult:
    """7. A favicon and a 404 page."""
    problems: list[str] = []

    declared = [
        href
        for page in pages
        for rel in ICON_RELS
        for href in page.head.links.get(rel, [])
    ]
    stems = {Path(href.split('?')[0]).with_suffix('') for href in declared}
    stems.update(Path(stem) for stem in FAVICON_STEMS)

    def _exists(stem: Path, suffix: str) -> bool:
        relative = str(stem).lstrip('/')
        return (root / relative).with_suffix(suffix).is_file()

    if not any(
        _exists(stem, '.svg') or _exists(stem, '.ico') for stem in stems
    ):
        problems.append('no favicon (.svg or .ico) in the build')
    elif not any(
        _exists(stem, '.svg') and _exists(stem, '.ico') for stem in stems
    ):
        problems.append('favicon has no .ico fallback beside its .svg')

    if not (root / '404.html').is_file():
        problems.append('no 404.html in the build')

    if problems:
        return CheckResult(
            7,
            'Favicon and 404',
            Status.FAIL,
            'Problems:\n  ' + '\n  '.join(problems),
        )
    return CheckResult(
        7,
        'Favicon and 404',
        Status.PASS,
        'Favicon (.svg + .ico) and a 404 page are built. Confirm the '
        'deployed 404 answers with status 404, not 200 -- a soft-404 gets '
        'indexed.',
    )


def manual_checks() -> list[CheckResult]:
    """The items that only a deployed origin can answer.

    Reported rather than skipped: a dev-server answer to any of these is
    worse than no answer, since all three failure modes this list exists
    for -- broken absolute URLs, missing build-time assets, redirect
    misconfiguration -- are exactly what the dev server hides.
    """
    return [
        CheckResult(
            5,
            'Analytics',
            Status.MANUAL,
            'curl -s https://<origin>/ | grep -iE '
            "'analytics|plausible|umami|counter'  -- confirm it ships and "
            'is deferred. Then load the page with the tracker domain '
            'blocked (console must stay clean) and unblocked (the hit must '
            'land in the dashboard -- a bad site ID fails silently).',
        ),
        CheckResult(
            8,
            'Security headers',
            Status.MANUAL,
            'curl -sI https://<origin>/ | grep -iE '
            "'x-content-type-options|referrer-policy|x-frame-options|"
            "content-security-policy'\n  Then re-check one non-HTML route "
            '(feed, sitemap) -- nosniff makes its Content-Type binding.',
        ),
        CheckResult(
            9,
            'Works before announcing',
            Status.MANUAL,
            'npx lighthouse https://<origin>/ --view (read the a11y and SEO '
            'panels), plus a cold phone-width load: no console errors, no '
            'horizontal scroll, forms submit.',
        ),
    ]


def run_checks(root: Path) -> list[CheckResult]:
    """Every checklist item, in the order the skill states them."""
    if not root.is_dir():
        message = f'{root} is not a directory'
        raise SiteLaunchError(message)

    pages = find_pages(root)
    if not pages:
        message = (
            f'no HTML files under {root} -- point this at the build output '
            f'directory (dist/, build/, _site/), not the source tree'
        )
        raise SiteLaunchError(message)

    if not landing_pages(pages):
        message = (
            f'{root} contains only redirect stubs -- there is no page here '
            f'to check'
        )
        raise SiteLaunchError(message)

    return sorted(
        [
            check_absolute_base_url(pages),
            check_titles_and_descriptions(pages),
            check_share_card(pages),
            check_feed(root, pages),
            check_robots_and_sitemap(root, pages),
            check_favicon_and_404(root, pages),
            *manual_checks(),
        ],
        key=lambda result: result.number,
    )


STATUS_ORDER = (Status.FAIL, Status.MANUAL, Status.NA, Status.PASS)
EXIT_OK = 0
EXIT_FAILED_CHECK = 1
EXIT_UNUSABLE = 2


def version() -> str:
    """This checkout's plugin version, or `unknown` outside one.

    `--version` has to work with no config and no credentials, so a
    missing or unreadable manifest is an answer rather than a crash.
    """
    manifest = (
        Path(__file__).resolve().parents[3] / '.claude-plugin' / 'plugin.json'
    )
    try:
        return str(json.loads(manifest.read_text())['version'])
    except (OSError, ValueError, KeyError):
        return 'unknown'


def render(results: list[CheckResult]) -> str:
    """Human-readable report, worst first within the checklist order."""
    lines: list[str] = []
    for status in STATUS_ORDER:
        matching = [result for result in results if result.status is status]
        if not matching:
            continue
        lines.append(f'{status.value.upper()}')
        for result in matching:
            lines.append(f'  {result.number}. {result.title}')
            lines.extend(f'     {line}' for line in result.detail.splitlines())
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def as_json(results: list[CheckResult]) -> str:
    """The same report, for a caller that wants to branch on it."""
    return json.dumps(
        {
            'checks': [
                {
                    'number': result.number,
                    'title': result.title,
                    'status': result.status.value,
                    'detail': result.detail,
                }
                for result in results
            ],
        },
        indent=2,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. 0 clean, 1 a check failed, 2 nothing to check."""
    parser = argparse.ArgumentParser(
        prog='site-launch',
        description="The site-launch checklist's deterministic half.",
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'site-launch {version()}',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    check = subparsers.add_parser(
        'check',
        help='run the checklist over a build output directory',
    )
    check.add_argument(
        'directory',
        nargs='?',
        default='.',
        type=Path,
        help='build output (dist/, build/, _site/); defaults to cwd',
    )
    check.add_argument(
        '--json',
        action='store_true',
        dest='as_json',
        help='machine-readable output',
    )

    args = parser.parse_args(argv)

    try:
        results = run_checks(args.directory)
    except SiteLaunchError as error:
        print(f'site-launch: {error}', file=sys.stderr)
        return EXIT_UNUSABLE

    print(as_json(results) if args.as_json else render(results), end='')

    failed = any(result.status is Status.FAIL for result in results)
    return EXIT_FAILED_CHECK if failed else EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
