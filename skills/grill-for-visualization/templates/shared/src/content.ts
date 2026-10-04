// Everything you are likely to edit lives here: copy, colors, timing.
// Facts and numbers shown on screen are computed in src/logic/, not typed here.

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

export const colors = {
  bg: '#070B14',
  panel: '#0E1524',
  text: '#F2F5FA',
  textDim: '#8E9BB5',
  accent: '#6FD3FF',
} as const;

export const copy = {
  title: {
    kicker: 'Kicker',
    lines: ['Headline line one.', 'Line two.'],
    body: 'One supporting sentence.',
  },
} as const;

// Frames. Beats inside a scene are relative to that scene's start.
export const timing = {
  crossfade: 15,
  title: {duration: 90, kickerIn: 8, headlineIn: 16, bodyIn: 34},
} as const;

export const SCENE_ORDER = ['title'] as const;

export type SceneKey = (typeof SCENE_ORDER)[number];

export const TOTAL_FRAMES =
  SCENE_ORDER.reduce((sum, key) => sum + timing[key].duration, 0) - (SCENE_ORDER.length - 1) * timing.crossfade;
