/**
 * Types mirroring EVAL-CONTRACTS.md §15 (the `evals/state.json` derived read model), the loader,
 * project discovery, the installer's update notice and the freshness check.
 *
 * This file must not import `vscode`: the unit tests load it under plain Node.
 */

import * as fs from 'fs';
import * as path from 'path';

export const SUPPORTED_SCHEMA = 1;

export type EvalPhase = 'Scope' | 'Explore' | 'Data' | 'Evaluate' | 'Validate' | 'Run' | 'Report';

/** The /eval-status ladder (EVAL-CONTRACTS §15), bottom rung first. Sign-off belongs to stlc. */
export const EVAL_PHASES: EvalPhase[] = ['Scope', 'Explore', 'Data', 'Evaluate', 'Validate', 'Run', 'Report'];
export const LAYERS = ['L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6'] as const;

export type GateVerdict = 'PASS' | 'FAIL' | 'NOT-EVALUABLE';

export interface Rate {
  p: number;
  lo: number;
  hi: number;
  n: number;
}

export interface EvalRun {
  run_id: string;
  path: string;
  summary: string | null;
  ctrf: string | null;
  verdict: GateVerdict | null;
  decided_by: string | null;
  pass_1: Rate | null;
  pass_k: Rate | null;
  flaky: Rate | null;
  failed_attempts: number | null;
  errors: number | null;
  failing_cases: string[];
}

export interface EvalSuite {
  suite: string;
  path: string;
  layer: string | null;
  dataset: string | null;
  model: string | null;
  repeats: number | null;
  gated: boolean;
  gates: Record<string, unknown>;
  baseline: string | null;
  /** The baseline's headline rate (builder 1.1.0+); absent from older indexes, null when unreadable. */
  baseline_p?: number | null;
  /** `gates.regression_margin`, else 0 (builder 1.1.0+). */
  regression_margin?: number;
  evaluators: string[];
  unvalidated_judges: string[];
  runs: number;
  latest_run: EvalRun | null;
  previous_run: { run_id: string; verdict: GateVerdict | null; pass_k: Rate | null } | null;
}

export interface FailureMode {
  id: string;
  title: string | null;
  severity: 'blocking' | 'major' | 'minor' | null;
  status: 'open' | 'mitigated' | 'retired' | null;
  detector: string | null;
  frequency: string | null;
  path: string;
}

export interface Dataset {
  id: string;
  path: string;
  meta: string | null;
  retrieval: boolean;
  cases: number;
  trace_share: number | null;
  sha256: string;
}

export interface Judge {
  id: string;
  path: string;
  validation: string | null;
  verdict: 'VALIDATED' | 'UNVALIDATED' | null;
  tpr: number | null;
  tnr: number | null;
  kappa: number | null;
}

export interface Probe {
  id: string;
  code: string | null;
  severity: 'critical' | 'high' | 'medium' | 'low' | null;
  authorized: boolean;
  path: string;
}

export interface Scorecard {
  slug: string;
  date: string;
  path: string;
  verdict: GateVerdict | null;
}

export interface EvalTotals {
  failure_modes_open: number;
  failure_modes_blocking_open: number;
  datasets: number;
  judges: number;
  judges_validated: number;
  suites: number;
  suites_gated: number;
  runs: number;
  latest_pass: number;
  latest_fail: number;
  latest_not_evaluable: number;
  redteam_probes: number;
}

export interface EvalState {
  schema: number;
  generator_version: string;
  generated_at: string;
  source_hash: string;
  root: string;
  project: string;
  system_slug: string | null;
  risk_tier: 'low' | 'medium' | 'high' | null;
  /** null when no EVAL-PROFILE.md was found — unknown, not "none". */
  layers_enabled: string[] | null;
  profile: string | null;
  phase: EvalPhase;
  next_command: string | null;
  system_card: { path: string; system: string | null; seed: boolean; risk_tier: string | null } | null;
  totals: EvalTotals;
  failure_modes: FailureMode[];
  datasets: Dataset[];
  judges: Judge[];
  suites: EvalSuite[];
  redteam: Probe[];
  baselines: string[];
  scorecards: Scorecard[];
  audit: { date: string; path: string; mentions_blocking: number } | null;
}

export type LoadResult =
  | { ok: true; state: EvalState; statePath: string; projectRoot: string; staleFiles: string[] }
  | { ok: false; reason: string; detail?: string; statePath: string; projectRoot: string };

