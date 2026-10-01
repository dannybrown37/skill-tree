#!/usr/bin/env bash
# The credentials below are fake; they are the hardcoded secrets the audit
# is supposed to flag. .gitleaksignore covers them.
set -euo pipefail

mkdir -p scripts

cat >scripts/deploy.sh <<'EOF'
#!/bin/bash
API_KEY=sk-prod-abc123def456
curl -H "Authorization: Bearer $API_KEY" https://api.example.com/deploy
echo "Deployed successfully"
EOF

cat >scripts/backup.sh <<'EOF'
#!/bin/bash
DB_PASSWORD=hunter2
mysqldump -u root -p$DB_PASSWORD mydb > backup.sql
rm -rf /tmp/old_backups
EOF

cat >scripts/setup.sh <<'EOF'
#!/bin/bash
pip install flask requests
python app.py
EOF

chmod +x scripts/*.sh

cat >app.py <<'EOF'
from flask import Flask
app = Flask(__name__)

@app.route("/")
def index():
    return "hello"

if __name__ == "__main__":
    app.run(debug=True)
EOF

cat >.gitignore <<'EOF'
*.pyc
EOF

cat >README.md <<'EOF'
# myproject
Run scripts/setup.sh to get started.
EOF

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
