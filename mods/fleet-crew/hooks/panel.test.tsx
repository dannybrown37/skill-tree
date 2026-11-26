import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

const PANE = {
  plugin: 'fleet-crew',
  component: 'Pane',
  requestId: 'fleet-crew',
  props: { title: 'Fleet crew', isFocused: false, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

const ROWS = [
  {
    name: 'bike-endless',
    kind: 'claude',
    state: 'working',
    managed: true,
    where: 'fleet',
    cwd: '/home/danny/projects/the-letter-station-worktrees/bike-endless',
    message: 'Make the bike ride endless',
    steps: { done: 3, total: 5, note: 'track gen' },
  },
  {
    name: 'https-serve',
    kind: 'claude',
    state: 'waiting',
    managed: true,
    where: 'fleet',
    cwd: '/home/danny/projects/homestead-hq-worktrees/https-serve',
    message: 'Serve over https',
    steps: null,
  },
]

type World = { runs: string[][]; out: { stdout: string; exitCode: number; stderr: string }; panes: string[]; slowPanes?: boolean }

async function boot($: Engine, on: On, world: World) {
  const clock = mock.clock(on, { now: 0 })
  mock.env(on, { HOME: '/h', DOTFILES_DIR: '/d' })
  on('command.register', () => ({ value: { command: 'crew' } }))
  on('ui.panes', async () => {
    const shown = world.panes.map(id => ({ id }))
    if (world.slowPanes) {
      world.slowPanes = false
      await clock.sleep(500)
    }
    return { value: shown } as never
  })
  on('ui.open', (_$, e) => {
    world.panes.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('ui.close', (_$, e) => {
    world.panes = world.panes.filter(id => id !== e.id)
    return { value: undefined } as never
  })
  on('process.run', (_$, e) => {
    world.runs.push([...e.argv])
    return { value: { ...world.out, isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('session.start', (_$, e) => ({ cwd: e.cwd }) as never)
  await $.session.start({ source: 'startup', cwd: '/', surface: 'terminal', isInteractive: true } as never)
  return clock
}

const fresh = (): World => ({ runs: [], out: { stdout: JSON.stringify(ROWS), exitCode: 0, stderr: '' }, panes: [] })

test('/crew opens the panel after one fleet poll, and closes it again', async ($, on) => {
  const world = fresh()
  await boot($, on, world)
  expect(await $.command.run({ command: 'crew', args: '' } as never)).toMatchObject({ text: 'All hands on deck.' })
  expect(world.panes).toEqual(['fleet-crew'])
  expect(world.runs).toEqual([['/d/scripts/fleet.sh', 'ls', '--json']])
  expect(await $.command.run({ command: 'crew', args: '' } as never)).toMatchObject({ text: 'Crew dismissed.' })
  expect(world.panes).toEqual([])
})

test('polls every 3s only while the panel is open', async ($, on) => {
  const world = fresh()
  const clock = await boot($, on, world)
  await clock.advance(9000)
  expect(world.runs).toHaveLength(0)
  await $.command.run({ command: 'crew', args: '' } as never)
  await clock.advance(9000)
  expect(world.runs).toHaveLength(4)
})

test('a second session.start (/clear, resume) keeps one poll timer, not two', async ($, on) => {
  const world = fresh()
  const clock = await boot($, on, world)
  await $.session.start({ source: 'clear', cwd: '/', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'crew', args: '' } as never)
  await clock.advance(9000)
  expect(world.runs).toHaveLength(4)
})

test('a second session.start refills the crew even when fleet prints the same thing', async ($, on) => {
  const world = fresh()
  let writes = 0
  on('state.set', (_$, e, next) => {
    writes += 1
    return next(e)
  })
  const clock = await boot($, on, world)
  await $.command.run({ command: 'crew', args: '' } as never)
  const opened = writes
  await $.session.start({ source: 'clear', cwd: '/', surface: 'terminal', isInteractive: true } as never)
  await clock.advance(3000)
  expect(writes).toBe(opened + 1)
})

test('/crew during an in-flight clock poll still loads the crew before opening', async ($, on) => {
  const world = fresh()
  const clock = await boot($, on, world)
  world.slowPanes = true
  await clock.advance(3000)
  const ran = $.command.run({ command: 'crew', args: '' } as never)
  await clock.advance(500)
  await ran
  expect(world.runs).toHaveLength(1)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: '1 needs you · 1 busy', in: 'stage' })).toBeDefined()
  await ui.unmount()
})

for (const surface of ['terminal', 'desktop'] as const) {
  test(`${surface}: each agent is a character with its quip and step bar`, async ($, on) => {
    const world = fresh()
    await boot($, on, world)
    await $.command.run({ command: 'crew', args: '' } as never)
    const ui = await $.ui.mount({ ...PANE, surface })
    const scope = { in: 'stage' }
    expect(await ui.find({ type: 'Text', text: '1 needs you · 1 busy', ...scope })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /bike-endless/, ...scope })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /███░░ 3\/5 track gen|3\/5 track gen/, ...scope })).toBeDefined()
    // No steps: the brief stands in for the bar.
    expect(await ui.find({ type: 'Text', text: 'Serve over https', ...scope })).toBeDefined()
    // The waiting crab holds up its ? bubble.
    expect(await ui.find({ type: 'Text', text: /\?/, ...scope })).toBeDefined()
    await ui.unmount()
  })

  test(`${surface}: the crew animates, and holds still under reduced motion`, async ($, on) => {
    const world = fresh()
    await boot($, on, world)
    await $.command.run({ command: 'crew', args: '' } as never)
    const ui = await $.ui.mount({ ...PANE, surface })
    const frame = async () => JSON.stringify(await ui.drawn({ in: 'stage' }))
    const first = await frame()
    await ui.advance(400)
    expect(await frame()).not.toBe(first)

    await ui.setMotionReduced(true)
    const still = await frame()
    await ui.advance(4000)
    expect(await frame()).toBe(still)
    await ui.unmount()
  })
}

test('unchanged fleet output writes nothing; changed output redraws', async ($, on) => {
  const world = fresh()
  let writes = 0
  on('state.set', (_$, e, next) => {
    writes += 1
    return next(e)
  })
  const clock = await boot($, on, world)
  await $.command.run({ command: 'crew', args: '' } as never)
  const opened = writes
  await clock.advance(6000)
  expect(writes).toBe(opened)
  world.out = { ...world.out, stdout: JSON.stringify([{ ...ROWS[0], state: 'idle', steps: { done: 5, total: 5 } }]) }
  await clock.advance(3000)
  expect(writes).toBe(opened + 1)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: '1 done', in: 'stage' })).toBeDefined()
  await ui.unmount()
})

