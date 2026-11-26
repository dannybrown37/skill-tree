import type { ClientElements } from 'claude-code'

import { SPRITE_W, colorFor, frameFor, quipFor, stepBar, summary } from './crew'
import type { Crew, Member } from '../types'

export const FRAME_MS = 400
// Quips turn over every ~20 s, not every frame: readable, not jittery.
const QUIP_TICKS = 50
const WAITING = '#e5c07b'

type Els = Pick<ClientElements, 'Box' | 'Text'>

const STATE_GLYPH: Record<string, string> = {
  busy: '⚙ working',
  tapping: '? needs you',
  napping: '· idle',
  celebrating: '✓ done',
  dizzy: '✗ error',
  gone: '– gone',
  booting: '… starting',
}

const row = ({ Box, Text }: Els, m: Member, i: number, tick: number, cols: number) => {
  const sprite = frameFor(m.character, m.mood, tick)
  const color = colorFor(m.character)
  const needsYou = m.mood === 'tapping'
  const isFaded = m.mood === 'gone'
  const quip = quipFor(m.character, m.mood, m.name, Math.floor(tick / QUIP_TICKS))
  const barW = Math.max(4, Math.min(16, cols - SPRITE_W - 24))
  return (
    // include=all can list two sessions under one name.
    <Box key={`${i}:${m.name}`} flexDirection="row" gap={1} marginBottom={1}>
      <Box flexDirection="column" width={SPRITE_W} flexShrink={0}>
        {sprite.map((line, y) => (
          <Text key={String(y)} color={needsYou ? WAITING : color} dimColor={isFaded}>
            {line}
          </Text>
        ))}
      </Box>
      <Box flexDirection="column" flexGrow={1}>
        <Text wrap="truncate-end">
          <Text bold color={needsYou ? WAITING : undefined} dimColor={isFaded}>
            {m.name}
          </Text>
          <Text dimColor> {STATE_GLYPH[m.mood] ?? m.state}</Text>
        </Text>
        <Text wrap="truncate-end" dimColor>
          {m.repo ? `${m.repo} · ` : ''}
          <Text italic>{quip}</Text>
        </Text>
        {m.steps ? (
          <Text wrap="truncate-end">
            <Text color={color}>{stepBar(m.steps, barW)}</Text>
            <Text dimColor>
              {' '}
              {m.steps.done}/{m.steps.total}
              {m.steps.note ? ` ${m.steps.note}` : ''}
            </Text>
          </Text>
        ) : (
          <Text wrap="truncate-end" dimColor>
            {m.brief || ' '}
          </Text>
        )}
      </Box>
    </Box>
  )
}

export const crewTree = (els: Els, crew: Crew, tick: number, cols: number) => {
  const { Box, Text } = els
  return (
    <Box flexDirection="column">
      <Text bold wrap="truncate-end">
        {summary(crew.members)}
      </Text>
      {crew.error ? (
        <Text color="red" wrap="truncate-end">
          can't reach fleet: {crew.error}
        </Text>
      ) : null}
      <Box flexDirection="column" marginTop={1}>
        {crew.members.length === 0 && !crew.error ? (
          <Text dimColor>Launch one: fleet new NAME -p "task"</Text>
        ) : null}
        {crew.members.map((m, i) => row(els, m, i, tick, cols))}
      </Box>
    </Box>
  )
}
