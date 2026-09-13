#!/usr/bin/env python3
"""Every hook that would fire in this session, from every source at once.

Claude and Copilot each merge hooks from several files -- user settings,
project settings, project-local settings, and every installed plugin's own
hooks.json (Copilot: one hooks/*.json per plugin) -- and none of them show
you the merged result. This reads every source directly off disk and prints
what actually runs, so "why did that hook fire twice" or "is this hook even
wired up" doesn't require grepping five files by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Claude settings resolve in this order; Copilot has one file per plugin
# instead, discovered separately. Sources that don't exist are skipped, not
# reported as missing -- most repos have no local override.
CLAUDE_USER_SOURCE = ('user settings', Path('.claude/settings.json'))
CLAUDE_MANAGED_PATHS = (
    Path('/etc/claude-code/managed-settings.json'),
    Path('/Library/Application Support/ClaudeCode/managed-settings.json'),
)


@dataclass(frozen=True)
class HookEntry:
    """One hook, as a single source declared it."""

    host: str  # 'claude' | 'copilot'
    source: str  # human label: 'user settings', 'plugin:name@marketplace', ...
    event: str
    matcher: str | None
    command: str
    timeout: int | None


@dataclass(frozen=True)
class GatherResult:
    entries: list[HookEntry]
    warnings: list[str]


def _load_json(path: Path) -> dict[str, object] | None:
    """Parsed JSON, or None if the file is absent/unreadable/malformed."""
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _parse_claude_hooks(
    source: str,
    data: dict[str, object],
) -> list[HookEntry]:
    """The nested `{event: [{matcher, hooks: [{type, command}]}]}` shape."""
    entries: list[HookEntry] = []
    hooks = data.get('hooks', {})
    if not isinstance(hooks, dict):
        return entries

    for event, matchers in hooks.items():
        if not isinstance(matchers, list):
            continue
        for matcher_block in matchers:
            if not isinstance(matcher_block, dict):
                continue
            matcher = matcher_block.get('matcher')
            for hook in matcher_block.get('hooks', []) or []:
                if not isinstance(hook, dict):
                    continue
                command = hook.get('command')
                if not isinstance(command, str):
                    continue
                timeout = hook.get('timeout')
                entries.append(
                    HookEntry(
                        host='claude',
                        source=source,
                        event=str(event),
                        matcher=matcher if isinstance(matcher, str) else None,
                        command=command,
                        timeout=timeout if isinstance(timeout, int) else None,
                    ),
                )
    return entries


def _parse_copilot_hooks(
    source: str,
    data: dict[str, object],
) -> list[HookEntry]:
    """The flat `{event: [{type, matcher?, bash, timeoutSec?}]}` shape."""
    entries: list[HookEntry] = []
    hooks = data.get('hooks', {})
    if not isinstance(hooks, dict):
        return entries

    for event, hook_list in hooks.items():
        if not isinstance(hook_list, list):
            continue
        for hook in hook_list:
            if not isinstance(hook, dict):
                continue
            command = hook.get('bash')
            if not isinstance(command, str):
                continue
            matcher = hook.get('matcher')
            timeout = hook.get('timeoutSec')
            entries.append(
                HookEntry(
                    host='copilot',
                    source=source,
                    event=str(event),
                    matcher=matcher if isinstance(matcher, str) else None,
                    command=command,
                    timeout=timeout if isinstance(timeout, int) else None,
                ),
            )
    return entries


def _claude_settings_sources(home: Path, root: Path) -> list[tuple[str, Path]]:
    return [
        ('user settings', home / '.claude' / 'settings.json'),
        ('project settings', root / '.claude' / 'settings.json'),
        ('local settings', root / '.claude' / 'settings.local.json'),
        *(
            ('managed settings', path)
            for path in CLAUDE_MANAGED_PATHS
            if path.is_file()
        ),
    ]


def _claude_plugin_sources(plugins_home: Path) -> list[tuple[str, Path]]:
    """Every installed plugin with a `hooks/hooks.json`, from the registry.

    `installed_plugins.json` is Claude's own record of what's installed and
    where -- reading it beats guessing plugin directory layouts.
    """
    registry = plugins_home / '.claude' / 'plugins' / 'installed_plugins.json'
    data = _load_json(registry)
    if data is None:
        return []

    plugins = data.get('plugins', {})
    if not isinstance(plugins, dict):
        return []

    sources: list[tuple[str, Path]] = []
    for name, installs in plugins.items():
        if not isinstance(installs, list):
            continue
        for install in installs:
            if not isinstance(install, dict):
                continue
            install_path = install.get('installPath')
            if not isinstance(install_path, str):
                continue
            hooks_file = Path(install_path) / 'hooks' / 'hooks.json'
            if hooks_file.is_file():
                sources.append((f'plugin:{name}', hooks_file))
    return sources


def _copilot_sources(home: Path) -> list[tuple[str, Path]]:
    hooks_dir = home / '.copilot' / 'hooks'
    if not hooks_dir.is_dir():
        return []
    return [
        (f'copilot:{path.name}', path)
        for path in sorted(hooks_dir.glob('*.json'))
    ]


def gather(*, home: Path, root: Path, plugins_home: Path) -> GatherResult:
    """Every hook, from every source, plus sources that failed to parse."""
    entries: list[HookEntry] = []
    warnings: list[str] = []

    for source, path in _claude_settings_sources(home, root):
        if not path.is_file():
            continue
        data = _load_json(path)
        if data is None:
            warnings.append(f'could not parse {path}')
            continue
        entries.extend(_parse_claude_hooks(source, data))

    for source, path in _claude_plugin_sources(plugins_home):
        data = _load_json(path)
        if data is None:
            warnings.append(f'could not parse {path}')
            continue
        entries.extend(_parse_claude_hooks(source, data))

    for source, path in _copilot_sources(home):
        data = _load_json(path)
        if data is None:
            warnings.append(f'could not parse {path}')
            continue
        entries.extend(_parse_copilot_hooks(source, data))

    return GatherResult(entries=entries, warnings=warnings)


def collect(*, home: Path, root: Path, plugins_home: Path) -> list[HookEntry]:
    """`gather`, for callers that don't care about parse warnings."""
    return gather(home=home, root=root, plugins_home=plugins_home).entries


