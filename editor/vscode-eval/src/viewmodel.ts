/**
 * The view model: the index turned into what the board draws. Every judgement here is one the
 * index already made or EVAL-CONTRACTS states; the board adds wording and ordering, never verdicts.
 *
 * This file must not import `vscode`: the unit tests load it under plain Node.
 */

import { ActivityEvent, NEED_LABEL, openNeeds } from './activity';
import { EVAL_PHASES, EvalState, EvalSuite, FailureMode, GateVerdict, InstallInfo, LAYERS, LoadResult, Rate, phaseIndex } from './model';

export type Tone = 'ok' | 'bad' | 'warn' | 'muted' | 'accent';

export interface StepVM {
  key: string;
  label: string;
  state: 'done' | 'current' | 'todo';
}

export interface SuiteVM {
  suite: string;
  path: string;
  layer: string;
  gated: boolean;
  verdict: GateVerdict | 'NO RUN';
  tone: Tone;
  /** Why the verdict is what it is, in one line — the deciding gate, or why it cannot be decided. */
  why: string;
  passK: string | null;
  pass1: string | null;
  flaky: string | null;
  trend: 'up' | 'down' | 'same' | null;
  runId: string | null;
  summary: string | null;
  failing: string[];
  unvalidated: string[];
}

export interface LayerVM {
  layer: string;
  enabled: boolean | null;
  suites: number;
  verdict: GateVerdict | 'NO RUN' | 'OFF';
  tone: Tone;
}

export interface ItemVM {
  id: string;
  label: string;
  detail: string;
  path: string | null;
  tone: Tone;
}

export interface WarningVM {
  text: string;
  tone: Tone;
  path?: string;
}

export interface VersionVM {
  board: string;
  bundle: string | null;
  builder: string;
  update: { kind: 'patch' | 'minor' | 'major'; latest: string; label: string; command: string; changelogUrl: string | null } | null;
}

export type BoardVM =
  | {
      ok: true;
      project: string;
      tier: string | null;
      phase: string;
      nextCommand: string | null;
      generatedAt: string;
      steps: StepVM[];
      kpis: { label: string; value: string; tone: Tone; hint: string }[];
      layers: LayerVM[];
      suites: SuiteVM[];
      failureModes: ItemVM[];
      judges: ItemVM[];
      datasets: ItemVM[];
      probes: ItemVM[];
      scorecards: ItemVM[];
      warnings: WarningVM[];
      staleFiles: string[];
      version: VersionVM;
      summary: SummaryVM;
      activity: ActivityVM[];
      /** ai-eval keeps no decision ledger; always empty, so the Decisions view says so. */
      decisions: never[];
      findings: FindingVM[];
      needsYou: NeedVM[];
    }
  | { ok: false; reason: string; detail?: string; version: VersionVM };

export interface LayerScoreVM {
  layer: string;
  verdict: LayerVM['verdict'];
  tone: Tone;
  /** `holding`: every compared suite is within its margin of the baseline; `below`: one is not. */
  vsBaseline: 'holding' | 'below' | 'no baseline' | 'untrusted' | 'no run';
  /** One line per suite, e.g. "task-refunds 82.0% vs 84.0% (-2.0 pts)". */
  scores: string[];
}

export interface SummaryVM {
  /** What the suites evaluate: the system card's system, else the project. */
  evaluates: string;
  suites: number;
  latestRun: { suite: string; runId: string; verdict: string; tone: Tone; path: string | null } | null;
  layers: LayerScoreVM[];
  /** Layers at or within their margin of the baseline, of the layers that have one to compare. */
  atBaseline: { held: number; compared: number; percent: number | null };
  next: string | null;
}

export interface ActivityVM {
  kind: string;
  outcome: string;
  tone: Tone;
  title: string;
  at: string;
  slug: string | null;
  link: string | null;
}

export interface FindingVM {
  suite: string;
  /** A failure-mode id, or `total` for the suite's headline rate. */
  what: string;
  severity: 'blocking' | 'major' | 'minor' | 'unrated';
  base: number;
  now: number;
  /** Percentage points lost against the baseline. */
  drop: number;
  title: string;
  at: string;
  link: string | null;
}

