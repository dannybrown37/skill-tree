---
type: llm
focus: last_message
weight: 1
---
The response is a quality audit of a project containing shell scripts with hardcoded secrets and poor hygiene. Check that it identifies ALL of the following:

1. Hardcoded secrets: API_KEY and DB_PASSWORD are hardcoded directly in shell scripts (this is a critical security finding)
2. Missing shellcheck / shell linting: no shellcheck configured
3. Missing error handling in scripts: no `set -euo pipefail` or equivalent
4. Missing pre-commit hooks
5. Missing .env from .gitignore (secrets could be committed)
6. Missing gitleaks or secret scanner

The hardcoded secrets should be called out as a serious/critical issue, not buried as a minor note.

Score 1 if all 6 issues are identified and secrets are flagged as serious. Score 0.5 if 4-5 found or secrets not emphasized. Score 0 if fewer than 4 found.
