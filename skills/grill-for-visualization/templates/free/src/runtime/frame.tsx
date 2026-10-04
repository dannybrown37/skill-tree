import React, {createContext, useContext} from 'react';
import {sequenceWindow} from './math';

export type VideoConfig = {
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
};

const FrameContext = createContext<number>(0);
const ConfigContext = createContext<VideoConfig | null>(null);

export const useCurrentFrame = (): number => useContext(FrameContext);

export const useVideoConfig = (): VideoConfig => {
  const config = useContext(ConfigContext);
  if (config === null) throw new Error('useVideoConfig must be used inside <FrameProvider>');
  return config;
};

export const FrameProvider: React.FC<{frame: number; config: VideoConfig; children: React.ReactNode}> = ({
  frame,
  config,
  children,
}) => (
  <ConfigContext.Provider value={config}>
    <FrameContext.Provider value={frame}>{children}</FrameContext.Provider>
  </ConfigContext.Provider>
);

const fill: React.CSSProperties = {
  position: 'absolute',
  inset: 0,
  display: 'flex',
  flexDirection: 'column',
};

export const AbsoluteFill: React.FC<{style?: React.CSSProperties; children?: React.ReactNode}> = ({
  style,
  children,
}) => <div style={{...fill, ...style}}>{children}</div>;

export const Sequence: React.FC<{from?: number; durationInFrames?: number; children: React.ReactNode}> = ({
  from = 0,
  durationInFrames,
  children,
}) => {
  const {localFrame, visible} = sequenceWindow(useCurrentFrame(), from, durationInFrames);
  if (!visible) return null;
  return (
    <FrameContext.Provider value={localFrame}>
      <AbsoluteFill>{children}</AbsoluteFill>
    </FrameContext.Provider>
  );
};
