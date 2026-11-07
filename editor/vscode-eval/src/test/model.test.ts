/**
 * Tests for loading the index and the view model. They build the index from the bundle's own seed
 * and broken fixture with the shipped builder (build_state.py), so a change to the builder's output
 * that the board does not understand fails here, not in a reader's editor.
 *
 * Run with: npm run compile && npm test   (needs python3, or PYTHON=<interpreter>)
 */

import * as assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { test } from 'node:test';
import { findProjectRoots, loadState, parseUpdateNotice, readInstallInfo, resolveInProject, resolveStatePath } from '../model';
import { BoardVM, buildViewModel, rateText, statusLine } from '../viewmodel';

const BUNDLE = path.resolve(__dirname, '../../../..');
const BUILDER = path.join(BUNDLE, 'workspace/evals/scripts/shared/build_state.py');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

type OkVM = Extract<BoardVM, { ok: true }>;

/** A temp project holding a copy of `src` as `evals/`, with state.json built by the shipped builder. */
function project(src: string, extra: Record<string, string> = {}): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'eval-board-'));
  fs.cpSync(src, path.join(root, 'evals'), { recursive: true });
  for (const [rel, body] of Object.entries(extra)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), body);
  }
  execFileSync(PY, [BUILDER, '--root', path.join(root, 'evals'), '--quiet'], { env: { ...process.env, EVAL_STATE_NOW: '2099-01-01T00:00:00+00:00' } });
  return root;
}
const SEED = path.join(BUNDLE, 'workspace/evals');
const BROKEN = path.join(BUNDLE, 'tests/fixture/evals');

function board(root: string): OkVM {
  const r = loadState(root, 'evals/state.json');
  assert.ok(r.ok, r.ok ? '' : r.reason);
  const vm = buildViewModel(r, { install: readInstallInfo(root), addonVersion: '0.1.0' });
  assert.ok(vm.ok);
  return vm;
}

test('the seed loads: two suites, the seed warning, no judges to calibrate', () => {
  const vm = board(project(SEED));
  assert.equal(vm.project, 'example-system');
  assert.deepEqual(vm.suites.map((s) => s.suite), ['rag-example', 'task-example']);
  assert.ok(vm.warnings.some((w) => /shipped seed/.test(w.text)), 'the seed is called out');
  assert.equal(vm.nextCommand, '/eval-scope --refresh');
  assert.equal(vm.judges.length, 0);
});

test('a run is shown with its interval, never a bare point estimate', () => {
  const vm = board(project(SEED));
  const task = vm.suites.find((s) => s.suite === 'task-example')!;
  if (task.runId) {
    assert.match(task.passK ?? '', /\[.*–.*\] n=\d+/);
    // An ungated suite decides nothing, so it is never PASS (EVAL-CONTRACTS 8.3).
    assert.notEqual(task.verdict, 'PASS');
    assert.match(task.why, /no gate declared/);
  }
  assert.equal(rateText({ p: 0.84, lo: 0.79, hi: 0.88, n: 240 }), '84.0% [79.0%–88.0%] n=240');
});

test('a gated suite on an unvalidated judge is called out, and the next step is /eval-validate', () => {
  const vm = board(project(BROKEN));
  assert.ok(vm.warnings.some((w) => /not VALIDATED/.test(w.text)));
  assert.match(vm.nextCommand ?? '', /^\/eval-validate JDG-/);
  const tone = vm.judges.find((j) => j.id === 'JDG-tone-v1')!;
  assert.equal(tone.label, 'UNVALIDATED');
  assert.equal(tone.tone, 'warn');
  assert.ok(vm.probes.some((p) => p.tone === 'bad' && /no Authorization/.test(p.detail)), 'a probe with no authorization is red');
});

test('a NOT-EVALUABLE run is its own verdict, never folded into pass or fail', () => {
  const root = project(SEED);
  const run = path.join(root, 'evals/runs/task-example/2099-01-01-0000');
  fs.mkdirSync(run, { recursive: true });
  fs.writeFileSync(path.join(run, 'summary.md'), '# x\n\n## Verdict\nNOT-EVALUABLE — decided by `judge not validated`\n\n## Results\n| Metric | Value | n |\n|---|---|---|\n| pass^3 (per case) | 0.840 [0.790, 0.880] (n=240) | 240 |\n');
  execFileSync(PY, [BUILDER, '--root', path.join(root, 'evals'), '--quiet']);
  const vm = board(root);
  const task = vm.suites.find((s) => s.suite === 'task-example')!;
  assert.equal(task.verdict, 'NOT-EVALUABLE');
  assert.equal(task.tone, 'warn');
  assert.equal(statusLine(vm).tone, 'warn');
  assert.equal(vm.layers.find((l) => l.layer === 'L2')!.verdict, 'NOT-EVALUABLE');
});

test('the profile decides which layers are off', () => {
  const profile = fs.readFileSync(path.join(BUNDLE, 'EVAL-PROFILE.md'), 'utf8');
  const vm = board(project(SEED, { '.claude/EVAL-PROFILE.md': profile }));
  assert.equal(vm.layers.find((l) => l.layer === 'L3')!.verdict, 'OFF');
  assert.equal(vm.layers.find((l) => l.layer === 'L1')!.enabled, true);
});

