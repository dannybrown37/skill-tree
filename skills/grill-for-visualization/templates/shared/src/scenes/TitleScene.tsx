import React from 'react';
import {Appear} from '../components/Appear';
import {colors, copy, timing} from '../content';
import {fontFamily} from '../fonts';
import {AbsoluteFill} from '../runtime';

export const TitleScene: React.FC = () => {
  const t = timing.title;
  return (
    <AbsoluteFill style={{fontFamily, color: colors.text, justifyContent: 'center', padding: '0 160px'}}>
      <Appear
        at={t.kickerIn}
        style={{fontSize: 26, fontWeight: 600, letterSpacing: 5, textTransform: 'uppercase', color: colors.accent}}
      >
        {copy.title.kicker}
      </Appear>
      <Appear at={t.headlineIn} style={{marginTop: 28, fontSize: 112, fontWeight: 800, lineHeight: 1.04}}>
        {copy.title.lines.map((line) => (
          <div key={line}>{line}</div>
        ))}
      </Appear>
      <Appear at={t.bodyIn} style={{marginTop: 36, fontSize: 40, color: colors.textDim, maxWidth: 1100}}>
        {copy.title.body}
      </Appear>
    </AbsoluteFill>
  );
};
