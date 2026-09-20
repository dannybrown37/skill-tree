---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
I have a project with the following files. What quality issues does it have?

**scripts/deploy.sh:**
```bash
#!/bin/bash
API_KEY=sk-prod-abc123def456
curl -H "Authorization: Bearer $API_KEY" https://api.example.com/deploy
echo "Deployed successfully"
```

**scripts/backup.sh:**
```bash
#!/bin/bash
DB_PASSWORD=hunter2
mysqldump -u root -p$DB_PASSWORD mydb > backup.sql
rm -rf /tmp/old_backups
```

**scripts/setup.sh:**
```bash
#!/bin/bash
pip install flask requests
python app.py
```

**app.py:**
```python
from flask import Flask
app = Flask(__name__)

@app.route("/")
def index():
    return "hello"

if __name__ == "__main__":
    app.run(debug=True)
```

**.gitignore:**
```
*.pyc
```

**README.md:**
```
# myproject
Run scripts/setup.sh to get started.
```

That's the entire project — no other files exist. What quality issues does this project have?
