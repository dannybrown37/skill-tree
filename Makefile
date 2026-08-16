.PHONY: help skill output-style install
.DEFAULT_GOAL := help

help:
	@echo "Usage:"
	@echo "  make skill SKILL=<name>          Scaffold a new skill in skills/<name>/"
	@echo "  make output-style STYLE=<name>   Create an output style in output-styles/<name>.md"
	@echo "  make install                     Symlink skills, CLIs, and output styles into ~/"
	@echo ""
	@echo "skill and output-style open the new file in VS Code or \$$EDITOR."

skill:
	@./scripts/new-skill.sh $(SKILL)

output-style:
	@./scripts/new-output-style.sh $(STYLE)

install:
	@./scripts/install.sh
