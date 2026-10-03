#!/usr/bin/env bash
# A hand-written static blog in public/, deployed as-is to the domain in
# public/CNAME. `good` passes every automated site-launch check; the other
# variants break specific items on top of it.
#
#   site.sh good        clean control
#   site.sh gaps        relative URLs, no twitter:card, about has no
#                       description, no robots.txt/sitemap, no feed
#   site.sh blank-card  relative og:image/og:url, no twitter:card
set -euo pipefail

variant="${1:?usage: site.sh good|gaps|blank-card}"
origin="https://notes.example.com"

mkdir -p public/posts

page() {
	local path="$1" title="$2" description="$3" type="$4" body="$5"
	local url="${origin}/${path%index.html}"
	cat >"public/${path}" <<HTML
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${title}</title>
  <meta name="description" content="${description}">
  <link rel="canonical" href="${url}">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="alternate" type="application/rss+xml" title="Field Notes" href="${origin}/feed.xml">
  <meta property="og:title" content="${title}">
  <meta property="og:description" content="${description}">
  <meta property="og:image" content="${origin}/og.png">
  <meta property="og:url" content="${url}">
  <meta property="og:type" content="${type}">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <header class="site-header"><a href="/">Field Notes</a> · <a href="/about.html">About</a></header>
  <main>
${body}
  </main>
  <footer><a href="/feed.xml">RSS</a></footer>
</body>
</html>
HTML
}

page index.html "Field Notes" "Short essays on building small, durable software." website \
	'    <h1>Field Notes</h1>
    <ul>
      <li><a href="/posts/second-wind.html">Second wind</a></li>
      <li><a href="/posts/first-light.html">First light</a></li>
    </ul>'
page about.html "About · Field Notes" "Who writes Field Notes, and why." website \
	'    <h1>About</h1>
    <p>One person, writing occasionally.</p>'
page posts/first-light.html "First light · Field Notes" "Why the first version should be embarrassingly small." article \
	'    <h1>First light</h1>
    <p>Ship the smallest thing that can be wrong in public.</p>'
page posts/second-wind.html "Second wind · Field Notes" "What changes the second time you build the same tool." article \
	'    <h1>Second wind</h1>
    <p>The rewrite is where the real requirements show up.</p>'

page 404.html "Not found · Field Notes" "This page does not exist." website \
	'    <h1>Not found</h1>
    <p><a href="/">Back to the front page</a></p>'

cat >public/style.css <<'CSS'
body { max-width: 38rem; margin: 0 auto; padding: 0 1rem; font: 1.05rem/1.6 Georgia, serif; }
.site-header { padding: 1rem 0; border-bottom: 1px solid #ddd; }
CSS

cat >public/feed.xml <<XML
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Field Notes</title>
    <link>${origin}/</link>
    <description>Short essays on building small, durable software.</description>
    <item>
      <title>Second wind</title>
      <link>${origin}/posts/second-wind.html</link>
      <pubDate>Tue, 15 Sep 2026 09:00:00 GMT</pubDate>
    </item>
    <item>
      <title>First light</title>
      <link>${origin}/posts/first-light.html</link>
      <pubDate>Mon, 03 Aug 2026 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
XML

cat >public/robots.txt <<TXT
User-agent: *
Allow: /

Sitemap: ${origin}/sitemap.xml
TXT

cat >public/sitemap.xml <<XML
<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>${origin}/</loc></url>
  <url><loc>${origin}/about.html</loc></url>
  <url><loc>${origin}/posts/first-light.html</loc></url>
  <url><loc>${origin}/posts/second-wind.html</loc></url>
</urlset>
XML

cat >public/favicon.svg <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="#2b6"/></svg>
SVG
# Real, decodable images: a stub file is a genuine defect the agent will
# rightly flag, which turns the clean control into a false-positive trap.
python3 - <<'PY'
import struct
import zlib
from pathlib import Path


def png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + bytes(rgb) * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * height, 9))
        + chunk(b"IEND", b"")
    )


Path("public/og.png").write_bytes(png(1200, 630, (34, 102, 68)))
icon = png(32, 32, (34, 187, 102))
header = struct.pack("<HHH", 0, 1, 1)
entry = struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(icon), 6 + 16)
Path("public/favicon.ico").write_bytes(header + entry + icon)
PY
echo "notes.example.com" >public/CNAME

cat >README.md <<'MD'
# Field Notes

A hand-written static blog. There is no build step: `public/` is deployed
as-is to GitHub Pages at the domain in `public/CNAME`.
MD

html=(public/index.html public/about.html public/posts/*.html)
case "${variant}" in
good) ;;
gaps)
	sed -i -E \
		-e "s#${origin}/(og\.png|[^\"]*\.html|)\"#/\1\"#g" \
		-e '/twitter:card/d' \
		-e '/rel="alternate"/d' \
		"${html[@]}"
	sed -i -e '/name="description"/d' public/about.html
	sed -i -e '/feed\.xml/d' "${html[@]}"
	rm public/feed.xml public/robots.txt public/sitemap.xml
	;;
blank-card)
	sed -i -E \
		-e "/og:(image|url)/s#${origin}/#/#" \
		-e '/twitter:card/d' \
		"${html[@]}"
	;;
*)
	echo "unknown variant: ${variant}" >&2
	exit 2
	;;
esac

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
