/**
 * The throttle behind the optional background rebuild: the same Timers and Throttle as
 * vscode-sdlc's live.ts (and vscode-stlc's), kept here because this board has no live layer.
 */

export interface Timers {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
  now(): number;
}

export const realTimers: Timers = {
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
  now: () => Date.now(),
};

/**
 * Runs a task at most once per `intervalMs`, with one trailing run for requests that arrived inside
 * the window, and never two at once. Used for the optional background `build_state.py` (as in vscode-sdlc).
 */
export class Throttle {
  private lastStart = -Infinity;
  private running = false;
  private queued = false;
  private handle: unknown;

  constructor(
    private readonly task: () => Promise<void>,
    private readonly intervalMs: number,
    private readonly timers: Timers = realTimers,
  ) {}

  request(): void {
    if (this.running || this.handle !== undefined) {
      this.queued = true;
      return;
    }
    const wait = this.lastStart + this.intervalMs - this.timers.now();
    if (wait > 0) {
      this.handle = this.timers.setTimeout(() => {
        this.handle = undefined;
        void this.start();
      }, wait);
      return;
    }
    void this.start();
  }

  private async start(): Promise<void> {
    this.running = true;
    this.queued = false;
    this.lastStart = this.timers.now();
    try {
      await this.task();
    } catch {
      // A failed rebuild leaves the old index in place; the board keeps showing the live overlay.
    } finally {
      this.running = false;
      if (this.queued) {
        this.queued = false;
        this.request();
      }
    }
  }

  dispose(): void {
    if (this.handle !== undefined) this.timers.clearTimeout(this.handle);
    this.handle = undefined;
    this.queued = false;
  }
}
