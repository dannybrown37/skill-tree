import type { Crew, Member, Mood, Steps } from '../types'

export const SPRITE_W = 8
export const SPRITE_H = 3
const BODY_W = 6
const MAX_MEMBERS = 40
const MAX_BRIEF = 120
const MAX_NOTE = 80
const MAX_TOTAL = 999

type Frame = readonly [string, string, string]

type Character = {
  id: string
  color: string
  rest: Frame
  busy: readonly Frame[]
  tap: readonly Frame[]
  nap: Frame
  party: readonly Frame[]
  dizzy: Frame
  busyQuips: readonly string[]
}

// Bodies are BODY_W wide; the two columns right of them are the aura, where
// the ? bubble, z's and sparkles float.
export const CHARACTERS: Record<string, Character> = {
  tarn: {
    id: 'tarn',
    color: '#5fa8d3',
    rest: [' ,,,, ', '<(°°)>', '~~~~~~'],
    busy: [
      [' ,,,, ', '<(°o)>', '~^~~^~'],
      [' ,,,, ', '>(o°)<', '^~~^~~'],
      [' ,,,, ', '<(°o)>', '~~^~~^'],
    ],
    tap: [
      [' ,,,, ', '<(°°)>', '~~~~~/'],
      [' ,,,, ', '<(°°)>', '~~~~~_'],
    ],
    nap: ['      ', ',(--),', '~~~~~~'],
    party: [
      ['<(^^)>', "  ''  ", '~~..~~'],
      [' ,,,, ', '<(^^)>', '~~~~~~'],
    ],
    dizzy: [' ,,,, ', '<(@@)>', '~~~~~~'],
    busyQuips: ['making ripples', 'diving deep', 'stirring the lake', 'fishing for bugs', 'blowing bubbles'],
  },
  biker: {
    id: 'biker',
    color: '#e8a33d',
    rest: ['  o   ', ' <|\\  ', '(o)(o)'],
    busy: [
      ['  o   ', ' <|\\  ', '(-)(-)'],
      ['  o   ', ' <|<  ', '(\\)(\\)'],
      ['  o   ', ' <|\\  ', '(|)(|)'],
      ['  o   ', ' <|<  ', '(/)(/)'],
    ],
    tap: [
      [' o    ', '/|\\   ', '/ \\(o)'],
      [' o    ', '/|\\   ', '/ |(o)'],
    ],
    nap: ['      ', ' _o\\  ', '(o)(o)'],
    party: [
      [' \\o/  ', '  |\\  ', '(o)(o)'],
      ['  o   ', ' /|\\  ', '(o)(o)'],
    ],
    dizzy: ['  @   ', ' <|\\  ', '(o)(o)'],
    busyQuips: ['pedaling hard', 'wheels a-spinnin’', 'ringing the bell', 'no hands on the spokes', 'kickstand up!'],
  },
  robot: {
    id: 'robot',
    color: '#9aa5b1',
    rest: ['[o_o] ', '/[=]\\ ', ' d b  '],
    busy: [
      ['[o_o] ', '/[=]-o', ' d b  '],
      ['[0_0]*', '/[=]-O', ' d b  '],
      ['[o_o] ', '/[=]-+', ' d b  '],
    ],
    tap: [
      ['[o_o] ', '/[=]\\ ', ' d b  '],
      ['[o_o] ', '/[=]\\ ', ' d  b '],
    ],
    nap: ['[-_-] ', '/[=]\\ ', ' d b  '],
    party: [
      ['[^_^] ', '\\[=]/ ', ' d b  '],
      ['[^o^] ', '-[=]- ', ' d b  '],
    ],
    dizzy: ['[@_@] ', '/[=]\\ ', ' d b  '],
    busyQuips: ['tightening bolts', 'beep boop, refactoring', 'oiling the gears', 'rewiring the dotfiles', 'calibrating'],
  },
  wizard: {
    id: 'wizard',
    color: '#8f8cf4',
    rest: ['  /\\  ', ' (oo) ', ' /##\\ '],
    busy: [
      ['  /\\ *', ' (oo)/', ' /##\\ '],
      ['  /\\+ ', ' (oo)/', ' /##\\ '],
      ['  /\\ .', ' (oo)/', ' /##\\ '],
    ],
    tap: [
      ['  /\\  ', ' (oo) ', ' /##\\ '],
      ['  /\\  ', ' (oo) ', ' /##| '],
    ],
    nap: ['  /\\  ', ' (--) ', ' /##\\ '],
    party: [
      ['  /\\  ', '\\(^^)/', ' /##\\ '],
      [' */\\* ', ' (^^) ', ' /##\\ '],
    ],
    dizzy: ['  /\\  ', ' (@@) ', ' /##\\ '],
    busyQuips: ['brewing a spell', 'consulting the tome', 'growing new branches', 'waving the wand', 'reading the runes'],
  },
  climber: {
    id: 'climber',
    color: '#d9734e',
    rest: ['  |o  ', '  |\\  ', '  |/\\ '],
    busy: [
      ['  |o/ ', '  |\\  ', '  |/\\ '],
      ['  |\\o ', '  |/  ', '  |\\  '],
    ],
    tap: [
      ['  |o  ', '  |\\  ', '  |/\\ '],
      ['  |o  ', '  |\\  ', '  |/_ '],
    ],
    nap: ['  |   ', '  |(-)', '  |\\_/'],
    party: [
      ['  |\\o/', '  | | ', '  |/ \\'],
      ['  |>o ', '  | |\\', '  |/ \\'],
    ],
    dizzy: ['  |@  ', '  |\\  ', '  |/\\ '],
    busyQuips: ['on belay', 'chalking up', 'reaching for the next hold', 'clipping in', 'scaling the wall'],
  },
  crab: {
    id: 'crab',
    color: '#D97757',
    rest: ['(\\  /)', '(o..o)', "/ '' \\"],
    busy: [
      ['(\\  /)', '(o..o)', "/ '' \\"],
      ['(|  |)', '(o..o)', "\\ '' /"],
    ],
    tap: [
      ['(\\  /)', '(o..o)', "/ '' \\"],
      ['(\\  /)', '(o..o)', "/ '' |"],
    ],
    nap: ['(\\  /)', '(-..-)', "/ '' \\"],
    party: [
      ['\\/  \\/', '(^..^)', "/ '' \\"],
      ['(\\  /)', '(^..^)', " /''\\ "],
    ],
    dizzy: ['(\\  /)', '(@..@)', "/ '' \\"],
    busyQuips: ['scuttling through code', 'pinching bugs', 'making sideways progress', 'digging in the sand', 'clacking away'],
  },
}

