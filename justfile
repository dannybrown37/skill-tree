default:
    @echo "Usage:"
    @echo "  make skill <name>            Scaffold a new skill in skills/<name>/"
    @echo "  make output-style <name>     Create an output style in output-styles/<name>.md"
    @echo "  make install                 Symlink skills, CLIs, and output styles into ~/"
    @echo ""
    @echo "skill and output-style open the new file in VS Code or \$EDITOR."

skill name:
    @./scripts/new-skill.sh {{name}}

output-style name:
    @./scripts/new-output-style.sh {{name}}

install:
    @./scripts/install.sh
