import type { ClientSurface } from 'claude-code'

import { FRAME_MS, crewTree } from './draw'
import type { Crew } from '../types'

type State = { tick: number }

// Frames advance on the surface's own clock, so animation costs no hook
// round-trips; reduced motion or an unfocused window holds the frame.
export default function Stage(props: Crew, surface: ClientSurface<State>) {
  if (surface.state === undefined) {
    let tick = 0
    surface.every(FRAME_MS, () => {
      if (surface.isMotionReduced || !surface.isWindowFocused) return
      tick += 1
      surface.setState({ tick })
    })
    surface.setState({ tick })
  }
  const tick = surface.isMotionReduced ? 0 : (surface.state?.tick ?? 0)
  return crewTree(surface.elements, props, tick, surface.columns || 48)
}
