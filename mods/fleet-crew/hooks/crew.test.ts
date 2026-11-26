import { describe, expect, test } from 'claude-code/testing'

import {
  CHARACTERS,
  SPRITE_H,
  SPRITE_W,
  characterFor,
  fleetArgv,
  frameFor,
  moodFor,
  parseFleet,
  parseSteps,
  quipFor,
  repoFromCwd,
  stepBar,
  summary,
} from './crew'
import type { Mood } from '../types'

describe('repoFromCwd', () => {
  const cases: [string, string][] = [
    ['/home/danny/projects/tarn-worktrees/mobile-polish', 'tarn'],
    ['/home/danny/projects/the-letter-station-worktrees/bike-endless/', 'the-letter-station'],
    ['/home/danny/projects/skill-tree-worktrees/fleet-crew', 'skill-tree'],
    ['/home/danny/projects/dotfiles', 'dotfiles'],
    ['/home/danny/projects/git-a-grip/', 'git-a-grip'],
    ['/srv/x-worktrees/y/deeper/still', 'x'],
    ['/home/danny/projects/dotfiles/scripts/fleet', 'dotfiles'],
    ['/home/danny/projects/tarn/docs', 'tarn'],
    ['', ''],
    ['/', ''],
  ]
  for (const [cwd, repo] of cases) {
    test(`${JSON.stringify(cwd)} -> ${JSON.stringify(repo)}`, () => {
      expect(repoFromCwd(cwd)).toBe(repo)
    })
  }
})

describe('characterFor', () => {
  const cases: [string, string][] = [
    ['tarn', 'tarn'],
    ['the-letter-station', 'biker'],
    ['dotfiles', 'robot'],
    ['skill-tree', 'wizard'],
    ['git-a-grip', 'climber'],
    ['homestead-hq', 'crab'],
    ['', 'crab'],
    ['__proto__', 'crab'],
    ['constructor', 'crab'],
  ]
  for (const [repo, id] of cases) {
    test(`${repo || '(none)'} is the ${id}`, () => {
      expect(characterFor(repo).id).toBe(id)
    })
  }
})

describe('moodFor', () => {
  const cases: [string, ReturnType<typeof parseSteps>, Mood][] = [
    ['working', null, 'busy'],
    ['waiting', null, 'tapping'],
    ['idle', null, 'napping'],
    ['idle', { done: 2, total: 5, note: '' }, 'napping'],
    ['idle', { done: 5, total: 5, note: '' }, 'celebrating'],
    ['working', { done: 5, total: 5, note: '' }, 'busy'],
    ['error', null, 'dizzy'],
    ['exited', null, 'gone'],
    ['gone', null, 'gone'],
    ['unknown', null, 'booting'],
    ['dancing', null, 'booting'],
  ]
  for (const [state, steps, mood] of cases) {
    test(`${state}${steps ? ` ${steps.done}/${steps.total}` : ''} -> ${mood}`, () => {
      expect(moodFor(state, steps)).toBe(mood)
    })
  }
})

describe('parseSteps', () => {
  const cases: [unknown, ReturnType<typeof parseSteps>][] = [
    [{ done: 2, total: 5, note: 'tests' }, { done: 2, total: 5, note: 'tests' }],
    [{ done: 0, total: 3 }, { done: 0, total: 3, note: '' }],
    [{ done: 9, total: 4, note: 'x' }, { done: 4, total: 4, note: 'x' }],
    [{ done: -2, total: 4 }, { done: 0, total: 4, note: '' }],
    [{ done: 1, total: 2, note: 'n'.repeat(200) }, { done: 1, total: 2, note: `${'n'.repeat(79)}…` }],
    [{ done: 1, total: 0 }, null],
    [{ done: '1', total: 3 }, null],
    [{ done: 1.5, total: 3 }, null],
    [{ done: 1, total: 1e9 }, { done: 1, total: 999, note: '' }],
    [null, null],
    [undefined, null],
    ['2/5', null],
    [[2, 5], null],
  ]
  for (const [raw, steps] of cases) {
    test(`${JSON.stringify(raw) ?? 'undefined'}`, () => {
      expect(parseSteps(raw)).toEqual(steps)
    })
  }
})

