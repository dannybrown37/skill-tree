#!/usr/bin/env bash
set -euo pipefail

mkdir -p docs

cat >docs/rfc-profile-cache.md <<'MD'
# RFC: Read-through cache for the profile service

## Context

The profile service backs every page render. p99 read latency is 180 ms,
mostly Postgres. Peak traffic is 40,000 reads/second.

## Proposal

Put a Redis read-through cache in front of `GET /profiles/:id`.

- Key: `profile:<id>`, value: the full JSON profile (average 6 KB).
- TTL: 24 hours.
- On a miss, read Postgres and populate the cache.
- One `cache.r6g.large` node (13 GB memory). We have 30 million profiles,
  and expect most of them to be cached.

## Writes

Profile updates go straight to Postgres as they do today. The cache entry
expires on its own within a day.

## Expected impact

p99 read latency drops to under 10 ms. Postgres read load drops by about
95%.

## Rollout

Ship behind no flag; the cache is transparent to callers.
MD

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
