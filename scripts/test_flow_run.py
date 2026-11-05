"""Tests for `skill-tree run` (scripts/flow_run.py)."""

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import flow_run as fr

REPO_ROOT = Path(__file__).parent.parent


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


BASE = """
name = "base"
allow_tools = ["write"]

[[steps]]
id = "a"
skill = "skill-a"
out = "a.md"

[[steps]]
id = "b"
skill = "skill-b"
in = ["a.md"]
out = "b.md"
gate = "approve"

[[steps]]
id = "c"
skill = "skill-c"
in = ["b.md"]
out = "c.md"
"""


@pytest.fixture
def layers(tmp_path: Path) -> fr.Layers:
    repo = tmp_path / 'repo'
    (repo / '.git').mkdir(parents=True)
    user = tmp_path / 'user'
    builtin = tmp_path / 'builtin'
    write(builtin / 'base.toml', BASE)
    user.mkdir()
    return fr.Layers(repo=repo, user=user, builtin=builtin)


def ids(flow: fr.Flow) -> list[str]:
    return [step.id for step in flow.steps]


# --- loading + layering ---------------------------------------------------


def test_loads_builtin_flow(layers: fr.Layers) -> None:
    flow = fr.load_flow('base', layers)
    assert ids(flow) == ['a', 'b', 'c']
    assert flow.steps[1].inputs == ('a.md',)
    assert flow.steps[1].gate == 'approve'
    assert flow.steps[0].gate == 'none'
    assert flow.allow_tools == ('write',)


@pytest.mark.parametrize(
    ('winner', 'expected_skill'),
    [
        ('repo', 'from-repo'),
        ('user', 'from-user'),
        ('builtin', 'skill-a'),
    ],
)
def test_layer_precedence(
    layers: fr.Layers,
    winner: str,
    expected_skill: str,
) -> None:
    one_step = '[[steps]]\nid = "a"\nskill = "{}"\n'
    if winner in {'repo', 'user'}:
        write(layers.user / 'base.toml', one_step.format('from-user'))
    if winner == 'repo':
        write(
            layers.repo / '.skill-tree' / 'flows' / 'base.toml',
            one_step.format('from-repo'),
        )
    assert fr.load_flow('base', layers).steps[0].skill == expected_skill


def test_no_name_prefers_repo_flow_toml(layers: fr.Layers) -> None:
    write(
        layers.repo / '.skill-tree' / 'flow.toml',
        '[[steps]]\nid = "x"\nskill = "repo-skill"\n',
    )
    assert ids(fr.load_flow(None, layers)) == ['x']


def test_no_name_falls_back_to_default(layers: fr.Layers) -> None:
    write(layers.builtin / 'default.toml', BASE)
    assert ids(fr.load_flow(None, layers)) == ['a', 'b', 'c']


def test_unknown_flow_lists_search_paths(layers: fr.Layers) -> None:
    with pytest.raises(fr.FlowError, match=r'(?s)nope.*user/nope\.toml'):
        fr.load_flow('nope', layers)


def test_list_flows(layers: fr.Layers) -> None:
    write(layers.user / 'work.toml', BASE)
    names = {name for name, _ in fr.list_flows(layers)}
    assert names == {'base', 'work'}


# --- extends + patches ----------------------------------------------------


def child(body: str) -> str:
    return 'extends = "base"\n' + body


@pytest.mark.parametrize(
    ('patch', 'expected'),
    [
        ('[patch]\nremove = ["b"]\n', ['a', 'c']),
        (
            '[[patch.append]]\nid = "z"\nskill = "s"\n',
            ['a', 'b', 'c', 'z'],
        ),
        (
            '[[patch.insert_after.a]]\nid = "n"\nskill = "s"\n',
            ['a', 'n', 'b', 'c'],
        ),
        (
            '[[patch.insert_before.a]]\nid = "n"\nskill = "s"\n',
            ['n', 'a', 'b', 'c'],
        ),
    ],
)
def test_patch_ops(
    layers: fr.Layers,
    patch: str,
    expected: list[str],
) -> None:
    write(layers.user / 'work.toml', child(patch))
    assert ids(fr.load_flow('work', layers)) == expected


def test_replace_merges_fields_and_keeps_position(
    layers: fr.Layers,
) -> None:
    write(
        layers.user / 'work.toml',
        child('[patch.replace.b]\nskill = "to-sync-point"\n'),
    )
    flow = fr.load_flow('work', layers)
    assert ids(flow) == ['a', 'b', 'c']
    assert flow.steps[1].skill == 'to-sync-point'
    assert flow.steps[1].gate == 'approve'
    assert flow.steps[1].inputs == ('a.md',)


