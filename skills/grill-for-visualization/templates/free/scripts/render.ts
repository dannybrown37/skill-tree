import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdir} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {chromium, type Page} from 'playwright';
import {createServer} from 'vite';

const USAGE = `Usage:
  node scripts/render.ts <out.mp4>                 Render the whole video
  node scripts/render.ts --still <frame> [out.png]  Render one frame (default out/stills/f<frame>.png)

Options:
  --crf <n>    x264 quality, lower is better (default 16)
  -h, --help   This screen`;

type Composition = {fps: number; width: number; height: number; durationInFrames: number};

const fail = (message: string): never => {
  console.error(`${message}\n\n${USAGE}`);
  process.exit(2);
};

const parseFrame = (raw: string, composition: Composition): number => {
  const frame = Number(raw);
  if (!Number.isInteger(frame) || frame < 0 || frame >= composition.durationInFrames) {
    fail(`--still needs a frame between 0 and ${composition.durationInFrames - 1}, got "${raw}"`);
  }
  return frame;
};

const setFrame = (page: Page, frame: number): Promise<void> =>
  page.evaluate((value) => window.__setFrame?.(value), frame);

const renderVideo = async (page: Page, composition: Composition, outPath: string, crf: string): Promise<void> => {
  const ffmpeg = spawn(
    'ffmpeg',
    [
      '-y',
      '-loglevel', 'error',
      '-f', 'image2pipe',
      '-framerate', String(composition.fps),
      '-c:v', 'png',
      '-i', '-',
      '-c:v', 'libx264',
      '-pix_fmt', 'yuv420p',
      '-crf', crf,
      '-movflags', '+faststart',
      outPath,
    ],
    {stdio: ['pipe', 'inherit', 'inherit']},
  );
  ffmpeg.on('error', (error) => {
    console.error(`Could not start ffmpeg (${error.message}). Install it and make sure it is on PATH.`);
    process.exit(1);
  });
  const exited = once(ffmpeg, 'close');

  for (let frame = 0; frame < composition.durationInFrames; frame++) {
    await setFrame(page, frame);
    const png = await page.screenshot({type: 'png'});
    if (!ffmpeg.stdin.write(png)) await once(ffmpeg.stdin, 'drain');
    if (process.stdout.isTTY) {
      process.stdout.write(`\rframe ${frame + 1}/${composition.durationInFrames}`);
    }
  }
  ffmpeg.stdin.end();
  const [code] = await exited;
  if (process.stdout.isTTY) process.stdout.write('\n');
  if (code !== 0) throw new Error(`ffmpeg exited with code ${code}`);
};

const main = async (): Promise<void> => {
  const {values, positionals} = parseArgs({
    allowPositionals: true,
    options: {
      still: {type: 'string'},
      crf: {type: 'string', default: '16'},
      help: {type: 'boolean', short: 'h'},
    },
  });
  if (values.help || (values.still === undefined && positionals.length === 0)) {
    console.log(USAGE);
    return;
  }

  const server = await createServer({server: {port: 0, host: '127.0.0.1'}, logLevel: 'error'});
  await server.listen();
  const address = server.httpServer?.address();
  if (address === null || address === undefined || typeof address === 'string') {
    throw new Error('Vite did not report a port');
  }

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({deviceScaleFactor: 1});
    page.on('pageerror', (error) => {
      throw error;
    });
    await page.goto(`http://127.0.0.1:${address.port}/?render`);
    await page.waitForFunction(() => window.__composition !== undefined && window.__setFrame !== undefined);
    const composition = (await page.evaluate(() => window.__composition)) as Composition;
    await page.setViewportSize({width: composition.width, height: composition.height});

    if (values.still !== undefined) {
      const frame = parseFrame(values.still, composition);
      const outPath = resolve(positionals[0] ?? `out/stills/f${frame}.png`);
      await mkdir(dirname(outPath), {recursive: true});
      await setFrame(page, frame);
      await page.screenshot({type: 'png', path: outPath});
      console.log(outPath);
      return;
    }

    const outPath = resolve(positionals[0]);
    await mkdir(dirname(outPath), {recursive: true});
    await renderVideo(page, composition, outPath, values.crf);
    console.log(outPath);
  } finally {
    await browser.close();
    await server.close();
  }
};

await main();
