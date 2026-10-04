import {describe, expect, test} from 'vitest';
import {Easing, interpolate, sequenceWindow, spring} from './math';

describe('interpolate', () => {
  test.each([
    {input: 5, inRange: [0, 10], outRange: [0, 100], expected: 50},
    {input: 0, inRange: [0, 10], outRange: [20, 40], expected: 20},
    {input: 10, inRange: [0, 10], outRange: [20, 40], expected: 40},
    {input: 15, inRange: [0, 10, 20], outRange: [0, 100, 0], expected: 50},
    {input: 10, inRange: [0, 10, 20], outRange: [0, 100, 0], expected: 100},
    {input: 5, inRange: [0, 10], outRange: [100, 0], expected: 50},
  ])('maps $input over $inRange to $expected', ({input, inRange, outRange, expected}) => {
    expect(interpolate(input, inRange, outRange)).toBeCloseTo(expected);
  });

  test.each([
    {input: -5, options: {}, expected: -50},
    {input: 15, options: {}, expected: 150},
    {input: -5, options: {extrapolateLeft: 'clamp'} as const, expected: 0},
    {input: 15, options: {extrapolateLeft: 'clamp'} as const, expected: 150},
    {input: 15, options: {extrapolateRight: 'clamp'} as const, expected: 100},
    {input: -5, options: {extrapolateRight: 'clamp'} as const, expected: -50},
  ])('outside the range, $input with $options gives $expected', ({input, options, expected}) => {
    expect(interpolate(input, [0, 10], [0, 100], options)).toBeCloseTo(expected);
  });

  test('applies easing inside a segment', () => {
    expect(interpolate(5, [0, 10], [0, 100], {easing: Easing.in(Easing.cubic)})).toBeCloseTo(12.5);
  });

  test.each([
    {name: 'length mismatch', inRange: [0, 10], outRange: [0, 1, 2]},
    {name: 'single point', inRange: [0], outRange: [0]},
    {name: 'non-increasing input', inRange: [0, 10, 10], outRange: [0, 1, 2]},
    {name: 'decreasing input', inRange: [10, 0], outRange: [0, 1]},
  ])('rejects $name', ({inRange, outRange}) => {
    expect(() => interpolate(1, inRange, outRange)).toThrow();
  });
});

describe('Easing', () => {
  test.each([
    {name: 'linear', fn: Easing.linear, mid: 0.5},
    {name: 'quad', fn: Easing.quad, mid: 0.25},
    {name: 'cubic', fn: Easing.cubic, mid: 0.125},
    {name: 'in(cubic)', fn: Easing.in(Easing.cubic), mid: 0.125},
    {name: 'out(cubic)', fn: Easing.out(Easing.cubic), mid: 0.875},
    {name: 'inOut(cubic)', fn: Easing.inOut(Easing.cubic), mid: 0.5},
    {name: 'inOut(quad)', fn: Easing.inOut(Easing.quad), mid: 0.5},
  ])('$name runs 0 to 1 through $mid', ({fn, mid}) => {
    expect(fn(0)).toBeCloseTo(0);
    expect(fn(0.5)).toBeCloseTo(mid);
    expect(fn(1)).toBeCloseTo(1);
  });

  test('inOut(cubic) is slow at the ends', () => {
    expect(Easing.inOut(Easing.cubic)(0.25)).toBeCloseTo(0.0625);
    expect(Easing.inOut(Easing.cubic)(0.75)).toBeCloseTo(0.9375);
  });
});

describe('spring', () => {
  const fps = 30;

  test.each([{frame: -10}, {frame: 0}])('is 0 at frame $frame', ({frame}) => {
    expect(spring({frame, fps})).toBe(0);
  });

  test.each([
    {name: 'default', config: {}},
    {name: 'bouncy', config: {damping: 12, mass: 0.6}},
    {name: 'critically damped', config: {damping: 20}},
    {name: 'overdamped', config: {damping: 200}},
  ])('$name settles at 1', ({config}) => {
    expect(spring({frame: 3000, fps, config})).toBeCloseTo(1, 2);
  });

  test('underdamped overshoots', () => {
    const values = Array.from({length: 60}, (_, frame) => spring({frame, fps, config: {damping: 12, mass: 0.6}}));
    expect(Math.max(...values)).toBeGreaterThan(1.01);
  });

  test('overdamped rises without overshoot', () => {
    const values = Array.from({length: 400}, (_, frame) => spring({frame, fps, config: {damping: 200}}));
    values.slice(1).forEach((value, i) => {
      expect(value).toBeGreaterThanOrEqual(values[i]);
      expect(value).toBeLessThanOrEqual(1);
    });
  });

  test.each([{durationInFrames: 18}, {durationInFrames: 22}, {durationInFrames: 60}])(
    'durationInFrames $durationInFrames stretches the motion to end there',
    ({durationInFrames}) => {
      const at = (frame: number): number => spring({frame, fps, config: {damping: 200}, durationInFrames});
      expect(at(durationInFrames / 2)).toBeLessThan(0.99);
      expect(at(durationInFrames / 2)).toBeGreaterThan(0.5);
      expect(at(durationInFrames)).toBeCloseTo(1, 2);
      expect(at(durationInFrames + 30)).toBeCloseTo(1, 2);
    },
  );
});

describe('sequenceWindow', () => {
  test.each([
    {frame: 9, from: 10, duration: 5, expected: {localFrame: -1, visible: false}},
    {frame: 10, from: 10, duration: 5, expected: {localFrame: 0, visible: true}},
    {frame: 14, from: 10, duration: 5, expected: {localFrame: 4, visible: true}},
    {frame: 15, from: 10, duration: 5, expected: {localFrame: 5, visible: false}},
    {frame: 500, from: 10, duration: undefined, expected: {localFrame: 490, visible: true}},
  ])('frame $frame in [$from, +$duration)', ({frame, from, duration, expected}) => {
    expect(sequenceWindow(frame, from, duration)).toEqual(expected);
  });
});