describe('stepBar', () => {
  const cases: [number, number, number, string][] = [
    [0, 4, 8, '░░░░░░░░'],
    [2, 4, 8, '████░░░░'],
    [4, 4, 8, '████████'],
    [1, 3, 6, '██░░░░'],
    [1, 3, 0, ''],
  ]
  for (const [done, total, width, bar] of cases) {
    test(`${done}/${total} at ${width}`, () => {
      expect(stepBar({ done, total, note: '' }, width)).toBe(bar)
    })
  }
})

describe('parseFleet', () => {
  const row = {
    name: 'bike-endless',
    kind: 'claude',
    state: 'working',
    managed: true,
    where: 'fleet',
    cwd: '/home/danny/projects/the-letter-station-worktrees/bike-endless',
    message: 'Make the bike ride endless',
    steps: { done: 1, total: 4, note: 'track gen' },
  }

  test('a fleet row becomes a crew member with repo, character, mood and steps', () => {
    expect(parseFleet(JSON.stringify([row]), 'managed')).toEqual({
      members: [
        {
          name: 'bike-endless',
          repo: 'the-letter-station',
          character: 'biker',
          state: 'working',
          mood: 'busy',
          brief: 'Make the bike ride endless',
          steps: { done: 1, total: 4, note: 'track gen' },
        },
      ],
      error: '',
    })
  })

  test('managed keeps fleet-started agents only; all keeps every session', () => {
    const stray = { ...row, name: 'tarn', managed: false, cwd: '/home/danny/projects/tarn' }
    const out = JSON.stringify([row, stray])
    expect(parseFleet(out, 'managed').members.map(m => m.name)).toEqual(['bike-endless'])
    expect(parseFleet(out, 'all').members.map(m => m.name)).toEqual(['bike-endless', 'tarn'])
  })

  test('a row without steps falls back to state alone', () => {
    const { steps: _steps, ...bare } = row
    expect(parseFleet(JSON.stringify([bare]), 'all').members[0]?.steps).toBeNull()
  })

  test('the brief is one line, clipped', () => {
    const long = { ...row, message: `first line\nsecond ${'x'.repeat(300)}` }
    const brief = parseFleet(JSON.stringify([long]), 'all').members[0]?.brief ?? ''
    expect(brief.includes('\n')).toBe(false)
    expect(brief.length).toBeLessThanOrEqual(120)
  })

  const broken: [string, string][] = [
    ['not json', 'fleet ls --json did not print JSON'],
    ['{"name": "x"}', 'fleet ls --json did not print a list'],
  ]
  for (const [out, error] of broken) {
    test(`broken output ${JSON.stringify(out)} is an error, not a throw`, () => {
      expect(parseFleet(out, 'all')).toEqual({ members: [], error })
    })
  }

  test('junk rows are skipped, the rest kept', () => {
    const out = JSON.stringify([null, 3, { state: 'idle' }, { ...row, name: 42 }, row])
    expect(parseFleet(out, 'all').members.map(m => m.name)).toEqual(['bike-endless'])
  })

  test('at most 40 members', () => {
    const many = Array.from({ length: 100 }, (_, i) => ({ ...row, name: `a${i}` }))
    expect(parseFleet(JSON.stringify(many), 'all').members).toHaveLength(40)
  })
})

