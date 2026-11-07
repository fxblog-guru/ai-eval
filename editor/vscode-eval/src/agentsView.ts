/**
 * Feeds the Agents tab of a board webview. The tab itself (`media/agents.js`) lives inside the
 * board page; this side reads the transcripts and posts `{command: 'agents', ...}` to every board
 * that is attached.
 *
 * Shared verbatim by the sdlc, stlc and ai-eval addons. The host passes only which project is on
 * show and, optionally, titles for the work-item ids it knows.
 *
 * Transcripts live outside the workspace, so there is no file watcher to lean on. While a board
 * shows the tab, it is re-read every few seconds; otherwise only now and then, to keep the tab's
 * "working" count honest. `AgentsReader` keeps parsed files between reads, so a tick costs a
 * directory listing and some stats.
 */

import * as vscode from 'vscode';
import { AgentsReader, AgentsSnapshot } from './agents';

export interface AgentsSource {
  /** The project folder on show, or undefined when there is none. */
  projectRoot(): string | undefined;
  /** Titles for work-item ids, e.g. TASK-041 → "Post list API". */
  itemTitles?(): Record<string, string>;
}

const FAST_MS = 4000;
const SLOW_MS = 30_000;

export class AgentsFeed implements vscode.Disposable {
  private readonly reader = new AgentsReader();
  private readonly boards = new Map<vscode.Webview, { watching: boolean }>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private last: AgentsSnapshot | undefined;

  constructor(private readonly source: AgentsSource) {}

  /** Wire a board webview: it may ask to watch, and to open a transcript. */
  attach(webview: vscode.Webview): vscode.Disposable {
    this.boards.set(webview, { watching: false });
    const sub = webview.onDidReceiveMessage((msg: { command?: string; on?: boolean; path?: string }) => {
      const entry = this.boards.get(webview);
      if (!entry) return;
      if (msg?.command === 'ready') this.post(webview, this.last ?? this.read());
      if (msg?.command === 'agents:watch') {
        entry.watching = !!msg.on;
        if (entry.watching) this.post(webview, this.read());
        this.schedule();
      }
      if (msg?.command === 'agents:transcript' && typeof msg.path === 'string' && /\.jsonl$/.test(msg.path) && this.isTranscript(msg.path)) {
        void vscode.commands.executeCommand('vscode.open', vscode.Uri.file(msg.path));
      }
    });
    this.schedule();
    return new vscode.Disposable(() => {
      sub.dispose();
      this.boards.delete(webview);
      this.schedule();
    });
  }

  /** Re-read now, e.g. after the selected project changed. */
  refresh(): void {
    this.broadcast();
  }

  dispose(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
    this.boards.clear();
  }

  /** Only a file the last snapshot listed may be opened from the page. */
  private isTranscript(p: string): boolean {
    const s = this.last;
    if (!s) return false;
    return s.sessions.some((x) => x.file === p || x.agents.some((a) => a.file === p));
  }

  private read(): AgentsSnapshot {
    const root = this.source.projectRoot();
    const empty = (reason: string): AgentsSnapshot => ({ ok: false, reason, sessions: [], counts: { running: 0, quiet: 0, done: 0, stopped: 0 }, scannedAt: Date.now() });
    if (!root) return (this.last = empty('No project selected.'));
    try {
      return (this.last = this.reader.snapshot({ projectRoot: root }));
    } catch (e) {
      return (this.last = empty(`Could not read Claude Code transcripts: ${(e as Error).message}`));
    }
  }

  private post(webview: vscode.Webview, snapshot: AgentsSnapshot): void {
    void webview.postMessage({ command: 'agents', snapshot, titles: this.source.itemTitles?.() ?? {} });
  }

  private broadcast(): void {
    if (!this.boards.size) return;
    const snapshot = this.read();
    for (const w of this.boards.keys()) this.post(w, snapshot);
  }

  private schedule(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
    if (!this.boards.size) return;
    const fast = [...this.boards.values()].some((b) => b.watching);
    this.timer = setTimeout(() => {
      this.broadcast();
      this.schedule();
    }, fast ? FAST_MS : SLOW_MS);
  }
}
