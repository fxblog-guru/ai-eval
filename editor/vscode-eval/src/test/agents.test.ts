/**
 * Tests for the agents reader: which chats and agents belong to a project, what each was asked,
 * what it did last, and that a transcript it does not understand is skipped, not fatal.
 */

import * as assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { test } from 'node:test';
import { AgentInfo, AgentsReader, agentName, assignNames, belongsTo, seatAgents, describeTool, encodeProjectDir, statusFor } from '../agents';

const NOW = Date.parse('2026-10-24T10:00:00Z');

function line(o: object): string {
  return JSON.stringify(o) + '\n';
}

/** A projects dir with a parent-folder chat that spawned agents into two projects. */
function fixture(): { claudeDir: string; work: string; blog: string; other: string } {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'agents-'));
  const work = path.join(tmp, 'work');
  const blog = path.join(work, 'blog');
  const other = path.join(work, 'other');
  const claudeDir = path.join(tmp, 'projects');
  const dir = path.join(claudeDir, encodeProjectDir(work));
  const subs = path.join(dir, 's1', 'subagents');
  fs.mkdirSync(subs, { recursive: true });
  const at = (min: number): string => new Date(NOW - min * 60_000).toISOString();

  fs.writeFileSync(
    path.join(dir, 's1.jsonl'),
    line({ type: 'user', cwd: work, timestamp: at(50), message: { role: 'user', content: '<system-reminder>x</system-reminder>' } }) +
      line({ type: 'user', cwd: work, timestamp: at(50), message: { role: 'user', content: [{ type: 'text', text: 'build TASK-001..003' }] } }) +
      line({ type: 'ai-title', aiTitle: 'Build the blog tasks' }) +
      'not json at all\n',
  );
  const agent = (id: string, cwd: string, prompt: string, minAgo: number, meta: object, tool?: object): void => {
    const f = path.join(subs, `agent-${id}.jsonl`);
    fs.writeFileSync(
      f,
      line({ type: 'user', cwd, gitBranch: 'feature/x', timestamp: at(minAgo + 5), message: { role: 'user', content: prompt } }) +
        (tool ? line({ type: 'assistant', cwd, timestamp: at(minAgo), message: { content: [{ type: 'tool_use', ...tool }] } }) : ''),
    );
    const t = new Date(NOW - minAgo * 60_000);
    fs.utimesSync(f, t, t);
    fs.writeFileSync(path.join(subs, `agent-${id}.meta.json`), JSON.stringify(meta));
  };
  agent('aaa1', blog, 'Lane api: do TASK-001', 1, { agentType: 'dev-implementer', description: 'Lane api' }, { name: 'Edit', input: { file_path: path.join(blog, 'src', 'post.ts') } });
  agent('bbb2', work, `In ${blog.replace(/\\/g, '/')} run TASK-002`, 10, { agentType: 'general-purpose', description: 'Lane web', finished: true });
  agent('ccc3', other, 'Unrelated TASK-900', 1, { description: 'Other project' });
  agent('ddd4', `${blog}-wt-content`, 'Lane content TASK-003', 2, { description: 'Lane content', parentAgentId: 'agent-aaa1' }, { name: 'Bash', input: { command: 'cd /x && npm test' } });
  const t = new Date(NOW - 1 * 60_000);
  fs.utimesSync(path.join(dir, 's1.jsonl'), t, t);
  return { claudeDir, work, blog, other };
}

test('a parent-folder chat shows only the agents that worked in the project', () => {
  const { claudeDir, blog } = fixture();
  const snap = new AgentsReader().snapshot({ projectRoot: blog, claudeDir, now: NOW });
  assert.equal(snap.ok, true);
  assert.equal(snap.sessions.length, 1);
  const s = snap.sessions[0];
  assert.equal(s.title, 'Build the blog tasks');
  assert.deepEqual(s.agents.map((a) => a.id).sort(), ['aaa1', 'bbb2', 'ddd4']);
  assert.deepEqual(snap.counts, { running: 2, quiet: 0, done: 1, stopped: 0 });
});

