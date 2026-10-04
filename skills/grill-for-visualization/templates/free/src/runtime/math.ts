export type EasingFn = (t: number) => number;

export const Easing = {
  linear: ((t) => t) as EasingFn,
  quad: ((t) => t * t) as EasingFn,
  cubic: ((t) => t * t * t) as EasingFn,
  in: (fn: EasingFn): EasingFn => fn,
  out:
    (fn: EasingFn): EasingFn =>
    (t) =>
      1 - fn(1 - t),
  inOut:
    (fn: EasingFn): EasingFn =>
    (t) =>
      t < 0.5 ? fn(t * 2) / 2 : 1 - fn((1 - t) * 2) / 2,
};

type Extrapolate = 'extend' | 'clamp';

export type InterpolateOptions = {
  extrapolateLeft?: Extrapolate;
  extrapolateRight?: Extrapolate;
  easing?: EasingFn;
};

export const interpolate = (
  input: number,
  inputRange: readonly number[],
  outputRange: readonly number[],
  options: InterpolateOptions = {},
): number => {
  if (inputRange.length !== outputRange.length) {
    throw new Error(`interpolate: ranges differ in length (${inputRange.length} vs ${outputRange.length})`);
  }
  if (inputRange.length < 2) {
    throw new Error('interpolate: ranges need at least 2 points');
  }
  if (inputRange.some((value, i) => i > 0 && value <= inputRange[i - 1])) {
    throw new Error(`interpolate: inputRange must be strictly increasing, got [${inputRange.join(', ')}]`);
  }

  const {extrapolateLeft = 'extend', extrapolateRight = 'extend', easing = Easing.linear} = options;
  const last = inputRange.length - 1;

  if (input < inputRange[0] && extrapolateLeft === 'clamp') return outputRange[0];
  if (input > inputRange[last] && extrapolateRight === 'clamp') return outputRange[last];

  const upper = inputRange.findIndex((value, i) => i > 0 && input <= value);
  const hi = upper === -1 ? last : upper;
  const lo = hi - 1;
  const progress = (input - inputRange[lo]) / (inputRange[hi] - inputRange[lo]);
  const eased = progress < 0 || progress > 1 ? progress : easing(progress);
  return outputRange[lo] + eased * (outputRange[hi] - outputRange[lo]);
};

export type SpringConfig = {damping?: number; mass?: number; stiffness?: number};

type ResolvedSpring = Required<SpringConfig>;

const SETTLE_THRESHOLD = 0.005;
const SETTLE_SEARCH_LIMIT_S = 120;
const SETTLE_SEARCH_STEP_S = 1 / 240;

// Closed-form position of a unit-step damped spring starting at rest.
const springPosition = (seconds: number, {damping, mass, stiffness}: ResolvedSpring): number => {
  const omega = Math.sqrt(stiffness / mass);
  const zeta = damping / (2 * Math.sqrt(stiffness * mass));
  const decay = zeta * omega;

  if (zeta < 1) {
    const damped = omega * Math.sqrt(1 - zeta * zeta);
    return 1 - Math.exp(-decay * seconds) * (Math.cos(damped * seconds) + (decay / damped) * Math.sin(damped * seconds));
  }
  if (zeta === 1) {
    return 1 - Math.exp(-omega * seconds) * (1 + omega * seconds);
  }
  // Two separate exponentials: cosh/sinh overflow long before the product does.
  const spread = omega * Math.sqrt(zeta * zeta - 1);
  const ratio = decay / spread;
  return (
    1 -
    0.5 * ((1 + ratio) * Math.exp((spread - decay) * seconds) + (1 - ratio) * Math.exp(-(spread + decay) * seconds))
  );
};

const settleCache = new Map<string, number>();

const settleSeconds = (config: ResolvedSpring): number => {
  const key = `${config.damping}/${config.mass}/${config.stiffness}`;
  const cached = settleCache.get(key);
  if (cached !== undefined) return cached;

  let lastUnsettled = 0;
  for (let t = 0; t <= SETTLE_SEARCH_LIMIT_S; t += SETTLE_SEARCH_STEP_S) {
    if (Math.abs(1 - springPosition(t, config)) >= SETTLE_THRESHOLD) lastUnsettled = t;
    else if (t - lastUnsettled > 2) break;
  }
  const settled = lastUnsettled + SETTLE_SEARCH_STEP_S;
  settleCache.set(key, settled);
  return settled;
};

export type SpringOptions = {
  frame: number;
  fps: number;
  config?: SpringConfig;
  durationInFrames?: number;
};

export const spring = ({frame, fps, config = {}, durationInFrames}: SpringOptions): number => {
  if (frame <= 0) return 0;
  const resolved: ResolvedSpring = {damping: 10, mass: 1, stiffness: 100, ...config};
  if (durationInFrames === undefined) return springPosition(frame / fps, resolved);
  if (frame >= durationInFrames) return 1;
  return springPosition((frame / durationInFrames) * settleSeconds(resolved), resolved);
};

export const sequenceWindow = (
  frame: number,
  from: number,
  durationInFrames: number | undefined,
): {localFrame: number; visible: boolean} => {
  const localFrame = frame - from;
  const visible = localFrame >= 0 && (durationInFrames === undefined || localFrame < durationInFrames);
  return {localFrame, visible};
};
