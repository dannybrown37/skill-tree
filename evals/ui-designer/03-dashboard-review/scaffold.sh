#!/usr/bin/env bash
set -euo pipefail

cat >index.html <<'EOF'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Employees · Crewbase</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <main>
    <header class="toolbar">
      <h1>Employees</h1>
      <div class="filters">
        <button class="chip">Department: All</button>
        <button class="chip">Status: All</button>
        <button class="chip">Location: All</button>
      </div>
      <div class="tools">
        <button class="icon-btn">⟳</button>
        <button class="icon-btn">⤓</button>
        <button class="icon-btn">⚙</button>
      </div>
    </header>
    <table>
      <thead>
        <tr><th>Name</th><th>Department</th><th>Status</th><th>Hours this week</th><th>Actions</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>Ana Okafor</td><td>Engineering</td><td>Active</td><td>38.5</td>
          <td class="actions"><button>Share</button><button>Copy ID</button><button>Remove</button></td>
        </tr>
        <tr>
          <td>Ben Halvorsen</td><td>Support</td><td>Inactive</td><td>0</td>
          <td class="actions"><button>Share</button><button>Copy ID</button><button>Remove</button></td>
        </tr>
        <tr>
          <td>Chloé Marchetti</td><td>Engineering</td><td>On leave</td><td>4</td>
          <td class="actions"><button>Share</button><button>Copy ID</button><button>Remove</button></td>
        </tr>
        <tr>
          <td>Dev Raman</td><td>Sales</td><td>Active</td><td>112.25</td>
          <td class="actions"><button>Share</button><button>Copy ID</button><button>Remove</button></td>
        </tr>
        <tr>
          <td>Eun-ji Park</td><td>Support</td><td>Active</td><td>40</td>
          <td class="actions"><button>Share</button><button>Copy ID</button><button>Remove</button></td>
        </tr>
      </tbody>
    </table>
  </main>
</body>
</html>
EOF

cat >style.css <<'EOF'
:root {
  --font-body: "Inter", sans-serif;
  --surface: #f7f6f3;
  --surface-raised: #fdfcfa;
  --text: #1d1c1a;
  --text-muted: #6b6862;
  --border: #e2dfd8;
  --accent: #2f5d50;
  --accent-contrast: #f7f6f3;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
}
body {
  font-family: var(--font-body);
  color: var(--text);
  background: var(--surface);
  margin: 0;
}
main {
  max-width: 1100px;
  margin: 0 auto;
  padding: var(--space-8) var(--space-6);
}
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}
.filters,
.tools {
  display: flex;
  gap: var(--space-2);
}
.tools {
  margin-left: auto;
}
.chip {
  background: var(--accent);
  color: var(--accent-contrast);
  border: 0;
  border-radius: 999px;
  padding: var(--space-1) var(--space-3);
}
.icon-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: var(--space-2);
}
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface-raised);
}
th,
td {
  text-align: left;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
}
th {
  color: var(--text-muted);
  font-weight: 500;
}
.actions {
  display: flex;
  gap: var(--space-2);
}
.actions button {
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: var(--space-1) var(--space-3);
}
EOF