def test_child_overrides_scalars_and_inherits_rest(
    layers: fr.Layers,
) -> None:
    write(layers.user / 'work.toml', child('context = ["glossary"]\n'))
    flow = fr.load_flow('work', layers)
    assert flow.context == ('glossary',)
    assert flow.allow_tools == ('write',)
    assert flow.name == 'work'


def test_user_flow_can_extend_same_named_builtin(
    layers: fr.Layers,
) -> None:
    write(layers.user / 'base.toml', child('[patch]\nremove = ["c"]\n'))
    assert ids(fr.load_flow('base', layers)) == ['a', 'b']


def test_extends_cycle_is_an_error(layers: fr.Layers) -> None:
    write(layers.user / 'x.toml', 'extends = "y"\n')
    write(layers.user / 'y.toml', 'extends = "x"\n')
    with pytest.raises(fr.FlowError, match='cycle'):
        fr.load_flow('x', layers)


@pytest.mark.parametrize(
    ('body', 'message'),
    [
        ('[patch]\nremove = ["nope"]\n', 'no step "nope"'),
        ('[patch.replace.nope]\nskill = "s"\n', 'no step "nope"'),
        ('[patch]\nfrobnicate = []\n', 'frobnicate'),
        ('[patch.replace.b]\nid = "renamed"\n', 'id'),
        ('[[steps]]\nid = "q"\nskill = "s"\n', 'both'),
        (
            '[[patch.append]]\nid = "a"\nskill = "s"\n',
            'duplicate step id "a"',
        ),
    ],
)
def test_bad_patches(layers: fr.Layers, body: str, message: str) -> None:
    write(layers.user / 'work.toml', child(body))
    with pytest.raises(fr.FlowError, match=message):
        fr.load_flow('work', layers)


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize(
    ('text', 'message'),
    [
        ('[[steps]]\nid = "a"\nskil = "s"\n', 'skil'),
        ('[[steps]]\nid = "a"\n', 'skill'),
        ('[[steps]]\nskill = "s"\n', 'id'),
        ('[[steps]]\nid = "a"\nskill = "s"\ngate = "maybe"\n', 'gate'),
        ('steps = []\n', 'no steps'),
        ('bogus = 1\n[[steps]]\nid = "a"\nskill = "s"\n', 'bogus'),
        ('[[steps]]\nid = "a"\nskill = "s"\nin = "x.md"\n', 'in'),
        ('[[steps]]\nid = "a"\nskill = "s"\nout = "../x.md"\n', 'out'),
        ('[[steps]]\nid = "a"\nskill = "s"\ntimeout = -1\n', 'timeout'),
        ('host = "gemini"\n[[steps]]\nid = "a"\nskill = "s"\n', 'host'),
        ('this is not toml', 'TOML'),
    ],
)
def test_invalid_flows(layers: fr.Layers, text: str, message: str) -> None:
    write(layers.user / 'bad.toml', text)
    with pytest.raises(fr.FlowError, match=message):
        fr.load_flow('bad', layers)


# --- planning / dry run ---------------------------------------------------


def skills_for(*names: str) -> dict[str, Path]:
    return {name: Path(f'/skills/{name}') for name in names}


def test_check_flow_ok(layers: fr.Layers) -> None:
    flow = fr.load_flow('base', layers)
    problems = fr.check_flow(flow, skills_for('skill-a', 'skill-b', 'skill-c'))
    assert problems == []


def test_check_flow_reports_missing_skills_and_context(
    layers: fr.Layers,
) -> None:
    write(layers.user / 'work.toml', child('context = ["glossary"]\n'))
    flow = fr.load_flow('work', layers)
    problems = fr.check_flow(flow, skills_for('skill-a'))
    joined = '\n'.join(problems)
    assert 'skill-b' in joined
    assert 'skill-c' in joined
    assert 'glossary' in joined


def test_check_flow_reports_input_nobody_produces(
    layers: fr.Layers,
) -> None:
    write(
        layers.user / 'work.toml',
        child('[patch]\nremove = ["a"]\n'),
    )
    flow = fr.load_flow('work', layers)
    problems = fr.check_flow(flow, skills_for('skill-b', 'skill-c'))
    assert any('a.md' in problem for problem in problems)


