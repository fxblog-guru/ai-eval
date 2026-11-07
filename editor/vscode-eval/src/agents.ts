/**
 * Who is working on this project right now: every Claude Code chat (session) that touched it, and
 * every subagent those chats spawned, with what each was asked to do and what it is doing.
 *
 * The pipeline's own files only say what is finished — a lane note or a progress row lands when an
 * agent is done. Claude Code, though, writes a transcript per session and per subagent as it works,
 * under `~/.claude/projects/<encoded cwd>/`:
 *
 *   <session>.jsonl                          the chat you typed into
 *   <session>/subagents/agent-<id>.jsonl     one per spawned agent, appended as it works
 *   <session>/subagents/agent-<id>.meta.json {description, agentType, finished?, worktreePath?, ...}
 *
 * Those transcripts are Claude Code's internal format, not a contract. So this module reads
 * defensively — a line it cannot parse is skipped, a file it cannot read is skipped — and depends on
 * nothing in VS Code, so the tests can feed it fixture folders and the stlc and ai-eval addons can
 * carry the same file. It only ever reads; it never writes under `~/.claude`.
 *
 * Cost: a parent folder like agentic-fx holds hundreds of agents. Only files written in the last
 * `sinceHours` are opened, only their first and last few KB are read, and a parsed file is reused
 * until its size or mtime changes.
 */

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

export type AgentStatus = 'running' | 'quiet' | 'done' | 'stopped';

export interface AgentAction {
  tool: string;
  target: string;
  at: number;
}

export interface AgentInfo {
  id: string;
  /** A person's name, unique in its chat, so "Mai is on TASK-041" is something you can say aloud. */
  name: string;
  role: string;
  description: string;
  prompt: string;
  /** Work-item ids found in the description and prompt (TASK-041, TC-012, ...). */
  items: string[];
  status: AgentStatus;
  startedAt: number;
  lastAt: number;
  where: string;
  branch: string;
  actions: AgentAction[];
  /** The agent that spawned this one, when it was not the chat itself. */
  parentId?: string;
  file: string;
}

/**
 * Agents that worked together: spawned by the same chat and running at the same time, or one
 * spawned by the other. A chat that sent out four lanes, then later a reviewer, has two tables.
 */
export interface AgentTable {
  id: string;
  agentIds: string[];
  status: AgentStatus;
  startedAt: number;
  lastAt: number;
  /** Work items more than one agent at the table names — what they share. */
  shared: string[];
}

export interface SessionInfo {
  id: string;
  title: string;
  status: AgentStatus;
  lastAt: number;
  where: string;
  actions: AgentAction[];
  agents: AgentInfo[];
  tables: AgentTable[];
  file: string;
}

export interface AgentsSnapshot {
  ok: boolean;
  reason?: string;
  sessions: SessionInfo[];
  counts: Record<AgentStatus, number>;
  scannedAt: number;
}

export interface ReadOptions {
  /** The project to show. Sessions opened in it, in a parent folder, or in a sibling worktree count. */
  projectRoot: string;
  /** Claude Code's projects folder; defaults to `$CLAUDE_CONFIG_DIR/projects` or `~/.claude/projects`. */
  claudeDir?: string;
  sinceHours?: number;
  /** Work-item ids to pick out of a prompt. */
  itemPattern?: RegExp;
  now?: number;
}

/** Last write within this many ms, not finished: working. Older but not finished: quiet, then stopped. */
export const RUNNING_MS = 3 * 60_000;
export const QUIET_MS = 30 * 60_000;
const HEAD_BYTES = 48 * 1024;
const TAIL_BYTES = 96 * 1024;

export function claudeProjectsDir(env: NodeJS.ProcessEnv = process.env): string {
  const base = env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude');
  return path.join(base, 'projects');
}

/** How Claude Code names a project folder: every character that is not a letter or digit becomes `-`. */
export function encodeProjectDir(abs: string): string {
  return abs.replace(/[^a-zA-Z0-9]/g, '-');
}

