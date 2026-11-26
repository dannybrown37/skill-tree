import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import { fleetArgv, parseFleet } from './crew'
import type { Include } from './crew'
import { crewTree } from './draw'

const PANE = 'fleet-crew'
const TITLE = 'Fleet crew'
const POLL_MS = 3000
const crew = atom({ plugin: 'fleet-crew', key: 'crew' } as const, { members: [], error: '' }, { shape: 'crew-1' })

type Config = { include: Include; fleetCommand: string }

// Module scope is fine: a reload starts it over and the next poll refills it.
let lastOut = ''
let inFlight: Promise<void> | null = null
let timer: Timer | null = null

// A forced poll (opening the pane) waits for one in flight rather than being
// dropped: that one may have skipped fleet because the pane was still closed.
async function poll($: EngineInterface, config: Config, force: boolean): Promise<void> {
  if (inFlight) {
    if (!force) return
    await inFlight.catch(() => undefined)
    return poll($, config, true)
  }
  inFlight = pollOnce($, config, force)
  try {
    await inFlight
  } finally {
    inFlight = null
  }
}

// Runs fleet only while the pane is open, and writes state only when its
// output changed, so an idle crew redraws nothing.
async function pollOnce($: EngineInterface, config: Config, force: boolean): Promise<void> {
  if (!force && !(await $.ui.panes()).some(p => p.id === PANE)) return
  const argv = fleetArgv(config.fleetCommand, {
    home: (await $.env.get('HOME')) ?? '',
    dotfiles: (await $.env.get('DOTFILES_DIR')) ?? '',
  })
  const ran = await $.process.run(argv, { timeoutMs: 10_000 }).catch((err: unknown) => ({
    exitCode: 127,
    stdout: '',
    stderr: err instanceof Error ? err.message : String(err),
  }))
  const out = ran.exitCode === 0 ? ran.stdout : `\0${ran.stderr}`
  if (out === lastOut) return
  lastOut = out
  const next =
    ran.exitCode === 0
      ? parseFleet(ran.stdout, config.include)
      : { members: [], error: (ran.stderr.trim().split('\n')[0] ?? '').slice(0, 120) || `exit ${ran.exitCode}` }
  await update($, crew, () => next)
}

async function togglePane($: EngineInterface, config: Config): Promise<boolean> {
  if ((await $.ui.panes()).some(p => p.id === PANE)) {
    await $.ui.close({ id: PANE })
    return false
  }
  await poll($, config, true)
  await $.ui.open({ id: PANE, title: TITLE })
  return true
}

export const register: Register = (on, options) => {
  const config: Config = {
    include: options.include === 'all' ? 'all' : 'managed',
    fleetCommand: typeof options.fleetCommand === 'string' ? options.fleetCommand : '',
  }

  on('session.start', async ($, e, next) => {
    const started = await next(e)
    await $.command.register({ name: 'crew', description: 'Show or hide the fleet crew panel: your fleet agents as animated characters' })
    // session.start comes again on /clear and resume in the same module:
    // one timer, and the next poll writes even if fleet's output is unchanged.
    lastOut = ''
    timer?.cancel()
    timer = $.clock.every(POLL_MS, () => void poll($, config, false).catch(() => undefined))
    return started
  })

  on('command.run', { command: 'crew' }, async $ => {
    const isOpen = await togglePane($, config)
    return { text: isOpen ? 'All hands on deck.' : 'Crew dismissed.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const ui = $.ui.resolve(e)
    const value = await read($, crew)
    if ((e.surface === 'terminal' || e.surface === 'desktop') && 'Client' in ui) {
      const { Client } = ui
      return <Client key="stage" module="./stage.tsx" props={value} />
    }
    return crewTree(ui, value, 0, e.props.bodyColumns || 40)
  })
}
