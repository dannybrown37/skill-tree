#!/usr/bin/env bash
set -euo pipefail

mkdir -p posts

cat >style.css <<'CSS'
:root {
  --bg: #fdfcf8;
  --fg: #1d1b16;
  --accent: #b5462a;
  --muted: #6b665c;
}

body {
  background: var(--bg);
  color: var(--fg);
  font: 18px/1.6 Georgia, serif;
  max-width: 38rem;
  margin: 3rem auto;
}

a { color: var(--accent); }
.meta { color: var(--muted); }
CSS

cat >index.html <<'HTML'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Field Notes</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <h1>Field Notes</h1>
  <ul>
    <li><a href="posts/first-frost.html">First frost</a> <span class="meta">2026-09-30</span></li>
  </ul>
</body>
</html>
HTML

cat >posts/first-frost.html <<'HTML'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>First frost</title>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <h1>First frost</h1>
  <p class="meta">2026-09-30</p>
  <p>The tomatoes did not make it.</p>
</body>
</html>
HTML

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
