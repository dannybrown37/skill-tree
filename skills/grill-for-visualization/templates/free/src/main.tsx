import React from 'react';
import {createRoot} from 'react-dom/client';
import {FPS, HEIGHT, TOTAL_FRAMES, WIDTH} from './content';
import {Player} from './runtime';
import {Video} from './Video';

const config = {fps: FPS, width: WIDTH, height: HEIGHT, durationInFrames: TOTAL_FRAMES};

createRoot(document.getElementById('root') as HTMLElement).render(
  <Player config={config}>
    <Video />
  </Player>,
);
