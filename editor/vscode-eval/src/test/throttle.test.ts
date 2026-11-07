/** The background rebuild's throttle (throttle.ts), the same test as vscode-sdlc's. */
import * as assert from 'node:assert/strict';
import { test } from 'node:test';
import { Throttle, Timers } from '../throttle';

function fakeTimers(): Timers & { advance(ms: number): void } {
  let now = 1_000_000;
  let seq = 0;
  const queue = new Map<number, { at: number; fn: () => void }>();
  return {
    now: () => now,
    setTimeout(fn, ms) {
      const id = ++seq;
      queue.set(id, { at: now + ms, fn });
      return id;
    },
    clearTimeout(h) {
      queue.delete(h as number);
    },
    advance(ms) {
      const until = now + ms;
      for (;;) {
        const due = [...queue.entries()].filter(([, t]) => t.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        queue.delete(due[0]);
        now = due[1].at;
        due[1].fn();
      }
      now = until;
    },
  };
}

test('the background rebuild runs at most once per interval, with one trailing run', async () => {
  const t = fakeTimers();
  let runs = 0;
  const th = new Throttle(async () => {
    runs++;
  }, 60_000, t);
  th.request();
  await Promise.resolve();
  assert.equal(runs, 1);
  th.request();
  th.request();
  th.request();
  await Promise.resolve();
  assert.equal(runs, 1, 'ran again inside the interval');
  t.advance(60_000);
  await new Promise((r) => setImmediate(r));
  assert.equal(runs, 2, 'the trailing request did not run');
  t.advance(600_000);
  await new Promise((r) => setImmediate(r));
  assert.equal(runs, 2, 'ran with nothing requested');
});