export interface NeedVM {
  need: string;
  label: string;
  title: string;
  at: string;
  link: string | null;
}

export const pct =(v: number): string => `${(v * 100).toFixed(v === 1 || v === 0 ? 0 : 1)}%`;

/** A rate is never shown without its interval (EVAL-CONTRACTS §8.3). */
export function rateText(r: Rate | null): string | null {
  if (!r) return null;
  return `${pct(r.p)} [${pct(r.lo)}–${pct(r.hi)}] n=${r.n}`;
}

const toneOf = (v: GateVerdict | 'NO RUN' | 'OFF' | null): Tone =>
  v === 'PASS' ? 'ok' : v === 'FAIL' ? 'bad' : v === 'NOT-EVALUABLE' ? 'warn' : 'muted';

export function suiteVM(s: EvalSuite): SuiteVM {
  const run = s.latest_run;
  const verdict: SuiteVM['verdict'] = run?.verdict ?? 'NO RUN';
  let why: string;
  if (!run) why = s.evaluators.length ? 'never run' : 'no evaluators yet';
  else if (!s.gated) why = 'no gate declared — numbers, not a decision';
  else if (verdict === 'NOT-EVALUABLE' && s.unvalidated_judges.length) why = `judge not VALIDATED: ${s.unvalidated_judges.join(', ')}`;
  else if (verdict === 'NOT-EVALUABLE') why = 'the interval spans the threshold — not enough power to decide';
  else why = `decided by ${run.decided_by ?? 'its first gate'}`;
  let trend: SuiteVM['trend'] = null;
  const now = run?.pass_k?.p;
  const before = s.previous_run?.pass_k?.p;
  if (typeof now === 'number' && typeof before === 'number') {
    // Point estimates only steer the arrow; the scorecard decides regressions, per failure mode.
    trend = Math.abs(now - before) < 0.005 ? 'same' : now > before ? 'up' : 'down';
  }
  return {
    suite: s.suite,
    path: s.path,
    layer: s.layer ?? '?',
    gated: s.gated,
    verdict,
    tone: toneOf(verdict),
    why,
    passK: rateText(run?.pass_k ?? null),
    pass1: rateText(run?.pass_1 ?? null),
    flaky: rateText(run?.flaky ?? null),
    trend,
    runId: run?.run_id ?? null,
    summary: run?.summary ?? null,
    failing: run?.failing_cases ?? [],
    unvalidated: s.unvalidated_judges,
  };
}

/** The worst verdict wins: FAIL over NOT-EVALUABLE over PASS. A layer with no run says so. */
function worst(vs: SuiteVM['verdict'][]): SuiteVM['verdict'] {
  for (const v of ['FAIL', 'NOT-EVALUABLE', 'PASS'] as const) if (vs.includes(v)) return v;
  return 'NO RUN';
}

export function layersVM(state: EvalState, suites: SuiteVM[]): LayerVM[] {
  return LAYERS.map((layer) => {
    const mine = suites.filter((s) => s.layer === layer);
    const enabled = state.layers_enabled ? state.layers_enabled.includes(layer) : null;
    const verdict: LayerVM['verdict'] = enabled === false && !mine.length ? 'OFF' : worst(mine.map((s) => s.verdict));
    return { layer, enabled, suites: mine.length, verdict, tone: toneOf(verdict) };
  });
}

export interface BuildOptions {
  /** `<eval root>/logs/activity.jsonl`, parsed and newest first (docs/activity-format.md). */
  events?: ActivityEvent[];
  install?: InstallInfo;
  addonVersion?: string;
  dismissedUpdate?: string | null;
}

function versionVM(state: EvalState | null, opts: BuildOptions): VersionVM {
  const n = opts.install?.update ?? null;
  const pending = n && (n.kind === 'patch' || n.kind === 'minor' || n.kind === 'major') && n.latest && n.latest !== opts.dismissedUpdate ? n : null;
  return {
    board: opts.addonVersion ?? '',
    bundle: opts.install?.bundle ?? null,
    builder: state?.generator_version ?? '',
    update: pending
      ? {
          kind: pending.kind as 'patch' | 'minor' | 'major',
          latest: pending.latest!,
          label: pending.kind === 'major' ? `MAJOR update ${pending.latest}` : `update ${pending.latest}`,
          command: pending.command,
          changelogUrl: pending.changelogUrl,
        }
      : null,
  };
}

