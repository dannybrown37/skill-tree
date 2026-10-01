#!/usr/bin/env bash
set -euo pipefail

cat >index.html <<'EOF'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ledgerly</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <section class="hero">
    <h1>Bookkeeping, simplified.</h1>
    <p>Ledgerly is the all-in-one platform for modern small businesses.</p>
    <a class="btn" href="#signup">Get started</a>
  </section>
  <section class="features">
    <div class="card"><span class="icon">⚡</span><h3>Fast</h3><p>Reconcile in seconds.</p></div>
    <div class="card"><span class="icon">🔒</span><h3>Secure</h3><p>Bank-grade encryption.</p></div>
    <div class="card"><span class="icon">📈</span><h3>Insightful</h3><p>Reports that make sense.</p></div>
  </section>
</body>
</html>
EOF

cat >style.css <<'EOF'
body {
  font-family: system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
  color: #000;
  background: #fff;
  margin: 0;
}
.hero {
  padding: 37px 22px;
  text-align: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}
.btn {
  display: inline-block;
  padding: 11px 26px;
  margin-top: 13px;
  background: #007bff;
  color: #fff;
  border-radius: 6px;
}
.btn:focus { outline: none; }
.features {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 19px;
  padding: 45px 30px;
}
.card {
  padding: 17px;
  box-shadow: 0 2px 9px rgba(0, 0, 0, 0.1);
  border-radius: 10px;
}
.icon { font-size: 28px; }
EOF
