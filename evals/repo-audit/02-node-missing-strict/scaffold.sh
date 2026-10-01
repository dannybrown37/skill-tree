#!/usr/bin/env bash
set -euo pipefail

mkdir -p src

cat >package.json <<'EOF'
{
  "name": "my-api",
  "version": "1.0.0",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js"
  },
  "dependencies": {
    "express": "^4.18.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}
EOF

cat >tsconfig.json <<'EOF'
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "outDir": "./dist",
    "strict": false
  },
  "include": ["src"]
}
EOF

cat >src/index.ts <<'EOF'
import express from 'express';

const app = express();

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

app.listen(3000, () => {
  console.log('Server running on port 3000');
});
EOF

cat >.gitignore <<'EOF'
node_modules/
dist/
EOF

cat >README.md <<'EOF'
# my-api
An Express API.
EOF

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
