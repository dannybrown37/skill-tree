#!/usr/bin/env python3
"""PreToolUse hook: pre-approve reading the screenshot the user just took.

Resolving a screenshot costs two permission prompts -- one for the
resolver, one for the `Read` of a path outside the workspace -- which is
most of the friction in a skill whose whole job is "look at this". A
plugin can't ship `permissions.allow` (a plugin `settings.json` only
honors `agent` and `subagentStatusLine`), so the grant is expressed here
instead, where it can be narrow: this exact script run read-only, and
image files inside whichever directory it resolves to.

Anything else -- another command riding along on the same line, `set`,
a non-image, a path outside that directory -- leaves the normal
permission flow untouched.

Two hosts, two dialects, detected per payload rather than configured:

* Claude Code sends `tool_name`/`tool_input` and reads a decision nested
  under `hookSpecificOutput`. Saying nothing means "no opinion".
* Copilot CLI sends `toolName`/`toolArgs` and reads a flat
  `permissionDecision`. Its preToolUse hooks are *fail-closed*, so
  silence is not a safe way to abstain -- every path answers explicitly,
  with `ask` meaning "run the normal permission flow". This hook has no
  deny path in either dialect; it only ever widens.
"""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

RESOLVER = Path(__file__).parent / 'screenshot'

# Read-only actions. `set` is excluded deliberately: it writes config, so
# it should cost a prompt.
SAFE_ACTIONS = frozenset({'latest', 'list', 'dir', 'help', '-h', '--help'})

# Shell syntax that could smuggle a second command onto an allowed line.
# `${VAR:-default}` is not in here -- it's how SKILL.md spells the path.
CHAINING = (';', '&', '|', '<', '>', '\n', '`', '$(')

IMAGE_SUFFIXES = frozenset(
    {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'},
)

# Interpreters the resolver is plausibly invoked through.
INTERPRETERS = frozenset({'bash', 'sh'})

# The `${NAME:-fallback}` form, which os.path.expandvars leaves alone.
DEFAULTED_VAR = re.compile(r'\$\{(\w+):-([^{}]*)\}')

RESOLVE_TIMEOUT_SECONDS = 5


def expand(token: str) -> str:
    """A path token as the shell would have expanded it.

    Only the substitutions the skill's own spellings use -- enough to
    recognize a path, never enough to run anything.
    """
    expanded = DEFAULTED_VAR.sub(
        lambda match: os.environ.get(match.group(1)) or match.group(2),
        token,
    )
    return os.path.expandvars(expanded)


def is_resolver(token: str) -> bool:
    """Whether `token` names this very script's sibling resolver."""
    try:
        candidate = Path(expand(token)).expanduser().resolve()
    except (OSError, ValueError):
        return False
    return candidate == RESOLVER.resolve()


def resolver_args(argv: list[str]) -> list[str] | None:
    """`argv`'s arguments if it invokes the resolver, else None."""
    if argv and Path(argv[0]).name in INTERPRETERS:
        argv = argv[1:]
    if not argv:
        return None

    # `skill-tree screenshot <action>` reaches the same code by another
    # door; the dispatcher name is the only part worth matching loosely.
    if Path(expand(argv[0])).name == 'skill-tree':
        return argv[2:] if argv[1:2] == ['screenshot'] else None

    return argv[1:] if is_resolver(argv[0]) else None


def allowed_bash(command: str) -> bool:
    """Whether `command` is one read-only run of the resolver, alone."""
    if any(token in command for token in CHAINING):
        return False

    try:
        argv = shlex.split(command)
    except ValueError:
        return False

    args = resolver_args(argv)
    if args is None:
        return False

    action, *rest = args or ['help']
    if action not in SAFE_ACTIONS:
        return False
    # `list N` is the only action that takes an argument.
    counted = action == 'list' and len(rest) == 1 and rest[0].isdigit()
    return not rest or counted


def screenshot_dir() -> Path | None:
    """The directory the resolver would use, or None if it has none."""
    try:
        result = subprocess.run(  # noqa: S603
            ['bash', str(RESOLVER), 'dir'],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=RESOLVE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    printed = result.stdout.strip()
    if not printed:
        return None
    try:
        return Path(printed).resolve()
    except (OSError, ValueError):
        return None


def allowed_read(file_path: str) -> bool:
    """Whether `file_path` is an image inside the screenshots directory."""
    if not file_path:
        return False
    try:
        target = Path(file_path).expanduser().resolve()
    except (OSError, ValueError):
        return False

    if target.suffix.lower() not in IMAGE_SUFFIXES:
        return False

    directory = screenshot_dir()
    # `resolve()` on both sides first, so `<dir>/../elsewhere.png` is
    # judged by where it lands rather than how it's spelled.
    return directory is not None and directory in target.parents


# Copilot CLI's tool names and argument keys aren't specified anywhere
# the way Claude's are, and a wrong guess here reads as "the hook simply
# never fires". Both sets are matched case-insensitively, and every
# plausible spelling is accepted -- widening these only ever costs an
# extra `allowed_*` check, which is the part that actually decides.
SHELL_TOOLS = frozenset({'bash', 'shell'})
READ_TOOLS = frozenset({'read', 'view'})
COMMAND_KEYS = ('command', 'cmd')
PATH_KEYS = ('file_path', 'path', 'filePath', 'target_file')


def first_string(args: dict, keys: tuple[str, ...]) -> str | None:
    """The first of `keys` present in `args` with a string value."""
    for key in keys:
        value = args.get(key)
        if isinstance(value, str):
            return value
    return None


def decide(tool_name: str, args: dict) -> str | None:
    """The reason to allow this call, or None to have no opinion."""
    normalized = tool_name.lower()

    if normalized in SHELL_TOOLS:
        command = first_string(args, COMMAND_KEYS)
        if command is not None and allowed_bash(command):
            return 'Read-only screenshot path lookup (skill-tree).'
    elif normalized in READ_TOOLS:
        file_path = first_string(args, PATH_KEYS)
        if file_path is not None and allowed_read(file_path):
            return "Image in this machine's screenshots directory."
    return None


def respond_claude(reason: str | None) -> None:
    if reason is None:
        return
    json.dump(
        {
            'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'permissionDecision': 'allow',
                'permissionDecisionReason': reason,
            },
        },
        sys.stdout,
    )


def respond_copilot(reason: str | None) -> None:
    if reason is None:
        json.dump({'permissionDecision': 'ask'}, sys.stdout)
        return
    json.dump(
        {'permissionDecision': 'allow', 'permissionDecisionReason': reason},
        sys.stdout,
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    if not isinstance(payload, dict):
        return

    # Junk stdin exits above without a decision: the dialect is only
    # knowable from a payload that parsed, and Claude's silence is the
    # safer of the two guesses.
    is_copilot = 'toolName' in payload or 'toolArgs' in payload
    name_key, args_key = (
        ('toolName', 'toolArgs') if is_copilot else ('tool_name', 'tool_input')
    )
    respond = respond_copilot if is_copilot else respond_claude

    tool_name = payload.get(name_key)
    args = payload.get(args_key)
    if not isinstance(tool_name, str) or not isinstance(args, dict):
        respond(None)
        return

    respond(decide(tool_name, args))


if __name__ == '__main__':
    main()
