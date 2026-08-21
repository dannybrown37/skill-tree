"""Tests for the site-launch check CLI."""

import json
from pathlib import Path

import pytest

from site_launch_cli import (
    EXIT_FAILED_CHECK,
    EXIT_OK,
    EXIT_UNUSABLE,
    SiteLaunchError,
    Status,
    check_absolute_base_url,
    check_favicon_and_404,
    check_feed,
    check_robots_and_sitemap,
    check_share_card,
    check_titles_and_descriptions,
    find_pages,
    main,
    manual_checks,
    parse_head,
    run_checks,
)

PAGE = """\
<!doctype html>
<html lang="en">
<head>
<title>Widgets — Acme</title>
<meta name="description" content="We make widgets.">
<link rel="canonical" href="https://acme.test/widgets/">
<meta property="og:url" content="https://acme.test/widgets/">
<link rel="alternate" type="application/rss+xml" href="https://acme.test/feed.xml">
</head>
<body><h1>Widgets</h1></body>
</html>
"""

RELATIVE_PAGE = PAGE.replace('https://acme.test/widgets/', '/widgets/')


def write(root: Path, rel: str, html: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html)
    return path


class TestParseHead:
    def test_reads_title(self) -> None:
        assert parse_head(PAGE).title == 'Widgets — Acme'

    def test_reads_named_meta(self) -> None:
        assert parse_head(PAGE).meta['description'] == 'We make widgets.'

    def test_reads_property_meta(self) -> None:
        assert parse_head(PAGE).meta['og:url'] == 'https://acme.test/widgets/'

    def test_reads_links_by_rel(self) -> None:
        head = parse_head(PAGE)
        assert head.links['canonical'][0] == 'https://acme.test/widgets/'

    def test_reads_lang(self) -> None:
        assert parse_head(PAGE).lang == 'en'

    @pytest.mark.parametrize(
        'html',
        [
            '',
            '<html><head></head></html>',
            '<html><head><title></title><meta content="x"></head></html>',
            '<p>unclosed',
        ],
    )
    def test_survives_degenerate_html(self, html: str) -> None:
        head = parse_head(html)
        assert head.title in (None, '')

    def test_ignores_body_title(self) -> None:
        html = '<head><title>Real</title></head><body><title>No</title>'
        assert parse_head(html).title == 'Real'


