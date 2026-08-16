---
name: node-style
description: "Read before writing Node, TypeScript, or JavaScript code. Covers type safety, ESLint, error handling, testing (Jest/Vitest), and package management."
user-invocable: true
---

# Node / TypeScript

## Type Safety

- Always use explicit type hints for function parameters.
- Always use explicit return types (`@typescript-eslint/explicit-function-return-type`).
- Never use `any` — use `unknown` and narrow, or define a proper type.
- Use `type` imports for type-only imports (`import type { Foo } from ...`).

## ESLint Rules

Use [ESLint](https://eslint.org/) to enforce consistent code style.

## Error Handling

- Never use bare `catch(e)` — type-narrow or use `unknown` and check with `instanceof`.
- Use the most specific built-in or library error available (e.g., `TypeError`, `RangeError`). Custom error classes are a last resort.
- Always handle promise rejections — no fire-and-forget `.then()` without `.catch()`.

## Testing

Use [Jest](https://jestjs.io/) as the default test runner. Consider [Vitest](https://vitest.dev/) for new standalone projects.

## Logging

Logs should be one line when possible.

## Package Management

Use [npm](https://www.npmjs.com/) for package management.

Consider [Deno 2](https://deno.land/) for new standalone projects.
