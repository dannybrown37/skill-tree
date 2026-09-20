---
type: llm
focus: last_message
weight: 1
---
The response audits a nearly empty project (just a placeholder README and a .gitignore). Check that:

1. The response acknowledges the project is minimal/empty and identifies what's missing
2. It provides useful feedback (e.g., no source code, no tests, no pre-commit, placeholder README)
3. It does not crash, produce empty output, or simply refuse to audit

Score 1 if the response gives useful, structured feedback about what the project needs. Score 0.5 if it gives some feedback but is vague or unstructured. Score 0 if empty or refuses.