export function buildViewModel(result: LoadResult, opts: BuildOptions = {}): BoardVM {
  if (!result.ok) return { ok: false, reason: result.reason, detail: result.detail, version: versionVM(null, opts) };
  const st = result.state;
  const t = st.totals;
  const cur = phaseIndex(st.phase);
  const steps: StepVM[] = EVAL_PHASES.map((p, i) => ({ key: p, label: p, state: i < cur ? 'done' : i === cur ? 'current' : 'todo' }));
  const suites = st.suites.map(suiteVM);

  const warnings: WarningVM[] = [];
  if (st.system_card?.seed) warnings.push({ text: 'The system card is still the shipped seed — every number below is about example-system.', tone: 'warn', path: st.system_card.path });
  if (!st.system_card) warnings.push({ text: 'No system card: nothing states what is being evaluated.', tone: 'bad' });
  for (const s of suites) {
    if (s.gated && s.unvalidated.length) warnings.push({ text: `${s.suite} gates on ${s.unvalidated.join(', ')}, which is not VALIDATED — it can only report NOT-EVALUABLE (§5.4).`, tone: 'warn', path: s.path });
  }
  if (t.failure_modes_blocking_open) warnings.push({ text: `${t.failure_modes_blocking_open} blocking failure mode(s) open.`, tone: 'bad' });
  if (st.layers_enabled === null) warnings.push({ text: 'No EVAL-PROFILE.md found — enabled layers are unknown.', tone: 'muted' });
  if (result.staleFiles.length) warnings.push({ text: `The index may be out of date: ${result.staleFiles.length} file(s) changed since it was built.`, tone: 'muted' });

  const latestRuns = t.latest_pass + t.latest_fail + t.latest_not_evaluable;
  const kpis: { label: string; value: string; tone: Tone; hint: string }[] = [
    { label: 'Suites passing', value: `${t.latest_pass}/${latestRuns || t.suites}`, tone: t.latest_fail ? 'bad' : t.latest_not_evaluable ? 'warn' : latestRuns ? 'ok' : 'muted', hint: 'latest run of each suite' },
    { label: 'Not evaluable', value: String(t.latest_not_evaluable), tone: t.latest_not_evaluable ? 'warn' : 'muted', hint: 'the measurement itself was not trustworthy' },
    { label: 'Judges validated', value: `${t.judges_validated}/${t.judges}`, tone: t.judges && t.judges_validated < t.judges ? 'warn' : t.judges ? 'ok' : 'muted', hint: 'TPR/TNR on a held-out split' },
    { label: 'Open failure modes', value: String(t.failure_modes_open), tone: t.failure_modes_blocking_open ? 'bad' : t.failure_modes_open ? 'accent' : 'muted', hint: `${t.failure_modes_blocking_open} blocking` },
  ];

  const sevTone = (s: string | null): Tone => (s === 'blocking' || s === 'critical' ? 'bad' : s === 'major' || s === 'high' ? 'warn' : 'muted');
  return {
    ok: true,
    project: st.project,
    tier: st.risk_tier,
    phase: st.phase,
    nextCommand: st.next_command,
    generatedAt: st.generated_at,
    steps,
    kpis,
    layers: layersVM(st, suites),
    suites,
    failureModes: st.failure_modes
      .slice()
      .sort((a, b) => Number(a.status !== 'open') - Number(b.status !== 'open') || a.id.localeCompare(b.id))
      .map((f) => ({ id: f.id, label: f.title ?? f.id, detail: [f.severity, f.status, f.detector].filter(Boolean).join(' · '), path: f.path, tone: f.status === 'open' ? sevTone(f.severity) : 'muted' })),
    judges: st.judges.map((j) => ({
      id: j.id,
      label: j.verdict ?? 'no validation',
      detail: j.tpr !== null && j.tnr !== null ? `TPR ${j.tpr.toFixed(3)} · TNR ${j.tnr.toFixed(3)}${j.kappa !== null ? ` · κ ${j.kappa.toFixed(3)}` : ''}` : 'never scored on held-out labels',
      path: j.validation ?? j.path,
      tone: j.verdict === 'VALIDATED' ? 'ok' : 'warn',
    })),
    datasets: st.datasets.map((d) => ({
      id: d.id,
      label: `${d.cases} case(s)${d.retrieval ? ' · retrieval' : ''}`,
      detail: d.trace_share === null ? 'empty' : `${pct(d.trace_share)} from real traces · sha ${d.sha256.slice(0, 12)}`,
      path: d.path,
      // EVAL-CONTRACTS §7.2: under 30% from traces tests a product that does not exist.
      tone: d.trace_share !== null && d.trace_share < 0.3 ? 'warn' : 'muted',
    })),
    probes: st.redteam.map((p) => ({ id: p.id, label: p.code ?? p.id, detail: `${p.severity ?? '?'}${p.authorized ? '' : ' · no Authorization section'}`, path: p.path, tone: p.authorized ? sevTone(p.severity) : 'bad' })),
    scorecards: st.scorecards.map((c) => ({ id: c.slug, label: c.verdict ?? '?', detail: c.date, path: c.path, tone: toneOf(c.verdict) })),
    warnings,
    staleFiles: result.staleFiles,
    version: versionVM(st, opts),
    summary: summaryVM(st, suites),
    activity: (opts.events ?? []).map((e) => ({ kind: e.kind, outcome: e.outcome, tone: OUTCOME_TONE[e.outcome] ?? 'muted', title: e.title, at: e.at, slug: e.slug, link: e.link ?? null })),
    decisions: [],
    findings: findingsVM(opts.events ?? [], st.failure_modes),
    needsYou: openNeeds(opts.events ?? []).map((n) => ({ need: n.need, label: NEED_LABEL[n.need], title: n.title, at: n.at, link: n.link })),
  };
}