def test_dry_run_table_shows_source_and_gate(layers: fr.Layers) -> None:
    flow = fr.load_flow('base', layers)
    table = fr.render_plan(flow, skills_for('skill-a', 'skill-b'))
    assert 'skill-b' in table
    assert '/skills/skill-a' in table
    assert 'approve' in table
    assert 'MISSING' in table


# --- skill resolution (Copilot) -------------------------------------------

SKILL_LIST_JSON = [
    {
        'name': 'to-sync-point',
        'source': 'personal-copilot',
        'path': '/home/u/.copilot/skills/to-sync-point',
        'enabled': True,
    },
    {
        'name': 'arch-review',
        'source': 'project',
        'path': '/repo/.github/skills/arch-review',
        'enabled': True,
    },
    {
        'name': 'off',
        'source': 'personal-copilot',
        'path': '/x/off',
        'enabled': False,
    },
]


def fake_copilot(
    tmp_path: Path,
    script_body: str,
) -> Path:
    binary = tmp_path / 'bin' / 'copilot'
    write(binary, '#!/usr/bin/env bash\nset -euo pipefail\n' + script_body)
    binary.chmod(0o755)
    return binary


def test_copilot_list_skills_parses_json(tmp_path: Path) -> None:
    data = tmp_path / 'skills.json'
    data.write_text(json.dumps(SKILL_LIST_JSON))
    binary = fake_copilot(tmp_path, f'cat {data}\n')
    skills = fr.CopilotHost(str(binary)).list_skills(tmp_path)
    assert skills == {
        'to-sync-point': Path('/home/u/.copilot/skills/to-sync-point'),
        'arch-review': Path('/repo/.github/skills/arch-review'),
    }


def test_copilot_list_skills_failure_is_flow_error(tmp_path: Path) -> None:
    binary = fake_copilot(tmp_path, 'echo boom >&2; exit 3\n')
    with pytest.raises(fr.FlowError, match='boom'):
        fr.CopilotHost(str(binary)).list_skills(tmp_path)


def test_copilot_missing_binary_is_flow_error(tmp_path: Path) -> None:
    host = fr.CopilotHost(str(tmp_path / 'does-not-exist'))
    with pytest.raises(fr.FlowError, match='copilot'):
        host.list_skills(tmp_path)


def test_copilot_headless_argv(tmp_path: Path) -> None:
    argv_file = tmp_path / 'argv'
    binary = fake_copilot(
        tmp_path,
        f'printf "%s\\n" "$@" > {argv_file}\necho "{{}}"\n',
    )
    log = tmp_path / 'log.jsonl'
    code = fr.CopilotHost(str(binary)).run_headless(
        'do it; rm -rf /',
        fr.RunOptions(
            cwd=tmp_path,
            model='gpt-x',
            allow_tools=('write', 'shell(git:*)'),
            allow_all=False,
            timeout=None,
        ),
        log,
    )
    assert code == 0
    argv = argv_file.read_text().splitlines()
    assert argv[:2] == ['-p', 'do it; rm -rf /']
    assert argv[argv.index('--model') :][:2] == ['--model', 'gpt-x']
    assert argv.count('--allow-tool') == 2
    assert 'shell(git:*)' in argv
    assert '--allow-all-tools' not in argv
    assert log.read_text().strip() == '{}'


def test_copilot_headless_allow_all(tmp_path: Path) -> None:
    argv_file = tmp_path / 'argv'
    binary = fake_copilot(tmp_path, f'printf "%s\\n" "$@" > {argv_file}\n')
    fr.CopilotHost(str(binary)).run_headless(
        'p',
        fr.RunOptions(
            cwd=tmp_path,
            model=None,
            allow_tools=(),
            allow_all=True,
            timeout=None,
        ),
        tmp_path / 'log',
    )
    argv = argv_file.read_text().splitlines()
    assert '--allow-all-tools' in argv
    assert '--model' not in argv


def test_copilot_headless_timeout(tmp_path: Path) -> None:
    binary = fake_copilot(tmp_path, 'sleep 5\n')
    code = fr.CopilotHost(str(binary)).run_headless(
        'p',
        fr.RunOptions(
            cwd=tmp_path,
            model=None,
            allow_tools=(),
            allow_all=False,
            timeout=1,
        ),
        tmp_path / 'log',
    )
    assert code == fr.TIMEOUT_EXIT


# --- prompt ---------------------------------------------------------------


