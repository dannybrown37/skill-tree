export type Mood = 'busy' | 'tapping' | 'napping' | 'celebrating' | 'dizzy' | 'gone' | 'booting'

export type Steps = { done: number; total: number; note: string }

export type Member = {
  name: string
  repo: string
  character: string
  state: string
  mood: Mood
  brief: string
  steps: Steps | null
}

export type Crew = {
  members: Member[]
  error: string
}

declare module 'claude-code' {
  interface PluginState {
    'fleet-crew': { crew: Shaped<Crew> }
  }
}
