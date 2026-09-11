// Original procedural motion artwork, rendered locally. No stock footage or external media.
import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const directory = path.resolve('public/media');
await mkdir(directory, { recursive: true });
const poster = `<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900"><defs><linearGradient id="bg"><stop stop-color="#11160e"/><stop offset="1" stop-color="#30362b"/></linearGradient><linearGradient id="metal"><stop stop-color="#505b44"/><stop offset=".4" stop-color="#2b3324"/><stop offset="1" stop-color="#161d12"/></linearGradient></defs><path fill="url(#bg)" d="M0 0h1600v900H0z"/>${Array.from({ length: 19 }, (_, i) => `<path d="M${640 + i * 46} ${-130 + i * 17}l33-14 125 810-33 14z" fill="url(#metal)" stroke="#879071" stroke-opacity=".23"/>`).join('')}</svg>`;
await writeFile(path.join(directory, 'vault-poster.svg'), poster);
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage();
  await page.setContent('<canvas width="1600" height="900"></canvas>');
  const encoded = await page.evaluate(async () => {
    const canvas = document.querySelector('canvas');
    const ctx = canvas.getContext('2d');
    function frame(t) {
      const phase = t * Math.PI * 2;
      const bg = ctx.createLinearGradient(0, 0, 1600, 900);
      bg.addColorStop(0, '#10170d');
      bg.addColorStop(1, '#30362b');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, 1600, 900);
      for (let i = 0; i < 22; i++) {
        const x = 615 + i * 47 + Math.sin(phase) * 13;
        const y = -220 + i * 19 + Math.sin(phase + i * 0.16) * 15;
        const width = 26 + Math.sin(phase + i * 0.11) * 4;
        const light = Math.round(63 + Math.sin(phase + i * 0.19) * 12);
        const gradient = ctx.createLinearGradient(x, 0, x + width + 17, 0);
        gradient.addColorStop(0, `rgb(${light + 12},${light + 17},${light})`);
        gradient.addColorStop(0.16, '#46503b');
        gradient.addColorStop(0.5, '#303829');
        gradient.addColorStop(1, '#182012');
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + width, y - 17);
        ctx.lineTo(x + width + 145, y + 1040);
        ctx.lineTo(x + 145, y + 1057);
        ctx.closePath();
        ctx.fillStyle = gradient;
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + 145, y + 1057);
        ctx.strokeStyle = '#9cab7855';
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x + width, y - 17);
        ctx.lineTo(x + width + 11, y - 13);
        ctx.lineTo(x + width + 156, y + 1044);
        ctx.lineTo(x + width + 145, y + 1040);
        ctx.closePath();
        ctx.fillStyle = '#11180de0';
        ctx.fill();
      }
      const shade = ctx.createLinearGradient(0, 0, 0, 900);
      shade.addColorStop(0, '#00000000');
      shade.addColorStop(0.6, '#0d14082a');
      shade.addColorStop(1, '#0b12087a');
      ctx.fillStyle = shade;
      ctx.fillRect(0, 0, 1600, 900);
    }
    frame(0);
    const stream = canvas.captureStream(24);
    const chunks = [];
    const recorder = new MediaRecorder(stream, {
      mimeType: 'video/webm;codecs=vp9',
      videoBitsPerSecond: 900000,
    });
    const done = new Promise((resolve) => {
      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = async () => {
        const bytes = new Uint8Array(await new Blob(chunks).arrayBuffer());
        let binary = '';
        for (let i = 0; i < bytes.length; i += 32768)
          binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
        resolve(btoa(binary));
      };
    });
    recorder.start();
    const started = performance.now();
    await new Promise((resolve) => {
      function tick(now) {
        const elapsed = now - started;
        frame((elapsed % 10000) / 10000);
        if (elapsed < 10000) requestAnimationFrame(tick);
        else resolve();
      }
      requestAnimationFrame(tick);
    });
    recorder.stop();
    stream.getTracks().forEach((track) => track.stop());
    return await done;
  });
  const bytes = Buffer.from(encoded, 'base64');
  await writeFile(path.join(directory, 'vault-motion.webm'), bytes);
  console.log(
    `Created original 10-second WebM background: ${(bytes.length / 1024).toFixed(0)} KiB`,
  );
} finally {
  await browser.close();
}
