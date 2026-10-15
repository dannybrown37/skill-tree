#!/usr/bin/env bash
set -euo pipefail

mkdir -p templates static

cat >app.py <<'PY'
from flask import Flask, render_template

app = Flask(__name__)

PLANS = [
    {"name": "Hobby", "price": 0, "seats": 1, "features": ["1 project", "Community support"]},
    {"name": "Team", "price": 24, "seats": 10, "features": ["Unlimited projects", "Email support", "SSO"]},
    {"name": "Business", "price": 79, "seats": 50, "features": ["Audit log", "Priority support", "SAML"]},
]


@app.get("/")
def home() -> str:
    return render_template("home.html")


@app.get("/pricing")
def pricing() -> str:
    return render_template("pricing.html", plans=PLANS)
PY

cat >templates/base.html <<'HTML'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{% block title %}Ledgerly{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='site.css') }}">
</head>
<body>
  <header><a href="/">Ledgerly</a> <nav><a href="/pricing">Pricing</a></nav></header>
  <main>{% block main %}{% endblock %}</main>
</body>
</html>
HTML

cat >templates/home.html <<'HTML'
{% extends "base.html" %}
{% block main %}<h1>Bookkeeping for small teams</h1>{% endblock %}
HTML

cat >templates/pricing.html <<'HTML'
{% extends "base.html" %}
{% block title %}Pricing · Ledgerly{% endblock %}
{% block main %}
<h1>Pricing</h1>
<div class="plans">
  {% for plan in plans %}
  <div class="plan">
    <h2>{{ plan.name }}</h2>
    <p>${{ plan.price }}/month · {{ plan.seats }} seats</p>
    <ul>{% for f in plan.features %}<li>{{ f }}</li>{% endfor %}</ul>
  </div>
  {% endfor %}
</div>
{% endblock %}
HTML

cat >static/site.css <<'CSS'
body { font-family: system-ui, sans-serif; margin: 0; }
header { display: flex; gap: 1rem; padding: 1rem 2rem; border-bottom: 1px solid #ddd; }
main { padding: 2rem; }
.plans { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
.plan { border: 1px solid #ddd; padding: 1rem; }
CSS

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