const OUTCOME_TONE: Record<string, Tone> = { pass: 'ok', fail: 'bad', changes: 'warn', blocked: 'bad', stale: 'warn', stopped: 'warn', info: 'muted' };

const pts = (v: number): string => (v * 100).toFixed(1);

/**
 * A suite against its baseline: the latest pass^k point estimate against the baseline's headline
 * rate, allowed to drop by `regression_margin`, the same rule as the runner's score event. A suite
 * whose judges are not VALIDATED decides nothing, so it is not compared (§5.4).
 */
export function suiteVsBaseline(s: EvalSuite): { state: LayerScoreVM['vsBaseline']; text: string } {
  // With one repeat, pass^k is pass^1, and the summary labels the row pass^1, so the index has it there.
  const now = s.latest_run?.pass_k ?? (s.repeats === 1 ? s.latest_run?.pass_1 : null) ?? null;
  const base = s.baseline_p;
  if (!s.latest_run) return { state: 'no run', text: `${s.suite}: never run` };
  if (s.unvalidated_judges.length) return { state: 'untrusted', text: `${s.suite}: judge not VALIDATED` };
  if (typeof base !== 'number') return { state: 'no baseline', text: `${s.suite} ${now ? `${pts(now.p)}%` : '—'}, no baseline` };
  if (!now) return { state: 'no baseline', text: `${s.suite}: no pass^k in the run summary` };
  const drop = base - now.p;
  return {
    state: drop > (s.regression_margin ?? 0) + 1e-9 ? 'below' : 'holding',
    text: `${s.suite} ${pts(now.p)}% vs ${pts(base)}% (${drop > 0 ? '-' : '+'}${pts(Math.abs(drop))} pts)`,
  };
}

function layerVsBaseline(states: LayerScoreVM['vsBaseline'][]): LayerScoreVM['vsBaseline'] {
  for (const s of ['below', 'holding', 'untrusted', 'no baseline'] as const) if (states.includes(s)) return s;
  return 'no run';
}