def test_prompt_contents(tmp_path: Path) -> None:
    step = fr.Step(id='spec', skill='to-spec', inputs=('a.md',), out='b.md')
    prompt = fr.build_prompt(
        step,
        idea='Add dark mode',
        run_dir=tmp_path,
        skills=skills_for('to-spec', 'glossary'),
        context=('glossary',),
        headless=True,
    )
    assert '/skills/to-spec/SKILL.md' in prompt
    assert '/skills/glossary/SKILL.md' in prompt
    assert str(tmp_path / 'a.md') in prompt
    assert str(tmp_path / 'b.md') in prompt
    assert 'Add dark mode' in prompt
    assert 'do not ask' in prompt.lower()


def test_interactive_prompt_omits_no_questions_rule(tmp_path: Path) -> None:
    step = fr.Step(id='grill', skill='g', out='d.md', gate='interactive')
    prompt = fr.build_prompt(
        step,
        idea='x',
        run_dir=tmp_path,
        skills=skills_for('g'),
        context=(),
        headless=False,
    )
    assert 'do not ask' not in prompt.lower()
    assert 'context' not in prompt.lower()


# --- runner loop ----------------------------------------------------------


@dataclass
class FakeHost:
    """Writes each step's output file, or misbehaves on request."""

    skip_output: set[str] = field(default_factory=set)
    exit_codes: dict[str, int] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def list_skills(self, _cwd: Path) -> dict[str, Path]:
        return skills_for('skill-a', 'skill-b', 'skill-c', 'g')

    def _act(self, mode: str, prompt: str) -> int:
        step_id = prompt.split('[step:', 1)[1].split(']', 1)[0]
        self.calls.append((mode, step_id))
        out_line = next(
            (
                line
                for line in prompt.splitlines()
                if line.startswith('Write your output to:')
            ),
            None,
        )
        if out_line and step_id not in self.skip_output:
            Path(out_line.split(': ', 1)[1]).write_text(f'{step_id} done')
        return self.exit_codes.get(step_id, 0)

    def run_headless(
        self,
        prompt: str,
        _options: fr.RunOptions,
        log: Path,
    ) -> int:
        log.write_text('')
        return self._act('headless', prompt)

    def run_interactive(self, prompt: str, _options: fr.RunOptions) -> int:
        return self._act('interactive', prompt)


def answers(*replies: str) -> Callable[[str], str]:
    queue: Iterator[str] = iter(replies)
    return lambda _prompt: next(queue)


@pytest.fixture
def run_env(
    layers: fr.Layers,
) -> tuple[fr.Flow, Path]:
    flow = fr.load_flow('base', layers)
    run_dir = layers.repo / '.skill-tree' / 'runs' / 'r1'
    fr.init_run(run_dir, flow, 'idea text')
    return flow, run_dir


def run(
    run_env: tuple[fr.Flow, Path],
    host: FakeHost,
    *,
    ask: Callable[[str], str] | None = None,
    interactive: bool = True,
    start_from: str | None = None,
) -> int:
    flow, run_dir = run_env
    return fr.run_flow(
        flow,
        run_dir,
        host,
        fr.GateIO(ask=ask or answers('a'), interactive=interactive),
        start_from=start_from,
    )


def statuses(run_dir: Path) -> dict[str, str]:
    return fr.read_state(run_dir)['steps']


def test_happy_path(run_env: tuple[fr.Flow, Path]) -> None:
    host = FakeHost()
    assert run(run_env, host) == 0
    _, run_dir = run_env
    assert [c[1] for c in host.calls] == ['a', 'b', 'c']
    assert statuses(run_dir) == {'a': 'done', 'b': 'done', 'c': 'done'}
    assert (run_dir / 'c.md').read_text() == 'c done'
    assert (run_dir / 'logs' / 'a.jsonl').exists()


def test_missing_output_fails_step(run_env: tuple[fr.Flow, Path]) -> None:
    host = FakeHost(skip_output={'a'})
    assert run(run_env, host) == 1
    assert statuses(run_env[1])['a'] == 'failed'
    assert [c[1] for c in host.calls] == ['a']


def test_nonzero_exit_fails_step(run_env: tuple[fr.Flow, Path]) -> None:
    host = FakeHost(exit_codes={'a': 7})
    assert run(run_env, host) == 1
    assert statuses(run_env[1])['a'] == 'failed'


def test_resume_skips_done_steps(run_env: tuple[fr.Flow, Path]) -> None:
    assert run(run_env, FakeHost(skip_output={'c'})) == 1
    host = FakeHost()
    assert run(run_env, host) == 0
    assert [c[1] for c in host.calls] == ['c']