class TestFindPages:
    def test_finds_nested_html(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        write(tmp_path, 'widgets/index.html', PAGE)
        assert [page.path for page in find_pages(tmp_path)] == [
            Path('index.html'),
            Path('widgets/index.html'),
        ]

    def test_paths_are_relative_to_root(self, tmp_path: Path) -> None:
        write(tmp_path, 'widgets/index.html', PAGE)
        assert find_pages(tmp_path)[0].path == Path('widgets/index.html')

    def test_ignores_non_html(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        (tmp_path / 'feed.xml').write_text('<rss/>')
        assert [page.path for page in find_pages(tmp_path)] == [
            Path('index.html'),
        ]

    def test_empty_dir_finds_nothing(self, tmp_path: Path) -> None:
        assert find_pages(tmp_path) == []


class TestAbsoluteBaseUrl:
    def test_passes_when_canonical_and_og_are_absolute(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'index.html', PAGE)
        result = check_absolute_base_url(find_pages(tmp_path))
        assert result.status is Status.PASS

    def test_fails_on_root_relative_canonical(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', RELATIVE_PAGE)
        result = check_absolute_base_url(find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert 'index.html' in result.detail

    def test_na_when_no_pages(self, tmp_path: Path) -> None:
        result = check_absolute_base_url(find_pages(tmp_path))
        assert result.status is Status.NA


class TestTitlesAndDescriptions:
    def test_passes_when_every_page_is_distinct(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        write(
            tmp_path,
            'about/index.html',
            PAGE.replace('Widgets — Acme', 'About — Acme').replace(
                'We make widgets.',
                'Who we are.',
            ),
        )
        result = check_titles_and_descriptions(find_pages(tmp_path))
        assert result.status is Status.PASS

    def test_fails_on_duplicate_titles(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        write(tmp_path, 'about/index.html', PAGE)
        result = check_titles_and_descriptions(find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert 'Widgets — Acme' in result.detail

    def test_fails_on_missing_description(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'index.html',
            PAGE.replace(
                '<meta name="description" content="We make widgets.">',
                '',
            ),
        )
        result = check_titles_and_descriptions(find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert 'description' in result.detail.lower()


CARD_TAGS = """\
<meta property="og:title" content="Widgets">
<meta property="og:description" content="We make widgets.">
<meta property="og:image" content="https://acme.test/og/widgets.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
"""

CARD_PAGE = PAGE.replace('</head>', CARD_TAGS + '</head>')

RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Acme</title>
<item>
  <title>Post</title>
  <link>https://acme.test/posts/one/</link>
  <pubDate>Mon, 04 Aug 2025 00:00:00 GMT</pubDate>
</item>
</channel></rss>
"""

SITEMAP = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://acme.test/</loc></url>
<url><loc>https://acme.test/widgets/</loc></url>
</urlset>
"""


class TestShareCard:
    def test_passes_with_the_full_set(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', CARD_PAGE)
        result = check_share_card(find_pages(tmp_path))
        assert result.status is Status.PASS

    @pytest.mark.parametrize(
        ('missing', 'expected'),
        [
            ('og:image', 'og:image'),
            ('og:title', 'og:title'),
            ('twitter:card', 'twitter:card'),
        ],
    )
    def test_fails_when_a_tag_is_missing(
        self,
        tmp_path: Path,
        missing: str,
        expected: str,
    ) -> None:
        stripped = '\n'.join(
            line for line in CARD_PAGE.splitlines() if missing not in line
        )
        write(tmp_path, 'index.html', stripped)
        result = check_share_card(find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert expected in result.detail

    def test_fails_on_wrong_twitter_card_value(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'index.html',
            CARD_PAGE.replace('summary_large_image', 'summary'),
        )
        result = check_share_card(find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert 'summary_large_image' in result.detail

    def test_fails_on_relative_og_image(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'index.html',
            CARD_PAGE.replace('https://acme.test/og/widgets.png', '/og.png'),
        )
        result = check_share_card(find_pages(tmp_path))
        assert result.status is Status.FAIL


class TestFeed:
    def test_na_when_no_feed_exists(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        result = check_feed(tmp_path, find_pages(tmp_path))
        assert result.status is Status.NA

    def test_passes_with_feed_and_head_link(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        (tmp_path / 'feed.xml').write_text(RSS)
        result = check_feed(tmp_path, find_pages(tmp_path))
        assert result.status is Status.PASS

    def test_fails_when_no_page_advertises_it(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'index.html',
            PAGE.replace('rel="alternate"', 'rel="x"'),
        )
        (tmp_path / 'feed.xml').write_text(RSS)
        result = check_feed(tmp_path, find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert 'alternate' in result.detail

    def test_fails_on_relative_item_links(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        (tmp_path / 'feed.xml').write_text(
            RSS.replace('https://acme.test/posts/one/', '/posts/one/'),
        )
        result = check_feed(tmp_path, find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert 'absolute' in result.detail.lower()

    def test_fails_when_items_have_no_dates(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        (tmp_path / 'feed.xml').write_text(
            '\n'.join(
                line for line in RSS.splitlines() if 'pubDate' not in line
            ),
        )
        result = check_feed(tmp_path, find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert 'date' in result.detail.lower()

    def test_finds_an_atom_feed(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        (tmp_path / 'atom.xml').write_text(
            '<feed><entry><link href="https://acme.test/a/"/>'
            '<updated>2025-08-04T00:00:00Z</updated></entry></feed>',
        )
        result = check_feed(tmp_path, find_pages(tmp_path))
        assert result.status is Status.PASS


class TestRobotsAndSitemap:
    def test_passes_when_both_agree_with_the_build(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'index.html', PAGE)
        write(tmp_path, 'widgets/index.html', PAGE)
        (tmp_path / 'robots.txt').write_text(
            'User-agent: *\nSitemap: https://acme.test/sitemap.xml\n',
        )
        (tmp_path / 'sitemap.xml').write_text(SITEMAP)
        result = check_robots_and_sitemap(tmp_path, find_pages(tmp_path))
        assert result.status is Status.PASS

    def test_fails_without_robots(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        (tmp_path / 'sitemap.xml').write_text(SITEMAP)
        result = check_robots_and_sitemap(tmp_path, find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert 'robots.txt' in result.detail

    def test_fails_on_relative_sitemap_directive(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        write(tmp_path, 'widgets/index.html', PAGE)
        (tmp_path / 'robots.txt').write_text('Sitemap: /sitemap.xml\n')
        (tmp_path / 'sitemap.xml').write_text(SITEMAP)
        result = check_robots_and_sitemap(tmp_path, find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert 'absolute' in result.detail.lower()

    def test_fails_when_counts_disagree(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        write(tmp_path, 'widgets/index.html', PAGE)
        write(tmp_path, 'secret/index.html', PAGE)
        (tmp_path / 'robots.txt').write_text(
            'Sitemap: https://acme.test/sitemap.xml\n',
        )
        (tmp_path / 'sitemap.xml').write_text(SITEMAP)
        result = check_robots_and_sitemap(tmp_path, find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert '3' in result.detail

    def test_404_page_is_not_counted_as_a_route(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        write(tmp_path, 'widgets/index.html', PAGE)
        write(tmp_path, '404.html', PAGE)
        (tmp_path / 'robots.txt').write_text(
            'Sitemap: https://acme.test/sitemap.xml\n',
        )
        (tmp_path / 'sitemap.xml').write_text(SITEMAP)
        result = check_robots_and_sitemap(tmp_path, find_pages(tmp_path))
        assert result.status is Status.PASS


class TestFaviconAnd404:
    def test_passes_with_svg_ico_and_404(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        (tmp_path / 'favicon.svg').write_text('<svg/>')
        (tmp_path / 'favicon.ico').write_bytes(b'\x00')
        write(tmp_path, '404.html', PAGE)
        result = check_favicon_and_404(tmp_path, find_pages(tmp_path))
        assert result.status is Status.PASS

    def test_fails_without_a_404_page(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        (tmp_path / 'favicon.svg').write_text('<svg/>')
        (tmp_path / 'favicon.ico').write_bytes(b'\x00')
        result = check_favicon_and_404(tmp_path, find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert '404' in result.detail

    def test_fails_without_any_favicon(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        write(tmp_path, '404.html', PAGE)
        result = check_favicon_and_404(tmp_path, find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert 'favicon' in result.detail.lower()

    def test_accepts_a_favicon_declared_by_link_tag(
        self,
        tmp_path: Path,
    ) -> None:
        write(
            tmp_path,
            'index.html',
            PAGE.replace(
                '</head>',
                '<link rel="icon" href="/icons/mark.svg"></head>',
            ),
        )
        (tmp_path / 'icons').mkdir()
        (tmp_path / 'icons' / 'mark.svg').write_text('<svg/>')
        (tmp_path / 'icons' / 'mark.ico').write_bytes(b'\x00')
        write(tmp_path, '404.html', PAGE)
        result = check_favicon_and_404(tmp_path, find_pages(tmp_path))
        assert result.status is Status.PASS


class TestManualChecks:
    def test_deployed_only_items_are_manual(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        results = manual_checks()
        assert {result.status for result in results} == {Status.MANUAL}
        assert {result.number for result in results} == {5, 8, 9}

    def test_each_manual_check_names_a_command(self) -> None:
        assert all(
            'curl' in r.detail or 'npx' in r.detail for r in manual_checks()
        )


class TestRunChecks:
    def test_covers_every_checklist_item_once(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        results = run_checks(tmp_path)
        assert [result.number for result in results] == list(range(1, 10))

    def test_missing_directory_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(SiteLaunchError, match='not a directory'):
            run_checks(tmp_path / 'nope')

    def test_directory_with_no_html_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(SiteLaunchError, match='no HTML'):
            run_checks(tmp_path)


class TestMain:
    def _site(self, root: Path, *, complete: bool) -> Path:
        write(root, 'index.html', CARD_PAGE if complete else PAGE)
        if complete:
            (root / 'robots.txt').write_text(
                'Sitemap: https://acme.test/sitemap.xml\n',
            )
            (root / 'sitemap.xml').write_text(
                SITEMAP.replace(
                    '<url><loc>https://acme.test/widgets/</loc></url>\n',
                    '',
                ),
            )
            (root / 'favicon.svg').write_text('<svg/>')
            (root / 'favicon.ico').write_bytes(b'\x00')
            write(
                root,
                '404.html',
                CARD_PAGE.replace('Widgets — Acme', 'Not found — Acme'),
            )
        return root

    def test_exit_0_when_nothing_fails(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        root = self._site(tmp_path, complete=True)
        assert main(['check', str(root)]) == EXIT_OK
        assert 'pass' in capsys.readouterr().out.lower()

    def test_exit_1_on_any_failure(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        root = self._site(tmp_path, complete=False)
        assert main(['check', str(root)]) == EXIT_FAILED_CHECK
        assert 'fail' in capsys.readouterr().out.lower()

    def test_manual_items_do_not_fail_the_run(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        root = self._site(tmp_path, complete=True)
        assert main(['check', str(root)]) == EXIT_OK
        assert 'manual' in capsys.readouterr().out.lower()

    def test_json_is_machine_readable(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        root = self._site(tmp_path, complete=True)
        main(['check', str(root), '--json'])
        payload = json.loads(capsys.readouterr().out)
        assert [item['number'] for item in payload['checks']] == list(
            range(1, 10),
        )
        assert payload['checks'][0]['status'] == 'pass'

    def test_bad_directory_exits_2_with_a_message(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert main(['check', str(tmp_path / 'nope')]) == EXIT_UNUSABLE
        assert 'not a directory' in capsys.readouterr().err

    def test_defaults_to_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = self._site(tmp_path, complete=True)
        monkeypatch.chdir(root)
        assert main(['check']) == EXIT_OK

    def test_version_needs_no_arguments(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(['--version'])
        assert excinfo.value.code == 0
        assert 'site-launch' in capsys.readouterr().out


REDIRECT = """\
<html><head>
<meta http-equiv="refresh" content="0; url=/#about">
<title>Redirecting to: /#about</title>
</head><body></body></html>
"""


class TestRedirectStubs:
    """A redirect stub is plumbing, not a page anyone lands on."""

    def test_parsed_as_a_redirect(self) -> None:
        assert parse_head(REDIRECT).is_redirect
        assert not parse_head(PAGE).is_redirect

    def test_exempt_from_titles_and_descriptions(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'index.html', PAGE)
        write(tmp_path, 'about/index.html', REDIRECT)
        result = check_titles_and_descriptions(find_pages(tmp_path))
        assert result.status is Status.PASS

    def test_exempt_from_the_share_card(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', CARD_PAGE)
        write(tmp_path, 'about/index.html', REDIRECT)
        result = check_share_card(find_pages(tmp_path))
        assert result.status is Status.PASS

    def test_not_counted_as_a_sitemap_route(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        write(tmp_path, 'widgets/index.html', PAGE)
        write(tmp_path, 'about/index.html', REDIRECT)
        (tmp_path / 'robots.txt').write_text(
            'Sitemap: https://acme.test/sitemap.xml\n',
        )
        (tmp_path / 'sitemap.xml').write_text(SITEMAP)
        result = check_robots_and_sitemap(tmp_path, find_pages(tmp_path))
        assert result.status is Status.PASS

    def test_a_site_of_only_redirects_is_still_an_error(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'about/index.html', REDIRECT)
        with pytest.raises(SiteLaunchError, match='only redirect'):
            run_checks(tmp_path)


SITEMAP_INDEX = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://acme.test/sitemap-0.xml</loc></sitemap>
</sitemapindex>
"""


class TestSitemapIndex:
    """A sitemap index lists sitemaps, not pages."""

    def test_index_locs_are_not_counted_as_pages(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        write(tmp_path, 'widgets/index.html', PAGE)
        (tmp_path / 'robots.txt').write_text(
            'Sitemap: https://acme.test/sitemap.xml\n',
        )
        (tmp_path / 'sitemap.xml').write_text(SITEMAP_INDEX)
        (tmp_path / 'sitemap-0.xml').write_text(SITEMAP)
        result = check_robots_and_sitemap(tmp_path, find_pages(tmp_path))
        assert result.status is Status.PASS

    def test_an_index_pointing_at_nothing_fails(self, tmp_path: Path) -> None:
        write(tmp_path, 'index.html', PAGE)
        (tmp_path / 'robots.txt').write_text(
            'Sitemap: https://acme.test/sitemap.xml\n',
        )
        (tmp_path / 'sitemap.xml').write_text(SITEMAP_INDEX)
        result = check_robots_and_sitemap(tmp_path, find_pages(tmp_path))
        assert result.status is Status.FAIL
        assert '0 URL' in result.detail


@pytest.fixture
def default_target(tmp_path: Path) -> Path:
    write(tmp_path, 'index.html', CARD_PAGE)
    (tmp_path / 'robots.txt').write_text(
        'Sitemap: https://acme.test/sitemap.xml\n',
    )
    (tmp_path / 'sitemap.xml').write_text(
        SITEMAP.replace(
            '<url><loc>https://acme.test/widgets/</loc></url>\n',
            '',
        ),
    )
    (tmp_path / 'favicon.svg').write_text('<svg/>')
    (tmp_path / 'favicon.ico').write_bytes(b'\x00')
    write(
        tmp_path,
        '404.html',
        CARD_PAGE.replace('Widgets — Acme', 'Not found — Acme'),
    )
    return tmp_path


class TestDefaultCommand:
    """`site-launch <dir>` must work without naming the only subcommand."""

    def test_bare_invocation_checks_the_current_directory(
        self,
        default_target: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(default_target)
        assert main([]) == EXIT_OK
        assert 'PASS' in capsys.readouterr().out

    def test_version_still_reaches_the_parser(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['--version'])
        assert exit_info.value.code == EXIT_OK

    def test_help_still_reaches_the_parser(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['--help'])
        assert exit_info.value.code == EXIT_OK

    def test_explicit_subcommand_still_works(
        self,
        default_target: Path,
    ) -> None:
        assert main(['check', str(default_target)]) == EXIT_OK

    def test_directory_without_subcommand(
        self,
        default_target: Path,
    ) -> None:
        assert main([str(default_target)]) == EXIT_OK

    def test_flag_without_subcommand(
        self,
        default_target: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert main([str(default_target), '--json']) == EXIT_OK
        assert json.loads(capsys.readouterr().out)['checks']

    def test_unknown_flag_is_still_an_error(
        self,
        default_target: Path,
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main([str(default_target), '--nope'])
        assert exit_info.value.code != EXIT_OK