def _sources_per_event(entries: list[HookEntry]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for entry in entries:
        key = (entry.host, entry.event)
        sources = {e.source for e in entries if (e.host, e.event) == key}
        counts[key] = len(sources)
    return counts


def render(entries: list[HookEntry], *, warnings: list[str]) -> str:
    """Human-readable report, grouped by host then event."""
    lines: list[str] = [f'WARN: {warning}' for warning in warnings]
    if warnings:
        lines.append('')

    if not entries:
        lines.append('no hooks found in any source.')
        return '\n'.join(lines) + '\n'

    shared = _sources_per_event(entries)
    for host in sorted({entry.host for entry in entries}):
        lines.append(host.upper())
        by_event: dict[str, list[HookEntry]] = {}
        for entry in entries:
            if entry.host == host:
                by_event.setdefault(entry.event, []).append(entry)

        for event in sorted(by_event):
            count = shared[(host, event)]
            tag = f'  ({count} sources)' if count > 1 else ''
            lines.append(f'  {event}{tag}')
            for entry in by_event[event]:
                matcher = f' [{entry.matcher}]' if entry.matcher else ''
                timeout = f' ({entry.timeout}s)' if entry.timeout else ''
                lines.append(
                    f'    {entry.source}{matcher}: {entry.command}{timeout}',
                )
        lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


def as_json(entries: list[HookEntry], *, warnings: list[str]) -> str:
    return json.dumps(
        {
            'warnings': warnings,
            'hooks': [
                {
                    'host': entry.host,
                    'source': entry.source,
                    'event': entry.event,
                    'matcher': entry.matcher,
                    'command': entry.command,
                    'timeout': entry.timeout,
                }
                for entry in entries
            ],
        },
        indent=2,
    )


def version() -> str:
    """This checkout's plugin version, or `unknown` outside one.

    `--version` has to work with no config and no credentials, so a
    missing or unreadable manifest is an answer rather than a crash.
    """
    manifest = (
        Path(__file__).resolve().parents[3] / '.claude-plugin' / 'plugin.json'
    )
    try:
        return str(json.loads(manifest.read_text())['version'])
    except (OSError, ValueError, KeyError):
        return 'unknown'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='hooks',
        description='Every hook that would fire in this session, merged '
        'from every Claude and Copilot source on disk.',
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'hooks {version()}',
    )
    parser.add_argument(
        '--claude',
        action='store_true',
        help='show only Claude hooks',
    )
    parser.add_argument(
        '--copilot',
        action='store_true',
        help='show only Copilot hooks',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        dest='as_json',
        help='machine-readable output',
    )
    parser.add_argument(
        'root',
        nargs='?',
        default='.',
        type=Path,
        help='project root to read .claude/settings*.json from; defaults '
        'to cwd',
    )

    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    home = Path.home()
    result = gather(home=home, root=args.root, plugins_home=home)

    entries = result.entries
    if args.claude and not args.copilot:
        entries = [e for e in entries if e.host == 'claude']
    elif args.copilot and not args.claude:
        entries = [e for e in entries if e.host == 'copilot']

    output = (
        as_json(entries, warnings=result.warnings)
        if args.as_json
        else render(entries, warnings=result.warnings)
    )
    print(output, end='' if output.endswith('\n') else '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