const NAMES = [
  'An', 'Bao', 'Chi', 'Dung', 'Giang', 'Ha', 'Hai', 'Hoa', 'Huy', 'Khanh', 'Lan', 'Linh', 'Long', 'Mai', 'Minh', 'My',
  'Nam', 'Ngoc', 'Nhi', 'Phuc', 'Phong', 'Quan', 'Quynh', 'Son', 'Tam', 'Thao', 'Thu', 'Trang', 'Trung', 'Tuan', 'Van', 'Vy',
  'Anh', 'Binh', 'Cuong', 'Dat', 'Duc', 'Hanh', 'Hieu', 'Hung', 'Kien', 'Khoa', 'Loan', 'Luan', 'Nga', 'Nhung', 'Oanh', 'Phat',
  'Quang', 'Sang', 'Thanh', 'Thinh', 'Toan', 'Uyen', 'Viet', 'Xuan', 'Yen', 'Hau', 'Tien', 'Lam', 'Kim', 'Diep', 'Truc', 'Sen',
];

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

/** A first name for an agent id. Same id, same name, in every addon and every redraw. */
export function agentName(id: string): string {
  return NAMES[hash(id) % NAMES.length];
}

/**
 * Names unique within one chat: the earliest-started agent keeps its own name, a later one whose
 * name is taken walks to the next free one, and past the list's length a number is added. An agent
 * keeps its name for as long as the chat's earlier agents do — which is all of its life.
 */
export function assignNames(agents: { id: string; startedAt: number; name: string }[]): void {
  const taken = new Set<string>();
  for (const a of [...agents].sort((x, y) => x.startedAt - y.startedAt || (x.id < y.id ? -1 : 1))) {
    const start = hash(a.id) % NAMES.length;
    let name = '';
    for (let k = 0; k < NAMES.length * 4 && !name; k++) {
      const base = NAMES[(start + k) % NAMES.length];
      const n = Math.floor(k / NAMES.length);
      const candidate = n ? `${base} ${n + 1}` : base;
      if (!taken.has(candidate)) name = candidate;
    }
    a.name = name || a.id.slice(0, 6);
    taken.add(a.name);
  }
}

export function statusFor(finished: boolean | undefined, lastAt: number, now: number): AgentStatus {
  if (finished) return 'done';
  const idle = now - lastAt;
  if (idle < RUNNING_MS) return 'running';
  if (idle < QUIET_MS) return 'quiet';
  return 'stopped';
}

const norm = (p: string): string => path.resolve(p).replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();

/** True when `p` is the project, inside it, or one of its sibling worktrees (`<root>-wt-*`). */
export function belongsTo(p: string | undefined, projectRoot: string): boolean {
  if (!p) return false;
  const a = norm(p);
  const r = norm(projectRoot);
  return a === r || a.startsWith(r + '/') || a.startsWith(r + '-wt');
}

