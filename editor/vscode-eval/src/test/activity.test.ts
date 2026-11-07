/**
 * The shared activity format, read side. vscode-sdlc, vscode-stlc and vscode-qa-standup carry the
 * same first three cases against their copy of activity.ts; the rest are the eval views.
 */

import * as assert from 'node:assert/strict';
import { test } from 'node:test';
import { ActivityEvent, isEvent, openNeeds, parseActivity } from '../activity';

const ev = (over: Partial<ActivityEvent>): ActivityEvent => ({ v: 1, at: '2026-10-22T09:00:00Z', source: 'sdlc', kind: 'gate', slug: 'demo', outcome: 'pass', title: 'G1 PASS', link: null, needs: null, ...over });

test('parseActivity keeps valid lines newest first and skips torn or foreign ones', () => {
  const text = [
    JSON.stringify(ev({ at: '2026-10-22T08:00:00Z', title: 'older' })),
    '{"v":1,"at":"2026-10-22T09',
    JSON.stringify({ ...ev({}), v: 2 }),
    JSON.stringify(ev({ at: '2026-10-22T10:00:00Z', title: 'newer' })),
    '',
  ].join('\n');
  assert.deepEqual(parseActivity(text).map((e) => e.title), ['newer', 'older']);
});

test('isEvent refuses each broken field', () => {
  assert.ok(isEvent(ev({})));
  for (const bad of [{ at: '2026-10-22 09:00' }, { source: 'jira' }, { kind: 'commit' }, { outcome: 'ok' }, { title: '' }, { needs: 'coffee' }]) {
    assert.equal(isEvent({ ...ev({}), ...bad }), false, JSON.stringify(bad));
  }
});

test('openNeeds: a need stays until a later pass for the same slug and link clears it', () => {
  const events = [
    ev({ at: '2026-10-22T11:00:00Z', kind: 'decision', title: 'DEC-004 answered', outcome: 'pass', slug: 'demo', link: 'x' }),
    ev({ at: '2026-10-22T10:00:00Z', kind: 'decision', title: 'DEC-004 assumed', outcome: 'info', needs: 'confirm-dec', link: 'x' }),
    ev({ at: '2026-10-22T09:30:00Z', kind: 'gate', title: 'G5 ui PASS', needs: 'approve-ui', link: 'g5.md' }),
    ev({ at: '2026-10-22T09:00:00Z', kind: 'gate', title: 'G5 ui PASS (older)', needs: 'approve-ui', link: 'g5.md' }),
    ev({ at: '2026-10-22T08:00:00Z', kind: 'stop', title: 'stopped at merge', outcome: 'stopped', needs: 'merge', slug: 'other' }),
  ];
  const open = openNeeds(events);
  assert.deepEqual(open.map((n) => `${n.slug} ${n.need}`), ['demo approve-ui', 'other merge'], 'DEC-004 is cleared, G5 listed once');
});


// ---- the eval views over the log ------------------------------------------------------------------

import { findingsVM, suiteVsBaseline, summaryVM, suiteVM } from '../viewmodel';
import type { EvalState, EvalSuite } from '../model';

const reg = (over: Partial<ActivityEvent>): ActivityEvent => ev({ source: 'eval', kind: 'finding', outcome: 'fail', slug: 'task-a', ...over });

test('findingsVM: severity first, then the size of the drop; a later passing score clears a suite', () => {
  const fms = [{ id: 'FM-001', title: null, severity: 'blocking', status: 'open', detector: null, frequency: null, path: 'x' }] as EvalState['failure_modes'];
  const events = [
    ev({ source: 'eval', kind: 'score', outcome: 'pass', slug: 'task-c', title: 'L2 task-c 90.0% vs baseline 90.0% (+0.0 pts)', at: '2026-10-22T12:00:00Z' }),
    reg({ title: 'regression total task-a: 90.0% -> 70.0% (-20.0 pts)', link: 'evals/runs/task-a/r/summary.md', at: '2026-10-22T11:00:00Z' }),
    reg({ title: 'regression FM-001 task-b: 95.0% -> 90.0% (-5.0 pts)', slug: 'task-b', at: '2026-10-22T11:00:00Z' }),
    reg({ title: 'regression total task-a: 90.0% -> 80.0% (-10.0 pts)', at: '2026-10-22T10:00:00Z' }),
    reg({ title: 'regression total task-c: 90.0% -> 50.0% (-40.0 pts)', slug: 'task-c', at: '2026-10-22T09:00:00Z' }),
    reg({ title: 'not a regression line' }),
  ];
  const f = findingsVM(events, fms);
  assert.deepEqual(f.map((x) => `${x.suite} ${x.what} ${x.drop}`), ['task-b FM-001 5', 'task-a total 20'], 'blocking FM first; task-a once, newest; task-c cleared');
  assert.equal(f[1].link, 'evals/runs/task-a/r/summary.md');
});