test('each agent says what it was asked, which items, and what it did last', () => {
  const { claudeDir, blog } = fixture();
  const s = new AgentsReader().snapshot({ projectRoot: blog, claudeDir, now: NOW }).sessions[0];
  const a = s.agents.find((x) => x.id === 'aaa1')!;
  assert.equal(a.role, 'dev-implementer');
  assert.equal(a.description, 'Lane api');
  assert.deepEqual(a.items, ['TASK-001']);
  assert.equal(a.status, 'running');
  assert.equal(a.branch, 'feature/x');
  assert.deepEqual(a.actions.map((x) => `${x.tool} ${x.target}`), ['Edit post.ts']);
  assert.equal(new Set(s.agents.map((x) => x.name)).size, s.agents.length);
  const d = s.agents.find((x) => x.id === 'ddd4')!;
  assert.equal(d.parentId, 'aaa1');
  assert.equal(d.actions[0].target, 'npm test');
});

test('the other project sees its own agent and not the blog lanes', () => {
  const { claudeDir, other } = fixture();
  const s = new AgentsReader().snapshot({ projectRoot: other, claudeDir, now: NOW }).sessions[0];
  assert.deepEqual(s.agents.map((a) => a.id), ['ccc3']);
});

test('nothing older than the window is opened', () => {
  const { claudeDir, blog } = fixture();
  const snap = new AgentsReader().snapshot({ projectRoot: blog, claudeDir, now: NOW + 48 * 3_600_000 });
  assert.equal(snap.sessions.length, 0);
});

test('a missing projects dir is a reason, not a throw', () => {
  const snap = new AgentsReader().snapshot({ projectRoot: os.tmpdir(), claudeDir: path.join(os.tmpdir(), 'no-such-claude-dir'), now: NOW });
  assert.equal(snap.ok, false);
  assert.match(snap.reason ?? '', /No Claude Code transcripts/);
});

test('status follows the last write', () => {
  assert.equal(statusFor(true, 0, NOW), 'done');
  assert.equal(statusFor(false, NOW - 60_000, NOW), 'running');
  assert.equal(statusFor(false, NOW - 10 * 60_000, NOW), 'quiet');
  assert.equal(statusFor(false, NOW - 60 * 60_000, NOW), 'stopped');
});

test('belongsTo takes the project, its insides and its sibling worktrees only', () => {
  assert.equal(belongsTo('C:\\w\\blog\\src', 'C:/w/blog'), true);
  assert.equal(belongsTo('C:/w/blog-wt-web', 'C:/w/blog'), true);
  assert.equal(belongsTo('C:/w/blogger', 'C:/w/blog'), false);
  assert.equal(belongsTo(undefined, 'C:/w/blog'), false);
});

test('a tool call reads as a few words', () => {
  assert.equal(describeTool('Read', { file_path: '/a/b/c.ts' }), 'c.ts');
  assert.equal(describeTool('Grep', { pattern: 'foo' }), 'foo');
  assert.equal(describeTool('Agent', { description: 'Lane api' }), 'Lane api');
  assert.equal(describeTool('X', null), '');
});

test('names are stable per id', () => {
  assert.equal(agentName('abc'), agentName('abc'));
});

test('no two agents in a chat share a name, and the first keeps its own', () => {
  const agents = Array.from({ length: 150 }, (_, i) => ({ id: `id${i}`, startedAt: i, name: '' }));
  assignNames(agents);
  assert.equal(new Set(agents.map((a) => a.name)).size, 150);
  assert.equal(agents[0].name, agentName('id0'));
});

test('agents running at the same time share a table; a later one sits at its own', () => {
  const mk = (id: string, start: number, end: number, extra: Partial<AgentInfo> = {}): AgentInfo =>
    ({ id, name: id, role: '', description: '', prompt: '', items: [], status: 'done', startedAt: start * 60_000, lastAt: end * 60_000, where: '', branch: '', actions: [], file: '', ...extra });
  const tables = seatAgents([
    mk('a', 0, 10, { items: ['TASK-1'] }),
    mk('b', 1, 12, { items: ['TASK-1', 'TASK-2'] }),
    mk('c', 11, 20, { status: 'running' }),
    mk('d', 60, 70),
    mk('e', 200, 210, { parentId: 'a' }),
  ]);
  const seats = tables.map((t) => t.agentIds.sort().join(''));
  assert.deepEqual(seats.sort(), ['abce', 'd']);
  const big = tables.find((t) => t.agentIds.includes('a'))!;
  assert.equal(big.status, 'running');
  assert.deepEqual(big.shared, ['TASK-1']);
  assert.equal(tables[0], big);
});