test('loadState says why when the index is missing, malformed or of another schema', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'eval-load-'));
  const missing = loadState(root, 'evals/state.json');
  assert.ok(!missing.ok && /No eval state index/.test(missing.reason));
  fs.mkdirSync(path.join(root, 'evals'));
  fs.writeFileSync(path.join(root, 'evals/state.json'), '{');
  const bad = loadState(root, 'evals/state.json');
  assert.ok(!bad.ok && /not valid JSON/.test(bad.reason));
  fs.writeFileSync(path.join(root, 'evals/state.json'), JSON.stringify({ schema: 9, suites: [] }));
  const other = loadState(root, 'evals/state.json');
  assert.ok(!other.ok && /schema 9/.test(other.reason));
});

test('the update notice: only version-shaped values, a fixed command, https changelogs', () => {
  const doc = (b: object): string => JSON.stringify({ bundles: { eval: b } });
  const n = parseUpdateNotice(doc({ installed: '1.0.0', latest: '1.1.0', kind: 'minor', command: 'rm -rf /', changelog_url: 'https://gitlab.com/x/CHANGELOG.md' }))!;
  assert.equal(n.command, 'afx update --bundle eval', 'a command from the file is never what runs');
  const npx = parseUpdateNotice(doc({ installed: '1.0.0', latest: '1.1.0', kind: 'minor', source: 'npm:agentic-fx@0.1.0', command: 'rm -rf /' }))!;
  assert.equal(npx.command, 'npx agentic-fx@latest update --bundle eval', 'an npx-installed project is told the npx command');
  assert.equal(n.latest, '1.1.0');
  assert.equal(parseUpdateNotice(doc({ latest: '$(evil)', kind: 'minor' }))!.latest, null);
  assert.equal(parseUpdateNotice(doc({ latest: '1.1.0', kind: 'minor', changelog_url: 'javascript:alert(1)' }))!.changelogUrl, null);
  assert.equal(parseUpdateNotice('{"bundles":{"qa":{}}}'), null, 'another bundle\'s notice is not ours');
  const root = project(SEED, {
    '.claude/.agentic-fx.json': JSON.stringify({ eval: { version: '1.0.0' } }),
    '.claude/.agentic-fx-updates.json': doc({ installed: '1.0.0', latest: '2.0.0', kind: 'major' }),
  });
  const vm = board(root);
  assert.equal(vm.version.bundle, '1.0.0');
  assert.equal(vm.version.update?.label, 'MAJOR update 2.0.0');
});

test('project discovery skips dot folders and never resolves outside the project', () => {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'eval-ws-'));
  for (const p of ['a/evals', '.claude/worktrees/x/evals', 'node_modules/y/evals']) {
    fs.mkdirSync(path.join(ws, p), { recursive: true });
    fs.writeFileSync(path.join(ws, p, 'state.json'), '{}');
  }
  assert.deepEqual(findProjectRoots(ws, 'evals/state.json').map((p) => path.basename(p.root)), ['a']);
  assert.equal(resolveInProject(ws, '../etc/passwd'), undefined);
  assert.equal(resolveInProject(ws, 'C:/Windows'), undefined);
  assert.ok(resolveInProject(ws, 'evals/suites/x.yaml'));
});

test('the builder copies the baseline rate, and the board reads the activity log into its views', async () => {
  const { readEvents } = await import('../events');
  const root = project(SEED, {
    'evals/baselines/BASE-2026-10-01-x.json': JSON.stringify({ id: 'BASE-2026-10-01-x', results: { task_success: { p: 0.9 } } }),
    'evals/logs/activity.jsonl': [
      '{"v":1,"at":"2026-10-22T09:00:00Z","source":"eval","kind":"finding","slug":"task-example","outcome":"fail","title":"regression total task-example: 90.0% -> 50.0% (-40.0 pts)","link":"evals/runs/task-example/2099-01-01-0000/summary.md","needs":null}',
      '{"v":1,"at":"2026-10-22T09:00:00Z","source":"eval","kind":"run","slug":"task-example","outcome":"fail","title":"task-example FAIL","needs":"review-stop"}',
      '',
    ].join('\n'),
  });
  const yaml = path.join(root, 'evals/suites/task-example.yaml');
  fs.appendFileSync(yaml, '\nbaseline: BASE-2026-10-01-x\ngates:\n  regression_margin: 0.05\n');
  execFileSync(PY, [BUILDER, '--root', path.join(root, 'evals'), '--quiet']);
  const r = loadState(root, 'evals/state.json');
  assert.ok(r.ok);
  const task = r.state.suites.find((s) => s.suite === 'task-example')!;
  assert.equal(task.baseline_p, 0.9);
  assert.equal(task.regression_margin, 0.05);
  const vm = buildViewModel(r, { events: readEvents(root, 'evals') });
  assert.ok(vm.ok);
  assert.equal(vm.activity.length, 2);
  assert.deepEqual(vm.findings.map((f) => f.drop), [40]);
  assert.deepEqual(vm.needsYou.map((n) => n.need), ['review-stop']);
  assert.deepEqual(vm.decisions, []);
  assert.deepEqual(readEvents(root, 'nowhere'), []);
});

test('the state path follows the root order: setting, then .evals/, then evals/, then .evals', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'eval-root-'));
  assert.equal(resolveStatePath(dir), '.evals/state.json', 'a new project');
  fs.mkdirSync(path.join(dir, 'evals'));
  assert.equal(resolveStatePath(dir), 'evals/state.json', 'an older project keeps evals/');
  fs.mkdirSync(path.join(dir, '.evals'));
  assert.equal(resolveStatePath(dir), '.evals/state.json', '.evals/ wins when both exist');
  assert.equal(resolveStatePath(dir, 'quality/evals/state.json'), 'quality/evals/state.json');
  assert.equal(resolveStatePath(dir, '  '), '.evals/state.json', 'a blank setting is no setting');
});
