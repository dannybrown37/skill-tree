import React, {useEffect, useRef, useState} from 'react';
import {flushSync} from 'react-dom';
import {FrameProvider, type VideoConfig} from './frame';

declare global {
  interface Window {
    __composition?: VideoConfig;
    __setFrame?: (frame: number) => Promise<void>;
  }
}

const nextPaint = (): Promise<void> =>
  new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));

const Stage: React.FC<{frame: number; config: VideoConfig; scale: number; children: React.ReactNode}> = ({
  frame,
  config,
  scale,
  children,
}) => (
  <div
    style={{
      position: 'relative',
      width: config.width,
      height: config.height,
      overflow: 'hidden',
      transform: `scale(${scale})`,
      transformOrigin: 'top left',
    }}
  >
    <FrameProvider frame={frame} config={config}>
      {children}
    </FrameProvider>
  </div>
);

// Driven frame by frame from scripts/render.ts: no controls, no scaling.
const RenderSurface: React.FC<{config: VideoConfig; children: React.ReactNode}> = ({config, children}) => {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    window.__composition = config;
    window.__setFrame = async (next: number): Promise<void> => {
      flushSync(() => setFrame(next));
      await document.fonts.ready;
      await nextPaint();
    };
  }, [config]);

  return (
    <Stage frame={frame} config={config} scale={1}>
      {children}
    </Stage>
  );
};

const CONTROLS_HEIGHT = 56;

const Preview: React.FC<{config: VideoConfig; children: React.ReactNode}> = ({config, children}) => {
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [viewport, setViewport] = useState({width: window.innerWidth, height: window.innerHeight});
  const frameRef = useRef(frame);
  frameRef.current = frame;

  useEffect(() => {
    const onResize = (): void => setViewport({width: window.innerWidth, height: window.innerHeight});
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    if (!playing) return;
    const startedAt = performance.now();
    const startFrame = frameRef.current;
    let handle = requestAnimationFrame(function tick(now: number) {
      const elapsed = Math.floor(((now - startedAt) / 1000) * config.fps);
      setFrame((startFrame + elapsed) % config.durationInFrames);
      handle = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(handle);
  }, [playing, config.fps, config.durationInFrames]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.code === 'Space') {
        event.preventDefault();
        setPlaying((value) => !value);
      }
      const step = event.code === 'ArrowRight' ? 1 : event.code === 'ArrowLeft' ? -1 : 0;
      if (step !== 0) {
        setPlaying(false);
        setFrame((value) => Math.min(config.durationInFrames - 1, Math.max(0, value + step)));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [config.durationInFrames]);

  const scale = Math.min(viewport.width / config.width, (viewport.height - CONTROLS_HEIGHT) / config.height);

  return (
    <div style={{height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
      <div style={{width: config.width * scale, height: config.height * scale}}>
        <Stage frame={frame} config={config} scale={scale}>
          {children}
        </Stage>
      </div>
      <div
        style={{
          height: CONTROLS_HEIGHT,
          width: '100%',
          boxSizing: 'border-box',
          padding: '0 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          color: '#c9d1e3',
          font: '13px ui-monospace, monospace',
        }}
      >
        <button type="button" onClick={() => setPlaying((value) => !value)} style={{width: 64}}>
          {playing ? 'Pause' : 'Play'}
        </button>
        <input
          type="range"
          aria-label="Frame"
          min={0}
          max={config.durationInFrames - 1}
          value={frame}
          onChange={(event) => {
            setPlaying(false);
            setFrame(Number(event.target.value));
          }}
          style={{flex: 1}}
        />
        <span style={{width: 190, textAlign: 'right'}}>
          f{frame} / {config.durationInFrames - 1} · {(frame / config.fps).toFixed(2)} s
        </span>
      </div>
    </div>
  );
};

export const Player: React.FC<{config: VideoConfig; children: React.ReactNode}> = ({config, children}) => {
  const renderMode = new URLSearchParams(window.location.search).has('render');
  const Surface = renderMode ? RenderSurface : Preview;
  return <Surface config={config}>{children}</Surface>;
};