/** The project's path as it may be written inside a prompt: `C:\x\y`, `C:/x/y` or `/c/x/y`. */
function pathSpellings(projectRoot: string): string[] {
  const fwd = path.resolve(projectRoot).replace(/\\/g, '/');
  const out = [fwd, fwd.replace(/\//g, '\\')];
  const m = /^([A-Za-z]):\/(.*)$/.exec(fwd);
  if (m) out.push(`/${m[1].toLowerCase()}/${m[2]}`);
  return out.map((s) => s.toLowerCase());
}

/** Folders under the projects dir worth opening: the project's own, its ancestors', its worktrees'. */
export function candidateDirs(claudeDir: string, projectRoot: string): string[] {
  let names: string[];
  try {
    names = fs.readdirSync(claudeDir);
  } catch {
    return [];
  }
  const own = encodeProjectDir(path.resolve(projectRoot)).toLowerCase();
  const ancestors = new Set<string>();
  for (let d = path.resolve(projectRoot); ; ) {
    ancestors.add(encodeProjectDir(d).toLowerCase());
    const up = path.dirname(d);
    if (up === d) break;
    d = up;
  }
  return names.filter((n) => {
    const l = n.toLowerCase();
    return ancestors.has(l) || l.startsWith(own + '-');
  }).map((n) => path.join(claudeDir, n));
}

/** The busiest status among a group: one agent working makes the table working. */
function groupStatus(list: { status: AgentStatus }[]): AgentStatus {
  for (const st of ['running', 'quiet', 'stopped'] as AgentStatus[]) if (list.some((a) => a.status === st)) return st;
  return 'done';
}

/**
 * Seats agents at tables. Two agents share a table when their working spans overlap — from the
 * first line of the transcript to the last — or when one spawned the other. Spans are compared
 * with a little slack, because a chat that fans out ten lanes starts them a few seconds apart.
 */
export function seatAgents(agents: AgentInfo[], slackMs = 30_000): AgentTable[] {
  const parent = new Map<string, string>();
  const find = (x: string): string => {
    while (parent.get(x) !== x) x = parent.get(x)!;
    return x;
  };
  const join = (a: string, b: string): void => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(rb, ra);
  };
  for (const a of agents) parent.set(a.id, a.id);
  for (const a of agents) if (a.parentId && parent.has(a.parentId)) join(a.parentId, a.id);
  const byStart = [...agents].sort((x, y) => x.startedAt - y.startedAt);
  let reach = -Infinity;
  let anchor = '';
  for (const a of byStart) {
    if (anchor && a.startedAt <= reach + slackMs) join(anchor, a.id);
    else anchor = a.id;
    reach = Math.max(reach, a.lastAt);
  }
  const groups = new Map<string, AgentInfo[]>();
  for (const a of agents) {
    const r = find(a.id);
    if (!groups.has(r)) groups.set(r, []);
    groups.get(r)!.push(a);
  }
  const tables = [...groups.values()].map((list) => {
    const seen = new Map<string, number>();
    for (const a of list) for (const i of a.items) seen.set(i, (seen.get(i) ?? 0) + 1);
    return {
      id: list.map((a) => a.id).sort()[0],
      agentIds: list.map((a) => a.id),
      status: groupStatus(list),
      startedAt: Math.min(...list.map((a) => a.startedAt)),
      lastAt: Math.max(...list.map((a) => a.lastAt)),
      shared: [...seen].filter(([, n]) => n > 1).map(([i]) => i).slice(0, 6),
    };
  });
  const order: Record<AgentStatus, number> = { running: 0, quiet: 1, stopped: 2, done: 3 };
  return tables.sort((a, b) => order[a.status] - order[b.status] || b.lastAt - a.lastAt);
}

// ---- reading one transcript ---------------------------------------------------------------------

interface Parsed {
  firstPrompt: string;
  cwd: string;
  branch: string;
  startedAt: number;
  title: string;
  actions: AgentAction[];
  lastCwd: string;
}

function readSlice(file: string, size: number): { head: string; tail: string } {
  const fd = fs.openSync(file, 'r');
  try {
    const hn = Math.min(size, HEAD_BYTES);
    const head = Buffer.alloc(hn);
    fs.readSync(fd, head, 0, hn, 0);
    if (size <= HEAD_BYTES) return { head: head.toString('utf8'), tail: head.toString('utf8') };
    const tn = Math.min(size, TAIL_BYTES);
    const tail = Buffer.alloc(tn);
    fs.readSync(fd, tail, 0, tn, size - tn);
    return { head: head.toString('utf8'), tail: tail.toString('utf8') };
  } finally {
    fs.closeSync(fd);
  }
}

/** Whole JSON lines only: a slice cut mid-line loses that line, never the rest. */
function lines(text: string): any[] {
  const out: any[] = [];
  for (const l of text.split('\n')) {
    if (!l.startsWith('{')) continue;
    try {
      out.push(JSON.parse(l));
    } catch {
      // a line cut by the slice, or one this version does not know
    }
  }
  return out;
}

const textOf = (content: unknown): string => {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.filter((b) => b && b.type === 'text').map((b) => String(b.text ?? '')).join('\n');
  return '';
};

/** Lines Claude Code adds to a user turn that are not what the person typed. */
const isNoise = (t: string): boolean => /^\s*<(system-reminder|local-command|command-|ide_|task-notification)/.test(t);

const short = (s: string, n: number): string => {
  const one = s.replace(/\s+/g, ' ').trim();
  return one.length > n ? one.slice(0, n - 1) + '…' : one;
};

/** One tool call, in a few words: `Edit post.ts`, `Bash npm test`. */
export function describeTool(name: string, input: any): string {
  const i = input && typeof input === 'object' ? input : {};
  const file = i.file_path ?? i.notebook_path ?? i.path;
  if (typeof file === 'string' && /^(Read|Write|Edit|NotebookEdit|MultiEdit)$/.test(name)) return path.basename(file);
  if (typeof i.command === 'string') return short(i.command.replace(/^cd\s+\S+\s*(&&|;)\s*/, ''), 60);
  if (typeof i.pattern === 'string') return short(i.pattern, 50);
  if (typeof i.description === 'string') return short(i.description, 60);
  if (typeof i.url === 'string') return short(i.url, 60);
  if (typeof i.query === 'string') return short(i.query, 60);
  return '';
}

function parse(file: string, size: number): Parsed {
  const { head, tail } = readSlice(file, size);
  const first = lines(head);
  const last = lines(tail);
  const out: Parsed = { firstPrompt: '', cwd: '', branch: '', startedAt: 0, title: '', actions: [], lastCwd: '' };
  for (const o of first) {
    if (!out.startedAt && o.timestamp) out.startedAt = Date.parse(o.timestamp) || 0;
    if (!out.cwd && typeof o.cwd === 'string') out.cwd = o.cwd;
    if (!out.branch && typeof o.gitBranch === 'string' && o.gitBranch !== 'HEAD') out.branch = o.gitBranch;
    if (!out.firstPrompt && o.type === 'user' && o.message) {
      const t = textOf(o.message.content);
      if (t && !isNoise(t)) out.firstPrompt = t;
    }
  }
  for (const o of last) {
    if (o.type === 'ai-title' && typeof o.aiTitle === 'string') out.title = o.aiTitle;
    if (typeof o.cwd === 'string') out.lastCwd = o.cwd;
    if (typeof o.gitBranch === 'string' && o.gitBranch !== 'HEAD') out.branch = o.gitBranch;
    if (o.type === 'assistant' && Array.isArray(o.message?.content)) {
      const at = Date.parse(o.timestamp) || 0;
      for (const b of o.message.content) {
        if (b?.type === 'tool_use' && typeof b.name === 'string') out.actions.push({ tool: b.name, target: describeTool(b.name, b.input), at });
      }
    }
  }
  if (!out.title) {
    for (const o of last) if (o.type === 'last-prompt' && typeof o.lastPrompt === 'string') out.title = o.lastPrompt;
  }
  out.actions = out.actions.slice(-6);
  return out;
}

// ---- the reader -----------------------------------------------------------------------------------

/** Keeps parsed transcripts between scans; a file is re-read only when its size or mtime moves. */
export class AgentsReader {
  private readonly cache = new Map<string, { size: number; mtime: number; parsed: Parsed }>();

  private read(file: string, st: fs.Stats): Parsed | undefined {
    const hit = this.cache.get(file);
    if (hit && hit.size === st.size && hit.mtime === st.mtimeMs) return hit.parsed;
    try {
      const parsed = parse(file, st.size);
      this.cache.set(file, { size: st.size, mtime: st.mtimeMs, parsed });
      return parsed;
    } catch {
      return undefined;
    }
  }

  snapshot(opts: ReadOptions): AgentsSnapshot {
    const now = opts.now ?? Date.now();
    const claudeDir = opts.claudeDir ?? claudeProjectsDir();
    const since = now - (opts.sinceHours ?? 24) * 3_600_000;
    // sdlc tasks and requirements, stlc cases and defects, eval cases: one pattern for all three addons.
    const pattern = opts.itemPattern ?? /\b(?:TASK|REQ|TC|DEF|BUG|US|EV|CASE)-\d+\b/g;
    const spellings = pathSpellings(opts.projectRoot);
    const mentions = (s: string): boolean => {
      const l = s.toLowerCase();
      return spellings.some((p) => l.includes(p));
    };
    const counts: Record<AgentStatus, number> = { running: 0, quiet: 0, done: 0, stopped: 0 };
    const empty = (reason: string): AgentsSnapshot => ({ ok: false, reason, sessions: [], counts, scannedAt: now });

    if (!fs.existsSync(claudeDir)) return empty(`No Claude Code transcripts at ${claudeDir}.`);
    const sessions: SessionInfo[] = [];
    const seen = new Set<string>();

    for (const dir of candidateDirs(claudeDir, opts.projectRoot)) {
      let entries: string[];
      try {
        entries = fs.readdirSync(dir);
      } catch {
        continue;
      }
      for (const name of entries) {
        if (!name.endsWith('.jsonl')) continue;
        const id = name.slice(0, -6);
        if (seen.has(id)) continue;
        const file = path.join(dir, name);
        let st: fs.Stats;
        try {
          st = fs.statSync(file);
        } catch {
          continue;
        }
        const agents = this.agentsOf(path.join(dir, id, 'subagents'), since, now, opts.projectRoot, mentions, pattern);
        const lastAgentAt = Math.max(0, ...agents.map((a) => a.lastAt));
        if (st.mtimeMs < since && lastAgentAt < since) continue;
        const p = this.read(file, st);
        if (!p) continue;
        const own = belongsTo(p.cwd, opts.projectRoot) || belongsTo(p.lastCwd, opts.projectRoot);
        if (!own && agents.length === 0) continue;
        seen.add(id);
        const lastAt = Math.max(st.mtimeMs, lastAgentAt);
        const status = statusFor(undefined, st.mtimeMs, now) === 'running' ? 'running' : agents.some((a) => a.status === 'running') ? 'running' : st.mtimeMs > now - QUIET_MS ? 'quiet' : 'stopped';
        sessions.push({
          id,
          title: short(p.title || p.firstPrompt || id, 90),
          status,
          lastAt,
          where: p.lastCwd || p.cwd,
          actions: p.actions,
          agents,
          tables: seatAgents(agents),
          file,
        });
      }
    }
    sessions.sort((a, b) => b.lastAt - a.lastAt);
    for (const s of sessions) for (const a of s.agents) counts[a.status]++;
    return { ok: true, sessions, counts, scannedAt: now };
  }

  private agentsOf(dir: string, since: number, now: number, projectRoot: string, mentions: (s: string) => boolean, pattern: RegExp): AgentInfo[] {
    let names: string[];
    try {
      names = fs.readdirSync(dir);
    } catch {
      return [];
    }
    const out: AgentInfo[] = [];
    for (const name of names) {
      if (!name.endsWith('.jsonl')) continue;
      const file = path.join(dir, name);
      let st: fs.Stats;
      try {
        st = fs.statSync(file);
      } catch {
        continue;
      }
      if (st.mtimeMs < since) continue;
      const p = this.read(file, st);
      if (!p) continue;
      let meta: any = {};
      try {
        meta = JSON.parse(fs.readFileSync(file.replace(/\.jsonl$/, '.meta.json'), 'utf8'));
      } catch {
        // an older Claude Code wrote no meta file; the transcript alone still says enough
      }
      const where = meta.worktreePath || p.lastCwd || p.cwd;
      const ours = belongsTo(p.cwd, projectRoot) || belongsTo(where, projectRoot) || mentions(p.firstPrompt.slice(0, 4000));
      if (!ours) continue;
      const id = name.replace(/^agent-|\.jsonl$/g, '');
      const description = String(meta.description ?? '');
      const items = [...new Set(`${description}\n${p.firstPrompt.slice(0, 4000)}`.match(new RegExp(pattern.source, 'g')) ?? [])].slice(0, 8);
      out.push({
        id,
        name: agentName(id),
        role: String(meta.agentType ?? 'agent'),
        description: description || short(p.firstPrompt, 80),
        prompt: p.firstPrompt.slice(0, 1200),
        items,
        status: statusFor(meta.finished === true, st.mtimeMs, now),
        startedAt: p.startedAt || st.birthtimeMs,
        lastAt: st.mtimeMs,
        where,
        branch: meta.worktreeBranch || p.branch,
        actions: p.actions,
        parentId: typeof meta.parentAgentId === 'string' ? meta.parentAgentId.replace(/^agent-/, '') : undefined,
        file,
      });
    }
    assignNames(out);
    const order: Record<AgentStatus, number> = { running: 0, quiet: 1, stopped: 2, done: 3 };
    return out.sort((a, b) => order[a.status] - order[b.status] || b.lastAt - a.lastAt);
  }
}