const REPO_CHARACTER: Record<string, string> = {
  tarn: 'tarn',
  'the-letter-station': 'biker',
  dotfiles: 'robot',
  'skill-tree': 'wizard',
  'git-a-grip': 'climber',
}

const AURA: Record<Mood, readonly Frame[]> = {
  busy: [['  ', '  ', '  ']],
  tapping: [
    ['? ', '  ', '  '],
    [' ?', '  ', '  '],
  ],
  napping: [
    ['  ', 'z ', '  '],
    [' Z', 'z ', '  '],
    ['Z ', ' z', '  '],
  ],
  celebrating: [
    ['* ', '  ', ' *'],
    [' *', '* ', '  '],
  ],
  dizzy: [
    ['@ ', '  ', '  '],
    [' @', '  ', '  '],
  ],
  gone: [['  ', '  ', '  ']],
  booting: [
    ['  ', '  ', '. '],
    ['  ', '  ', '..'],
  ],
}

const QUIPS: Record<Exclude<Mood, 'busy'>, readonly string[]> = {
  tapping: ['psst… you there?','needs your eyes', 'tap tap tap…', 'your move, captain', 'waiting on you', 'got a question!'],
  napping: ['napping', 'dreaming of green CI', 'zzz…', 'resting its eyes', 'on a coffee break'],
  celebrating: ['ta-da!', 'victory lap!', 'all steps done!', 'nailed it', 'ready for review'],
  dizzy: ['something broke…', 'seeing stars', 'ouch, an error'],
  gone: ['gone home', 'signed off'],
  booting: ['waking up…', 'stretching…', 'lacing its boots'],
}

const MOOD_WORD: [Mood, string][] = [
  ['tapping', 'needs you'],
  ['busy', 'busy'],
  ['celebrating', 'done'],
  ['dizzy', 'dizzy'],
  ['booting', 'waking'],
  ['napping', 'napping'],
  ['gone', 'gone'],
]

export const characterFor = (repo: string): Character =>
  CHARACTERS[Object.hasOwn(REPO_CHARACTER, repo) ? (REPO_CHARACTER[repo] ?? 'crab') : 'crab'] ?? (CHARACTERS.crab as Character)

const characterById = (id: string): Character => (Object.hasOwn(CHARACTERS, id) ? CHARACTERS[id] : undefined) ?? (CHARACTERS.crab as Character)

export const repoFromCwd = (cwd: string): string => {
  const path = cwd.replace(/\/+$/, '')
  const worktree = /\/([^/]+)-worktrees\/[^/]+/.exec(path)
  if (worktree) return worktree[1] ?? ''
  // A session can sit in a subfolder of a plain clone: the repo is the clone.
  const project = /\/projects\/([^/]+)/.exec(path)
  if (project) return project[1] ?? ''
  return path.slice(path.lastIndexOf('/') + 1)
}