export function summaryVM(st: EvalState, suites: SuiteVM[]): SummaryVM {
  const layers: LayerScoreVM[] = layersVM(st, suites)
    .filter((l) => l.suites > 0)
    .map((l) => {
      const cmp = st.suites.filter((s) => (s.layer ?? '?') === l.layer).map(suiteVsBaseline);
      return { layer: l.layer, verdict: l.verdict, tone: l.tone, vsBaseline: layerVsBaseline(cmp.map((c) => c.state)), scores: cmp.map((c) => c.text) };
    });
  const compared = layers.filter((l) => l.vsBaseline === 'holding' || l.vsBaseline === 'below');
  const held = compared.filter((l) => l.vsBaseline === 'holding').length;
  const ran = st.suites.filter((s) => s.latest_run).sort((a, b) => b.latest_run!.run_id.localeCompare(a.latest_run!.run_id));
  const latest = ran[0];
  const run = latest?.latest_run;
  return {
    evaluates: st.system_card?.system ?? st.project,
    suites: st.suites.length,
    latestRun: latest && run ? { suite: latest.suite, runId: run.run_id, verdict: run.verdict ?? 'no summary', tone: toneOf(run.verdict), path: run.summary ?? run.path } : null,
    layers,
    atBaseline: { held, compared: compared.length, percent: compared.length ? Math.round((held / compared.length) * 100) : null },
    next: st.next_command,
  };
}

// The runner writes this title shape for a regression (workspace/evals/scripts/shared/activity.py).
const REGRESSION = /^regression (\S+) (\S+): (\d+(?:\.\d+)?)% -> (\d+(?:\.\d+)?)% \(-(\d+(?:\.\d+)?) pts\)$/;
const SEVERITY_RANK = { blocking: 0, major: 1, minor: 2, unrated: 3 } as const;

/**
 * Regressions from the activity log. Only the newest per suite and failure mode is kept, and a
 * later passing score for the suite clears it: the run after the fix is the evidence of the fix.
 * Ordered by the failure mode's severity, then by the size of the drop. `events` is newest first.
 */
export function findingsVM(events: ActivityEvent[], fms: FailureMode[]): FindingVM[] {
  const sev = new Map(fms.map((f) => [f.id, f.severity]));
  // The newest passing score per suite. It clears findings of OLDER runs only: a run whose total
  // holds can still regress one failure mode, and its own pass must not hide that finding.
  const cleared = new Map<string, ActivityEvent>();
  const isOlder = (f: ActivityEvent, pass: ActivityEvent): boolean =>
    f.run_id && pass.run_id ? f.run_id !== pass.run_id : f.at < pass.at;
  const seen = new Set<string>();
  const out: FindingVM[] = [];
  for (const e of events) {
    if (e.source !== 'eval' || !e.slug) continue;
    if (e.kind === 'score' && e.outcome === 'pass' && !cleared.has(e.slug)) cleared.set(e.slug, e);
    const pass = cleared.get(e.slug);
    if (e.kind !== 'finding' || e.outcome !== 'fail' || (pass && isOlder(e, pass))) continue;
    const m = REGRESSION.exec(e.title);
    if (!m) continue;
    const key = `${e.slug}|${m[1]}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ suite: e.slug, what: m[1], severity: sev.get(m[1]) ?? 'unrated', base: Number(m[3]), now: Number(m[4]), drop: Number(m[5]), title: e.title, at: e.at, link: e.link ?? null });
  }
  return out.sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || b.drop - a.drop || a.suite.localeCompare(b.suite));
}

/** One line for the status bar. */
export function statusLine(vm: BoardVM): { text: string; tone: Tone } {
  if (!vm.ok) return { text: 'Eval', tone: 'warn' };
  const fail = vm.suites.filter((s) => s.verdict === 'FAIL').length;
  const ne = vm.suites.filter((s) => s.verdict === 'NOT-EVALUABLE').length;
  const pass = vm.suites.filter((s) => s.verdict === 'PASS').length;
  const ran = fail + ne + pass;
  const parts = [`${vm.phase}`];
  if (ran) parts.push(`${pass}✓ ${fail}✗${ne ? ` ${ne}?` : ''}`);
  return { text: parts.join(' · '), tone: fail ? 'bad' : ne ? 'warn' : ran ? 'ok' : 'muted' };
}
