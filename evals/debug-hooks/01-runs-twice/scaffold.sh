#!/usr/bin/env bash
set -euo pipefail

mkdir -p .claude scripts

cat >scripts/fmt.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "formatted: ${1:-}"
SH
chmod +x scripts/fmt.sh

# The same formatter hook, registered in both project and project-local settings.
cat >.claude/settings.json <<'JSON'
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "./scripts/fmt.sh \"$CLAUDE_FILE_PATHS\"" }]
      }
    ]
  }
}
JSON

cat >.claude/settings.local.json <<'JSON'
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "./scripts/fmt.sh \"$CLAUDE_FILE_PATHS\"" }]
      }
    ]
  }
}
JSON

cat >.gitignore <<'TXT'
.claude/settings.local.json
TXT

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
