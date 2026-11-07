// Regenerates media/icon.png (the marketplace icon) from the same motif as icon.svg: a bar chart
// with a trend line, on the coral that tells this board apart from the teal STLC and lavender SDLC.
//
// Kept as a script rather than a committed binary with no provenance. Pure Node: zlib is all a
// PNG needs.
//
//   node media/make-icon.mjs
import { deflateSync } from 'node:zlib';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const SIZE = 128;
const SS = 4;
const N = SIZE * SS;

const BG = [0x3b, 0x0d, 0x19];      // deep coral tile
const LINE = [0xff, 0xe4, 0xe6];    // bars
const TREND = [0xfb, 0x71, 0x85];   // accent trend line

const s = (v) => (v / 24) * N;
const buf = Buffer.alloc(N * N * 3);
for (let i = 0; i < N * N; i++) buf.set(BG, i * 3);
const put = (x, y, rgb) => {
  if (x >= 0 && y >= 0 && x < N && y < N) buf.set(rgb, (y * N + x) * 3);
};
function stroke(points, width, rgb) {
  const hw = s(width) / 2;
  for (let k = 0; k < points.length - 1; k++) {
    const [ax, ay] = points[k].map(s), [bx, by] = points[k + 1].map(s);
    const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy || 1;
    for (let py = Math.floor(Math.min(ay, by) - hw); py <= Math.ceil(Math.max(ay, by) + hw); py++) {
      for (let px = Math.floor(Math.min(ax, bx) - hw); px <= Math.ceil(Math.max(ax, bx) + hw); px++) {
        const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
        const qx = ax + t * dx, qy = ay + t * dy;
        if ((px - qx) ** 2 + (py - qy) ** 2 <= hw * hw) put(px, py, rgb);
      }
    }
  }
}
stroke([[4, 20], [20, 20]], 1.6, LINE);
for (const [x, top] of [[6, 15], [10, 11], [14, 14], [18, 8]]) stroke([[x, 20], [x, top]], 2.2, LINE);
stroke([[4, 9], [9, 5], [13, 8], [20, 3]], 2.0, TREND);

const out = Buffer.alloc(SIZE * SIZE * 3);
for (let y = 0; y < SIZE; y++) {
  for (let x = 0; x < SIZE; x++) {
    const acc = [0, 0, 0];
    for (let sy = 0; sy < SS; sy++) for (let sx = 0; sx < SS; sx++) {
      const o = ((y * SS + sy) * N + (x * SS + sx)) * 3;
      acc[0] += buf[o]; acc[1] += buf[o + 1]; acc[2] += buf[o + 2];
    }
    const o = (y * SIZE + x) * 3, n = SS * SS;
    out[o] = Math.round(acc[0] / n); out[o + 1] = Math.round(acc[1] / n); out[o + 2] = Math.round(acc[2] / n);
  }
}
const raw = Buffer.alloc(SIZE * (SIZE * 3 + 1));
for (let y = 0; y < SIZE; y++) out.copy(raw, y * (SIZE * 3 + 1) + 1, y * SIZE * 3, (y + 1) * SIZE * 3);

let TABLE = null;
function crc32(b) {
  if (!TABLE) {
    TABLE = new Int32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      TABLE[n] = c;
    }
  }
  let c = -1;
  for (const byte of b) c = TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
  return c ^ -1;
}
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body) >>> 0);
  return Buffer.concat([len, body, crc]);
}
const ihdr = Buffer.alloc(13);
ihdr.writeUInt32BE(SIZE, 0);
ihdr.writeUInt32BE(SIZE, 4);
ihdr[8] = 8;
ihdr[9] = 2;
const png = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  chunk('IHDR', ihdr),
  chunk('IDAT', deflateSync(raw, { level: 9 })),
  chunk('IEND', Buffer.alloc(0)),
]);
const target = join(dirname(fileURLToPath(import.meta.url)), 'icon.png');
writeFileSync(target, png);
console.log(`wrote ${target} (${png.length} bytes)`);