test('a fleet failure shows as a line, not a crash', async ($, on) => {
  const world = fresh()
  world.out = { stdout: '', exitCode: 1, stderr: 'fleet: error: tmux not running\n' }
  await boot($, on, world)
  await $.command.run({ command: 'crew', args: '' } as never)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /can't reach fleet: fleet: error: tmux not running/, in: 'stage' })).toBeDefined()
  await ui.unmount()
})

test('include=all brings unmanaged sessions aboard', { options: { include: 'all' } }, async ($, on) => {
  const world = fresh()
  world.out.stdout = JSON.stringify([...ROWS, { ...ROWS[0], name: 'tarn', managed: false, cwd: '/home/danny/projects/tarn' }])
  await boot($, on, world)
  await $.command.run({ command: 'crew', args: '' } as never)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /^tarn/, in: 'stage' })).toBeDefined()
  await ui.unmount()
})

for (const surface of ['vscode', 'mobile'] as const) {
  test(`${surface}: no Client there, so a still frame`, async ($, on) => {
    const world = fresh()
    await boot($, on, world)
    await $.command.run({ command: 'crew', args: '' } as never)
    const ui = await $.ui.mount({ ...PANE, surface })
    expect(await ui.find({ type: 'Text', text: /bike-endless/ })).toBeDefined()
    await ui.unmount()
  })
}