// The runner writes score (pass) and an FM finding of one run with the same `at`; the run's own
// pass must not clear its failure-mode regression.
test('findingsVM: a run whose total holds still shows its failure-mode regression', () => {
  const fms = [{ id: 'FM-001', title: null, severity: 'major', status: 'open', detector: null, frequency: null, path: 'x' }] as EvalState['failure_modes'];
  const at = '2026-10-22T12:00:00Z';
  const events = [
    ev({ source: 'eval', kind: 'score', outcome: 'pass', slug: 's', title: 'L2 s 95.0% vs baseline 95.0% (+0.0 pts)', at, run_id: 'r2' }),
    reg({ title: 'regression FM-001 s: 95.0% -> 80.0% (-15.0 pts)', slug: 's', at, run_id: 'r2' }),
    reg({ title: 'regression total s: 95.0% -> 60.0% (-35.0 pts)', slug: 's', at: '2026-10-21T12:00:00Z', run_id: 'r1' }),
  ];
  assert.deepEqual(findingsVM(events, fms).map((x) => `${x.suite} ${x.what}`), ['s FM-001'], 'r2 FM shown; r1 total cleared by r2 pass');
});

const suite = (over: Partial<EvalSuite>): EvalSuite => ({
  suite: 'task-a', path: 'evals/suites/task-a.yaml', layer: 'L2', dataset: 'DS', model: 'm', repeats: 3, gated: true, gates: {}, baseline: 'BASE-x',
  baseline_p: 0.9, regression_margin: 0.05, evaluators: ['assert:x'], unvalidated_judges: [], runs: 1, previous_run: null,
  latest_run: { run_id: '2026-10-22-0900', path: 'evals/runs/task-a/2026-10-22-0900', summary: 'evals/runs/task-a/2026-10-22-0900/summary.md', ctrf: null, verdict: 'PASS', decided_by: null, pass_1: null, pass_k: { p: 0.86, lo: 0.8, hi: 0.9, n: 100 }, flaky: null, failed_attempts: 0, errors: 0, failing_cases: [] },
  ...over,
});

test('suiteVsBaseline: within the margin holds, past it is below; untrusted and unbaselined are never compared', () => {
  assert.deepEqual(suiteVsBaseline(suite({})), { state: 'holding', text: 'task-a 86.0% vs 90.0% (-4.0 pts)' });
  assert.equal(suiteVsBaseline(suite({ regression_margin: 0.02 })).state, 'below');
  assert.equal(suiteVsBaseline(suite({ unvalidated_judges: ['JDG-x-v1'] })).state, 'untrusted');
  assert.equal(suiteVsBaseline(suite({ baseline_p: null })).state, 'no baseline');
  assert.equal(suiteVsBaseline(suite({ latest_run: null })).state, 'no run');
  const once = suite({ repeats: 1 });
  once.latest_run = { ...once.latest_run!, pass_k: null, pass_1: { p: 0.95, lo: 0.9, hi: 1, n: 50 } };
  assert.equal(suiteVsBaseline(once).state, 'holding', 'with one repeat, pass^1 is pass^k');
});

test('summaryVM: per-layer score vs baseline, and the share of compared layers at or above it', () => {
  const suites = [suite({}), suite({ suite: 'agent-a', layer: 'L3', regression_margin: 0 }), suite({ suite: 'nfr-a', layer: 'L5', baseline_p: null })];
  const st = { layers_enabled: null, suites, system_card: { path: 'x', system: 'refund-bot', seed: false, risk_tier: 'low' }, project: 'p', next_command: '/eval-report' } as unknown as EvalState;
  const s = summaryVM(st, suites.map(suiteVM));
  assert.equal(s.evaluates, 'refund-bot');
  assert.deepEqual(s.layers.map((l) => `${l.layer} ${l.vsBaseline}`), ['L2 holding', 'L3 below', 'L5 no baseline']);
  assert.deepEqual(s.atBaseline, { held: 1, compared: 2, percent: 50 });
  assert.equal(s.latestRun?.suite, 'task-a');
  assert.equal(s.next, '/eval-report');
});
