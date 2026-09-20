---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
I have a Node.js/TypeScript project with these files. Audit it for quality issues.

**package.json:**
```json
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
```

**tsconfig.json:**
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "outDir": "./dist",
    "strict": false
  },
  "include": ["src"]
}
```

**src/index.ts:**
```typescript
import express from 'express';

const app = express();

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

app.listen(3000, () => {
  console.log('Server running on port 3000');
});
```

**.gitignore:**
```
node_modules/
dist/
```

**README.md:**
```
# my-api
An Express API.
```

That's the entire project — no other files exist. Audit it for quality issues.
