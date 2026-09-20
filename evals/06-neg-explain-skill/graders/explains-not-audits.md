---
type: llm
focus: last_message
weight: 1
---
The user asked "What does repo-audit check for?" — an informational question, not a request to run an audit.

Check that the response:
1. Explains what repo-audit checks (lists sections, capabilities, or categories)
2. Does NOT actually run an audit against any directory (no pass/fail verdicts on real code, no "Section 1: PASS" style output)
3. Is informational/explanatory in tone

Score 1 if the response explains the skill without running it. Score 0 if it actually executes a repo audit and produces real verdicts.