def test_from_reruns_that_step_and_later(
    run_env: tuple[fr.Flow, Path],
) -> None:
    run(run_env, FakeHost())
    host = FakeHost()
    assert run(run_env, host, start_from='b') == 0
    assert [c[1] for c in host.calls] == ['b', 'c']


def test_from_unknown_step(run_env: tuple[fr.Flow, Path]) -> None:
    with pytest.raises(fr.FlowError, match='zzz'):
        run(run_env, FakeHost(), start_from='zzz')


def test_gate_rerun_then_approve(run_env: tuple[fr.Flow, Path]) -> None:
    host = FakeHost()
    assert run(run_env, host, ask=answers('r', 'a')) == 0
    assert [c[1] for c in host.calls] == ['a', 'b', 'b', 'c']


def test_gate_quit_pauses(run_env: tuple[fr.Flow, Path]) -> None:
    host = FakeHost()
    assert run(run_env, host, ask=answers('q')) == fr.PAUSED_EXIT
    assert statuses(run_env[1])['b'] == 'awaiting-approval'
    resumed = FakeHost()
    assert run(run_env, resumed, ask=answers('a')) == 0
    assert [c[1] for c in resumed.calls] == ['c']


def test_gate_bad_answer_reasks(run_env: tuple[fr.Flow, Path]) -> None:
    assert run(run_env, FakeHost(), ask=answers('huh', 'a')) == 0