export const moodFor = (state: string, steps: Steps | null): Mood => {
  if (state === 'working') return 'busy'
  if (state === 'waiting') return 'tapping'
  if (state === 'idle') return steps && steps.done >= steps.total ? 'celebrating' : 'napping'
  if (state === 'error') return 'dizzy'
  if (state === 'exited' || state === 'gone') return 'gone'
  return 'booting'
}

const pick = <T>(list: readonly T[], tick: number): T => list[((tick % list.length) + list.length) % list.length] as T

const bodyFrames = (c: Character, mood: Mood): readonly Frame[] => {
  if (mood === 'busy') return c.busy
  if (mood === 'tapping') return c.tap
  if (mood === 'celebrating') return c.party
  if (mood === 'dizzy') return [c.dizzy]
  if (mood === 'napping' || mood === 'gone') return [c.nap]
  return [c.rest]
}

export const frameFor = (characterId: string, mood: Mood, tick: number): string[] => {
  const body = pick(bodyFrames(characterById(characterId), mood), tick)
  const aura = pick(AURA[mood], tick)
  return body.map((line, i) => line.padEnd(BODY_W).slice(0, BODY_W) + (aura[i] ?? '  '))
}

const hash = (s: string): number => {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return h >>> 0
}

export const quipFor = (characterId: string, mood: Mood, name: string, slot: number): string => {
  const list = mood === 'busy' ? characterById(characterId).busyQuips : QUIPS[mood]
  return pick(list, hash(`${name}:${mood}`) + slot)
}

export const colorFor = (characterId: string): string => characterById(characterId).color

export const stepBar = (steps: Steps, width: number): string => {
  const filled = Math.round((width * steps.done) / steps.total)
  return '█'.repeat(filled) + '░'.repeat(Math.max(0, width - filled))
}

// Text refuses control characters; fleet passes through whatever a brief held.
const clean = (s: string, max: number): string => {
  const line = s.replace(/[\u0000-\u001f\u007f-\u009f]+/g, ' ').replace(/\s+/g, ' ').trim()
  const chars = Array.from(line)
  return chars.length > max ? `${chars.slice(0, max - 1).join('')}…` : line
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

export const parseSteps = (raw: unknown): Steps | null => {
  if (!isRecord(raw)) return null
  const { done, total, note } = raw
  if (!Number.isInteger(done) || !Number.isInteger(total) || (total as number) < 1) return null
  const t = Math.min(MAX_TOTAL, total as number)
  return {
    done: Math.min(t, Math.max(0, done as number)),
    total: t,
    note: typeof note === 'string' ? clean(note, MAX_NOTE) : '',
  }
}

export type Include = 'managed' | 'all'

const memberOf = (row: unknown): Member | null => {
  if (!isRecord(row) || typeof row.name !== 'string' || typeof row.state !== 'string') return null
  const repo = repoFromCwd(typeof row.cwd === 'string' ? row.cwd : '')
  const steps = parseSteps(row.steps)
  return {
    name: clean(row.name, 60),
    repo: clean(repo, 60),
    character: characterFor(repo).id,
    state: clean(row.state, 20),
    mood: moodFor(row.state, steps),
    brief: clean(typeof row.message === 'string' ? row.message : '', MAX_BRIEF),
    steps,
  }
}

export const parseFleet = (stdout: string, include: Include): Crew => {
  let rows: unknown
  try {
    rows = JSON.parse(stdout)
  } catch {
    return { members: [], error: 'fleet ls --json did not print JSON' }
  }
  if (!Array.isArray(rows)) return { members: [], error: 'fleet ls --json did not print a list' }
  const members = rows
    .filter(row => include === 'all' || (isRecord(row) && row.managed === true))
    .map(memberOf)
    .filter((m): m is Member => m !== null)
    .slice(0, MAX_MEMBERS)
  return { members, error: '' }
}

export const summary = (members: readonly Member[]): string => {
  if (members.length === 0) return 'no crew aboard'
  return MOOD_WORD.map(([mood, word]) => [members.filter(m => m.mood === mood).length, word] as const)
    .filter(([n]) => n > 0)
    .map(([n, word]) => `${n} ${word}`)
    .join(' · ')
}

// `fleet` is a shell alias, not on PATH, and $.process.run has no shell.
export const fleetArgv = (option: string, env: { home: string; dotfiles: string }): string[] => {
  const configured = option.trim().replace(/^~(?=\/)/, env.home)
  const script = configured || (env.dotfiles ? `${env.dotfiles}/scripts/fleet.sh` : `${env.home}/projects/dotfiles/scripts/fleet.sh`)
  return [script, 'ls', '--json']
}
