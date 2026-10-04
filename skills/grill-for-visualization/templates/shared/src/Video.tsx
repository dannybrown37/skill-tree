import React from 'react';
import {SCENE_ORDER, type SceneKey, colors, timing} from './content';
import {AbsoluteFill, Sequence, interpolate, useCurrentFrame} from './runtime';
import {TitleScene} from './scenes/TitleScene';

const sceneComponents: Record<SceneKey, React.FC> = {
  title: TitleScene,
};

const FadeIn: React.FC<{children: React.ReactNode}> = ({children}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, timing.crossfade], [0, 1], {extrapolateRight: 'clamp'});
  return <AbsoluteFill style={{opacity}}>{children}</AbsoluteFill>;
};

export const Video: React.FC = () => {
  let from = 0;
  return (
    <AbsoluteFill style={{background: colors.bg}}>
      {SCENE_ORDER.map((key) => {
        const Scene = sceneComponents[key];
        const {duration} = timing[key];
        const start = from;
        from += duration - timing.crossfade;
        return (
          <Sequence key={key} from={start} durationInFrames={duration}>
            <FadeIn>
              <Scene />
            </FadeIn>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