describe('sprites', () => {
  const moods: Mood[] = ['busy', 'tapping', 'napping', 'celebrating', 'dizzy', 'gone', 'booting']
  for (const c of Object.values(CHARACTERS)) {
    for (const mood of moods) {
      test(`${c.id} ${mood}: every frame is ${SPRITE_W}x${SPRITE_H}`, () => {
        for (let tick = 0; tick < 12; tick++) {
          const lines = frameFor(c.id, mood, tick)
          expect(lines).toHaveLength(SPRITE_H)
          for (const line of lines) expect([...line]).toHaveLength(SPRITE_W)
        }
      })
    }
  }

  const animated: Mood[] = ['busy', 'tapping', 'celebrating']
  for (const mood of animated) {
    test(`${mood} moves between ticks`, () => {
      for (const c of Object.values(CHARACTERS)) {
        expect(frameFor(c.id, mood, 0)).not.toEqual(frameFor(c.id, mood, 1))
      }
    })
  }

  test('tapping always shows the ? bubble somewhere in its loop', () => {
    for (const c of Object.values(CHARACTERS)) {
      expect(frameFor(c.id, 'tapping', 0).join('')).toContain('?')
    }
  })

  test('an unknown character draws as the crab', () => {
    expect(frameFor('nobody', 'busy', 0)).toEqual(frameFor('crab', 'busy', 0))
  })
})

describe('quips', () => {
  test('a quip is stable for the same agent, mood and slot', () => {
    expect(quipFor('crab', 'busy', 'a', 0)).toBe(quipFor('crab', 'busy', 'a', 0))
  })

  test('working quips speak in the character’s voice', () => {
    const quips = new Set(Array.from({ length: 40 }, (_, i) => quipFor('biker', 'busy', `n${i}`, 0)))
    expect([...quips].some(q => /pedal|wheel|bell|kickstand|spokes/i.test(q))).toBe(true)
  })

  test('waiting quips are short and name nobody', () => {
    const quips = new Set(Array.from({ length: 40 }, (_, i) => quipFor('crab', 'tapping', `n${i}`, 0)))
    expect([...quips].every(q => q.length > 0 && q.length <= 34)).toBe(true)
    expect([...quips].some(q => /danny/i.test(q))).toBe(false)
  })

  test('a long brief is cut on a code point, never mid-emoji', () => {
    const row = { name: 'a', state: 'idle', managed: true, cwd: '/p/x', message: `${'x'.repeat(118)}🦀🦀🦀` }
    const brief = parseFleet(JSON.stringify([row]), 'all').members[0]?.brief ?? ''
    expect(brief).toBe(`${'x'.repeat(118)}🦀…`)
  })
})

describe('fleetArgv', () => {
  const cases: [string, { home: string; dotfiles: string }, string][] = [
    ['', { home: '/h', dotfiles: '/d' }, '/d/scripts/fleet.sh'],
    ['', { home: '/h', dotfiles: '' }, '/h/projects/dotfiles/scripts/fleet.sh'],
    ['~/bin/fleet', { home: '/h', dotfiles: '/d' }, '/h/bin/fleet'],
    ['  /opt/fleet  ', { home: '/h', dotfiles: '/d' }, '/opt/fleet'],
  ]
  for (const [option, env, script] of cases) {
    test(`${JSON.stringify(option)} -> ${script}`, () => {
      expect(fleetArgv(option, env)).toEqual([script, 'ls', '--json'])
    })
  }
})

test('control characters in fleet output never reach a Text', () => {
  const row = { name: 'a\u001b[31mb', state: 'idle', managed: true, cwd: '/p/x', message: 'hi\u0007\tthere', steps: { done: 0, total: 2, note: 'n\u0000o' } }
  const [m] = parseFleet(JSON.stringify([row]), 'all').members
  expect(m?.name).toBe('a [31mb')
  expect(m?.brief).toBe('hi there')
  expect(m?.steps?.note).toBe('n o')
})

describe('summary', () => {
  test('counts by mood, the ones that need Danny first', () => {
    const m = (mood: Mood) => ({ name: '', repo: '', character: 'crab', state: '', mood, brief: '', steps: null })
    expect(summary([m('busy'), m('tapping'), m('busy'), m('napping')])).toBe('1 needs you · 2 busy · 1 napping')
    expect(summary([])).toBe('no crew aboard')
  })
})