export function phaseIndex(phase: EvalPhase): number {
  const i = EVAL_PHASES.indexOf(phase);
  return i === -1 ? 0 : i;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/**
 * Load the index. `chosenRoot` is the project the reader picked; otherwise the workspace root when
 * it holds the index, else the project whose index was written most recently.
 */
export function loadState(workspaceRoot: string, relStatePath: string, chosenRoot?: string): LoadResult {
  const projectRoot = chosenRoot ?? findProjectRoot(workspaceRoot, relStatePath) ?? workspaceRoot;
  const statePath = path.join(projectRoot, relStatePath);
  let raw: string;
  try {
    raw = fs.readFileSync(statePath, 'utf8');
  } catch {
    return {
      ok: false,
      projectRoot,
      statePath,
      reason: 'No eval state index found.',
      detail:
        `Expected ${relStatePath}. It is generated — run \`python3 ${path.posix.dirname(relStatePath) || '.evals'}/scripts/shared/build_state.py\` ` +
        `(or any /eval-* command; the Stop hook rebuilds it). Check evalBoard.statePath if your eval root differs.`,
    };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    return { ok: false, statePath, projectRoot, reason: 'The eval state index is not valid JSON.', detail: err instanceof Error ? err.message : String(err) };
  }
  if (!isRecord(parsed) || typeof parsed.schema !== 'number') {
    return { ok: false, statePath, projectRoot, reason: 'The eval state index has no schema field.' };
  }
  if (parsed.schema !== SUPPORTED_SCHEMA) {
    return {
      ok: false,
      statePath,
      projectRoot,
      reason: `Unsupported eval state schema ${parsed.schema}.`,
      detail: `This board understands schema ${SUPPORTED_SCHEMA}. Rather than guess at a layout it does not know, it shows nothing. Update the extension, or check which bundle version wrote this file.`,
    };
  }
  const state = parsed as unknown as EvalState;
  if (!Array.isArray(state.suites)) return { ok: false, statePath, projectRoot, reason: 'The eval state index has no suites array.' };
  state.failure_modes ??= [];
  state.datasets ??= [];
  state.judges ??= [];
  state.redteam ??= [];
  state.scorecards ??= [];
  state.baselines ??= [];
  return { ok: true, state, statePath, projectRoot, staleFiles: findStaleFiles(projectRoot, state) };
}

const SKIP_DIRS = new Set(['node_modules', 'vendor', 'out', 'dist', 'build', '__pycache__', 'venv']);
const MAX_DEPTH = 5;

export interface ProjectRef {
  root: string;
  /** Modification time of the project's index in ms. */
  mtime: number;
}

/**
 * Every project under the workspace that has an index, newest first. A folder with an index is a
 * project and is not searched further; dot folders (`.claude/worktrees`, `.git`, `.venv`) and
 * dependency or build folders are skipped.
 */
/** The eval root's two names, the fresh-install one first (EVAL-CONTRACTS §2). */
export const ROOT_NAMES = ['.evals', 'evals'] as const;

/**
 * The state index to read, relative to a project: the setting when it is set, else
 * `.evals/state.json` when the project has a `.evals/` root, else `evals/state.json`.
 */
export function resolveStatePath(projectRoot: string, setting?: string): string {
  const s = (setting ?? '').trim();
  if (s) return s;
  for (const name of ROOT_NAMES) {
    try {
      if (fs.statSync(path.join(projectRoot, name)).isDirectory()) return `${name}/state.json`;
    } catch {
      // not this one
    }
  }
  return `${ROOT_NAMES[0]}/state.json`;
}

export function findProjectRoots(workspaceRoot: string, relStatePath: string): ProjectRef[] {
  const found: ProjectRef[] = [];
  const probe = (dir: string): boolean => {
    try {
      found.push({ root: dir, mtime: fs.statSync(path.join(dir, relStatePath)).mtimeMs });
      return true;
    } catch {
      return false;
    }
  };
  const walk = (dir: string, depth: number): void => {
    if (depth > MAX_DEPTH) return;
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (!e.isDirectory() || e.name.startsWith('.') || SKIP_DIRS.has(e.name)) continue;
      const candidate = path.join(dir, e.name);
      if (!probe(candidate)) walk(candidate, depth + 1);
    }
  };
  if (!probe(workspaceRoot)) walk(workspaceRoot, 1);
  return found.sort((a, b) => b.mtime - a.mtime);
}

export function findProjectRoot(workspaceRoot: string, relStatePath: string): string | undefined {
  if (fs.existsSync(path.join(workspaceRoot, relStatePath))) return workspaceRoot;
  return findProjectRoots(workspaceRoot, relStatePath)[0]?.root;
}

/**
 * An absolute path for a path the index or the page names, inside the selected project. Absolute
 * paths and `..` segments are refused (undefined).
 */