def test_gate_edit_opens_editor(
    run_env: tuple[fr.Flow, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: Any) -> Any:  # noqa: ANN401
        opened.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setenv('EDITOR', 'myedit --wait')
    monkeypatch.delenv('VISUAL', raising=False)
    monkeypatch.setattr(fr.subprocess, 'run', fake_run)
    assert run(run_env, FakeHost(), ask=answers('e', 'a')) == 0
    assert opened == [['myedit', '--wait', str(run_env[1] / 'b.md')]]


def test_gate_non_tty_pauses(run_env: tuple[fr.Flow, Path]) -> None:
    host = FakeHost()
    assert run(run_env, host, interactive=False) == fr.PAUSED_EXIT
    assert statuses(run_env[1])['b'] == 'awaiting-approval'


def test_interactive_step_needs_tty(layers: fr.Layers) -> None:
    write(
        layers.user / 'i.toml',
        '[[steps]]\nid = "g"\nskill = "g"\nout = "d.md"\n'
        'gate = "interactive"\n',
    )
    flow = fr.load_flow('i', layers)
    run_dir = layers.repo / 'r'
    fr.init_run(run_dir, flow, 'x')
    host = FakeHost()
    no_tty = fr.GateIO(ask=answers(), interactive=False)
    assert fr.run_flow(flow, run_dir, host, no_tty) == fr.PAUSED_EXIT
    assert host.calls == []
    tty = fr.GateIO(ask=answers(), interactive=True)
    assert fr.run_flow(flow, run_dir, host, tty) == 0
    assert host.calls == [('interactive', 'g')]


def test_max_steps_caps_a_run(layers: fr.Layers) -> None:
    write(layers.user / 'cap.toml', child('max_steps = 2\n'))
    flow = fr.load_flow('cap', layers)
    run_dir = layers.repo / 'r'
    fr.init_run(run_dir, flow, 'x')
    host = FakeHost()
    gate = fr.GateIO(ask=answers('r', 'a'), interactive=True)
    code = fr.run_flow(flow, run_dir, host, gate)
    assert code == fr.PAUSED_EXIT
    assert [c[1] for c in host.calls] == ['a', 'b']


def test_flow_changed_since_run_started(
    run_env: tuple[fr.Flow, Path],
    layers: fr.Layers,
) -> None:
    write(layers.user / 'base.toml', child('[patch]\nremove = ["c"]\n'))
    edited = fr.load_flow('base', layers)
    _, run_dir = run_env
    host = FakeHost()
    gate = fr.GateIO(ask=answers('a'), interactive=True)
    assert fr.run_flow(edited, run_dir, host, gate) == 0
    assert statuses(run_dir) == {'a': 'done', 'b': 'done'}


# --- run dirs + git exclude -----------------------------------------------


def test_new_run_dir_adds_git_exclude(layers: fr.Layers) -> None:
    run_dir = fr.new_run_dir(layers.repo)
    assert run_dir.parent == layers.repo / '.skill-tree' / 'runs'
    exclude = layers.repo / '.git' / 'info' / 'exclude'
    assert '.skill-tree/runs/' in exclude.read_text().splitlines()
    fr.new_run_dir(layers.repo)
    assert exclude.read_text().count('.skill-tree/runs/') == 1


def test_latest_run(layers: fr.Layers) -> None:
    runs = layers.repo / '.skill-tree' / 'runs'
    (runs / '20260101T000000Z').mkdir(parents=True)
    (runs / '20260202T000000Z').mkdir()
    assert fr.latest_run(layers.repo) == runs / '20260202T000000Z'


def test_find_repo_root(tmp_path: Path) -> None:
    (tmp_path / '.git').mkdir()
    nested = tmp_path / 'a' / 'b'
    nested.mkdir(parents=True)
    assert fr.find_repo_root(nested) == tmp_path


# --- CLI ------------------------------------------------------------------


@pytest.fixture
def cli_env(
    layers: fr.Layers,
    monkeypatch: pytest.MonkeyPatch,
) -> fr.Layers:
    monkeypatch.chdir(layers.repo)
    monkeypatch.setattr(fr, 'default_layers', lambda _cwd: layers)
    monkeypatch.setattr(fr, 'make_host', lambda _name: FakeHost())
    monkeypatch.setattr(fr, '_stdin_is_tty', lambda: True)
    monkeypatch.setattr('builtins.input', answers('a', 'a', 'a'))
    return layers


@pytest.mark.usefixtures('cli_env')
def test_cli_no_args_prints_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert fr.main([]) == 2
    assert 'usage' in capsys.readouterr().out.lower()


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert fr.main(['--version']) == 0
    assert 'skill-tree run' in capsys.readouterr().out


def test_cli_dry_run_ok(
    cli_env: fr.Layers,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert fr.main(['--flow', 'base', '--dry-run']) == 0
    assert 'skill-c' in capsys.readouterr().out
    assert not (cli_env.repo / '.skill-tree' / 'runs').exists()


def test_cli_dry_run_missing_skill(
    cli_env: fr.Layers,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write(
        cli_env.user / 'work.toml',
        child('[patch.replace.b]\nskill = "to-sync-point"\n'),
    )
    assert fr.main(['--flow', 'work', '--dry-run']) == 1
    assert 'to-sync-point' in capsys.readouterr().err


@pytest.mark.usefixtures('cli_env')
def test_cli_bad_flow_is_clean_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert fr.main(['--flow', 'nope', 'idea']) == 1
    assert 'nope' in capsys.readouterr().err


def test_cli_full_run_then_resume(
    cli_env: fr.Layers,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert fr.main(['--flow', 'base', 'build a thing']) == 0
    run_dir = fr.latest_run(cli_env.repo)
    assert run_dir is not None
    assert fr.read_state(run_dir)['idea'] == 'build a thing'
    assert fr.main(['--resume']) == 0
    assert 'already done' in capsys.readouterr().out


@pytest.mark.usefixtures('cli_env')
def test_cli_resume_without_runs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert fr.main(['--resume']) == 1
    assert 'no runs' in capsys.readouterr().err


@pytest.mark.usefixtures('cli_env')
def test_cli_list_flows(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert fr.main(['--list']) == 0
    assert 'base' in capsys.readouterr().out


def test_builtin_default_flow_is_valid() -> None:
    layers = fr.Layers(
        repo=Path('/nonexistent'),
        user=Path('/nonexistent'),
        builtin=REPO_ROOT / 'flows',
    )
    flow = fr.load_flow('default', layers)
    assert ids(flow)[0] == 'grill'
    assert fr.check_flow(flow, {s.skill: Path() for s in flow.steps}) == []


def test_skill_tree_dispatches_run(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / 'scripts' / 'skill_tree_cli.py'),
            'run',
            '--version',
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert 'skill-tree run' in result.stdout


# --- Claude host ----------------------------------------------------------


def make_skill(directory: Path) -> Path:
    write(directory / 'SKILL.md', '---\nname: x\ndescription: d\n---\n')
    return directory


@pytest.fixture
def claude_world(tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / 'repo'
    home = tmp_path / 'home'
    plugin = tmp_path / 'cache' / 'skill-tree' / '1.0'
    disabled = tmp_path / 'cache' / 'off' / '1.0'
    make_skill(repo / '.claude' / 'skills' / 'arch-review')
    make_skill(repo / '.claude' / 'skills' / 'to-spec')
    make_skill(home / '.claude' / 'skills' / 'to-sync-point')
    make_skill(home / '.claude' / 'skills' / 'to-tickets')
    for name in ('to-spec', 'to-tickets', 'grill-for-planning'):
        make_skill(plugin / 'skills' / name)
    (plugin / 'skills' / 'not-a-skill').mkdir()
    make_skill(disabled / 'skills' / 'hidden')
    plugins = [
        {
            'id': 'skill-tree@skill-tree',
            'enabled': True,
            'installPath': str(plugin),
        },
        {'id': 'off@x', 'enabled': False, 'installPath': str(disabled)},
        {
            'id': 'gone@x',
            'enabled': True,
            'installPath': str(tmp_path / 'nope'),
        },
    ]
    data = tmp_path / 'plugins.json'
    data.write_text(json.dumps(plugins))
    binary = tmp_path / 'bin' / 'claude'
    write(binary, f'#!/usr/bin/env bash\ncat {data}\n')
    binary.chmod(0o755)
    return {'repo': repo, 'home': home, 'plugin': plugin, 'binary': binary}


def claude_skills(world: dict[str, Path]) -> dict[str, Path]:
    host = fr.ClaudeHost(str(world['binary']), home=world['home'])
    return host.list_skills(world['repo'])


@pytest.mark.parametrize(
    ('name', 'expected'),
    [
        ('arch-review', 'repo/.claude/skills/arch-review'),
        ('to-spec', 'repo/.claude/skills/to-spec'),
        ('to-sync-point', 'home/.claude/skills/to-sync-point'),
        ('to-tickets', 'home/.claude/skills/to-tickets'),
        ('grill-for-planning', 'skill-tree/1.0/skills/grill-for-planning'),
        ('skill-tree:to-spec', 'skill-tree/1.0/skills/to-spec'),
        ('skill-tree:grill-for-planning', '1.0/skills/grill-for-planning'),
    ],
)
def test_claude_skill_resolution(
    claude_world: dict[str, Path],
    name: str,
    expected: str,
) -> None:
    assert str(claude_skills(claude_world)[name]).endswith(expected)


@pytest.mark.parametrize(
    'absent',
    ['hidden', 'off:hidden', 'not-a-skill', 'skill-tree:not-a-skill'],
)
def test_claude_skips_disabled_and_non_skills(
    claude_world: dict[str, Path],
    absent: str,
) -> None:
    assert absent not in claude_skills(claude_world)


def test_claude_plugin_list_failure_is_flow_error(tmp_path: Path) -> None:
    binary = write(
        tmp_path / 'claude',
        '#!/usr/bin/env bash\necho no >&2\nexit 1\n',
    )
    binary.chmod(0o755)
    host = fr.ClaudeHost(str(binary), home=tmp_path)
    with pytest.raises(fr.FlowError, match='no'):
        host.list_skills(tmp_path)


def test_claude_missing_binary_is_flow_error(tmp_path: Path) -> None:
    host = fr.ClaudeHost(str(tmp_path / 'nope'), home=tmp_path)
    with pytest.raises(fr.FlowError, match='claude'):
        host.list_skills(tmp_path)


@pytest.mark.parametrize(
    ('tool', 'expected'),
    [
        ('write', 'Write'),
        ('read', 'Read'),
        ('shell', 'Bash'),
        ('shell(git:*)', 'Bash(git:*)'),
        ('Edit', 'Edit'),
        ('mcp__x__y', 'mcp__x__y'),
    ],
)
def test_claude_tool_mapping(tool: str, expected: str) -> None:
    assert fr.claude_tool(tool) == expected


def argv_of(tmp_path: Path, call: Callable[[fr.ClaudeHost], int]) -> list[str]:
    argv_file = tmp_path / 'argv'
    binary = fake_copilot(tmp_path, f'printf "%s\\n" "$@" > {argv_file}\n')
    call(fr.ClaudeHost(str(binary), home=tmp_path))
    return argv_file.read_text().splitlines()


def opts(tmp_path: Path, **overrides: Any) -> fr.RunOptions:  # noqa: ANN401
    base: dict[str, Any] = {
        'cwd': tmp_path,
        'model': None,
        'allow_tools': (),
        'allow_all': False,
        'timeout': None,
    }
    return fr.RunOptions(**{**base, **overrides})


def test_claude_headless_argv(tmp_path: Path) -> None:
    argv = argv_of(
        tmp_path,
        lambda host: host.run_headless(
            '--sneaky prompt',
            opts(
                tmp_path,
                model='opus',
                allow_tools=('write', 'shell(git:*)'),
            ),
            tmp_path / 'log',
        ),
    )
    assert argv[0] == '-p'
    assert argv[argv.index('--') + 1] == '--sneaky prompt'
    assert argv[argv.index('--output-format') + 1] == 'stream-json'
    assert '--verbose' in argv
    assert argv[argv.index('--model') + 1] == 'opus'
    tools = argv[argv.index('--allowedTools') + 1]
    assert tools == 'Write,Bash(git:*)'
    assert '--permission-mode' not in argv


def test_claude_headless_allow_all(tmp_path: Path) -> None:
    argv = argv_of(
        tmp_path,
        lambda host: host.run_headless(
            'p',
            opts(tmp_path, allow_all=True),
            tmp_path / 'log',
        ),
    )
    assert argv[argv.index('--permission-mode') + 1] == 'bypassPermissions'
    assert '--allowedTools' not in argv


def test_claude_interactive_argv(tmp_path: Path) -> None:
    argv = argv_of(
        tmp_path,
        lambda host: host.run_interactive(
            'hello',
            opts(tmp_path, allow_tools=('write',)),
        ),
    )
    assert '-p' not in argv
    assert argv[-2:] == ['--', 'hello']
    assert argv[argv.index('--allowedTools') + 1] == 'Write'


@pytest.mark.parametrize(
    ('name', 'expected'),
    [('copilot', fr.CopilotHost), ('claude', fr.ClaudeHost)],
)
def test_make_host(name: str, expected: type) -> None:
    assert isinstance(fr.make_host(name), expected)


def test_cli_host_flag_overrides_flow_and_sticks_on_resume(
    cli_env: fr.Layers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chosen: list[str] = []

    def fake_make_host(name: str) -> FakeHost:
        chosen.append(name)
        return FakeHost()

    monkeypatch.setattr(fr, 'make_host', fake_make_host)
    assert fr.main(['--flow', 'base', '--host', 'claude', 'x']) == 0
    run_dir = fr.latest_run(cli_env.repo)
    assert run_dir is not None
    assert fr.read_state(run_dir)['host'] == 'claude'
    assert fr.main(['--from', 'c']) == 0
    assert set(chosen) == {'claude'}


def test_dry_run_header_shows_effective_host(
    cli_env: fr.Layers,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert fr.main(['--flow', 'base', '--host', 'claude', '--dry-run']) == 0
    assert 'host: claude' in capsys.readouterr().out
    assert cli_env.repo.exists()


# --- e2e (real Copilot, costs tokens: pytest -m e2e) ----------------------


@pytest.mark.e2e
@pytest.mark.parametrize('host', ['copilot', 'claude'])
def test_e2e_real_host(tmp_path: Path, host: str) -> None:
    if shutil.which(host) is None:
        pytest.skip(f'no {host} CLI')
    repo = tmp_path / 'repo'
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    # Both hosts read a repo's .claude/skills.
    write(
        repo / '.claude' / 'skills' / 'echo-fixture' / 'SKILL.md',
        '---\nname: echo-fixture\ndescription: Test fixture.\n---\n\n'
        'Write exactly `PONG` and nothing else to the output file.\n',
    )
    write(
        repo / '.claude' / 'skills' / 'shout-fixture' / 'SKILL.md',
        '---\nname: shout-fixture\ndescription: Test fixture.\n---\n\n'
        'Read the input file and write its contents followed by `!` to the'
        ' output file, nothing else.\n',
    )
    write(
        repo / '.skill-tree' / 'flow.toml',
        f'host = "{host}"\nallow_tools = ["write"]\n'
        '[[steps]]\nid = "ping"\nskill = "echo-fixture"\nout = "ping.md"\n'
        'timeout = 300\n'
        '[[steps]]\nid = "shout"\nskill = "shout-fixture"\n'
        'in = ["ping.md"]\nout = "shout.md"\ntimeout = 300\n',
    )
    env = {**os.environ, 'XDG_CONFIG_HOME': str(tmp_path / 'xdg')}
    result = subprocess.run(
        [str(REPO_ROOT / 'scripts' / 'skill-tree'), 'run', 'say pong'],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run_dir = fr.latest_run(repo)
    assert run_dir is not None
    assert (run_dir / 'ping.md').read_text().strip() == 'PONG'
    assert (run_dir / 'shout.md').read_text().strip() == 'PONG!'
