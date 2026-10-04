import React from 'react';
import {Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from '../runtime';

export const useAppear = (at: number, out?: number): {opacity: number; shift: number} => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame: frame - at, fps, config: {damping: 200}, durationInFrames: 22});
  const exit =
    out === undefined
      ? 0
      : interpolate(frame, [out, out + 10], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.in(Easing.cubic),
        });
  return {opacity: enter * (1 - exit), shift: (1 - enter) * 28 - exit * 14};
};

export const Appear: React.FC<{
  at: number;
  out?: number;
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({at, out, style, children}) => {
  const {opacity, shift} = useAppear(at, out);
  return <div style={{...style, opacity, transform: `translateY(${shift}px)`}}>{children}</div>;
};