export function resolveInProject(projectRoot: string, rel: string): string | undefined {
  if (!rel || rel.startsWith('/') || rel.startsWith('\\') || /^[a-zA-Z]:/.test(rel)) return undefined;
  const parts = rel.split(/[\\/]/).filter(Boolean);
  if (!parts.length || parts.some((seg) => seg === '..')) return undefined;
  return path.join(projectRoot, ...parts);
}

/**
 * Freshness: every file the index cites is compared by modification time against `generated_at`.
 * Re-hashing would be a second implementation of the builder's rule; mtimes fail in the safe
 * direction — "possibly stale" when nothing meaningful changed, never silent when something did.
 */
function findStaleFiles(projectRoot: string, state: EvalState): string[] {
  const generatedAt = Date.parse(state.generated_at);
  if (!Number.isFinite(generatedAt)) return [];
  const refs = new Set<string>();
  if (state.system_card?.path) refs.add(state.system_card.path);
  for (const f of state.failure_modes) refs.add(f.path);
  for (const d of state.datasets) refs.add(d.path);
  for (const j of state.judges) {
    refs.add(j.path);
    if (j.validation) refs.add(j.validation);
  }
  for (const s of state.suites) {
    refs.add(s.path);
    if (s.latest_run?.summary) refs.add(s.latest_run.summary);
  }
  for (const c of state.scorecards) refs.add(c.path);
  const stale: string[] = [];
  for (const rel of refs) {
    const abs = resolveInProject(projectRoot, rel);
    if (!abs) continue;
    try {
      if (fs.statSync(abs).mtimeMs > generatedAt + 1000) stale.push(rel);
    } catch {
      stale.push(rel);
    }
  }
  return stale.sort();
}

// ---- the installer's files ------------------------------------------------------------------------

export type UpdateKind = 'patch' | 'minor' | 'major' | 'none' | 'unknown';

export interface UpdateNotice {
  installed: string | null;
  latest: string | null;
  kind: UpdateKind;
  command: string;
  changelogUrl: string | null;
}

const SEMVER = /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]{1,40})?$/;

/**
 * `.claude/.agentic-fx-updates.json`, written by the installer (`afx` or `npx agentic-fx`) and never by this extension:
 * `{checked_at, bundles: {eval: {installed, latest, kind, command, changelog_url}}}`. Anything
 * unreadable or not version-shaped is null, and the board shows a plain pill.
 */
export function parseUpdateNotice(text: string, bundle = 'eval'): UpdateNotice | null {
  let j: unknown;
  try {
    j = JSON.parse(text);
  } catch {
    return null;
  }
  const rec = (v: unknown): Record<string, unknown> | null => (isRecord(v) ? v : null);
  const b = rec(rec(rec(j)?.bundles)?.[bundle]);
  if (!b) return null;
  const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v.trim() : null);
  const kinds: UpdateKind[] = ['patch', 'minor', 'major', 'none', 'unknown'];
  const kind = kinds.includes(b.kind as UpdateKind) ? (b.kind as UpdateKind) : 'unknown';
  const latest = str(b.latest);
  const installed = str(b.installed);
  const url = str(b.changelog_url);
  // The command is one of two fixed ones, by the installer that wrote the notice (`npm:` = the public
  // npx package): a notice file is data, and data never picks what runs.
  return {
    installed: installed && SEMVER.test(installed) ? installed : null,
    latest: latest && SEMVER.test(latest) ? latest : null,
    kind,
    command: str(b.source)?.startsWith('npm:') ? `npx agentic-fx@latest update --bundle ${bundle}` : `afx update --bundle ${bundle}`,
    changelogUrl: url && /^https:\/\/[^\s<>"'`]{1,300}$/.test(url) ? url : null,
  };
}

/** The installed bundle version from the install manifest's `eval` entry, or null. */
export function parseManifestVersion(text: string, bundle = 'eval'): string | null {
  try {
    const j = JSON.parse(text) as Record<string, { version?: unknown }>;
    const v = j?.[bundle]?.version;
    return typeof v === 'string' && v ? v : null;
  } catch {
    return null;
  }
}

export interface InstallInfo {
  bundle: string | null;
  update: UpdateNotice | null;
}

/** Read the two installer files of a project. Missing files mean "not installed by afx". */
export function readInstallInfo(projectRoot: string): InstallInfo {
  const read = (rel: string): string | null => {
    try {
      return fs.readFileSync(path.join(projectRoot, rel), 'utf8');
    } catch {
      return null;
    }
  };
  const manifest = read('.claude/.agentic-fx.json');
  const notice = process.env.AFX_NO_UPDATE_CHECK === '1' ? null : read('.claude/.agentic-fx-updates.json');
  return {
    bundle: manifest ? parseManifestVersion(manifest) : null,
    update: notice ? parseUpdateNotice(notice) : null,
  };
}
