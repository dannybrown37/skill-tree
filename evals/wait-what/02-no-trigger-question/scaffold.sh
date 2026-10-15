#!/usr/bin/env bash
set -euo pipefail

cat >server.py <<'PY'
import http.server

PORT = 4173

if __name__ == "__main__":
    handler = http.server.SimpleHTTPRequestHandler
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler).serve_forever()
PY
