#!/usr/bin/env bash
set -euo pipefail

mkdir -p src

cat >package.json <<'JSON'
{
  "name": "relay",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "build": "tsc",
    "test": "vitest run"
  },
  "devDependencies": {
    "typescript": "5.6.3",
    "vitest": "2.1.4"
  }
}
JSON

cat >tsconfig.json <<'JSON'
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "outDir": "dist"
  },
  "include": ["src"]
}
JSON

cat >src/server.ts <<'TS'
import { createServer } from "node:http";

export function start(port: number, host: string): void {
  createServer((_req, res) => res.end("ok")).listen(port, host);
}
TS

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
