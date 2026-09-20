---
type: llm
focus: last_message
weight: 1
---
The response audits a Node.js/TypeScript project that has several quality gaps. The project has: package.json, tsconfig with strict:false, an Express app, .gitignore, README — but NO lockfile, NO linter/biome, NO pre-commit, NO tests, and NO secret scanner.

Check that the response identifies at least 4 of these 6 gaps:
1. TypeScript strict mode disabled (strict: false)
2. No linter/formatter (biome, eslint, or prettier)
3. No lockfile (package-lock.json)
4. No pre-commit hooks
5. No tests
6. No secrets scanner

The response should provide actionable fix suggestions.

Score 1 if ≥4 gaps identified with actionable suggestions. Score 0.5 if 2-3 gaps identified. Score 0 if fewer than 2.
