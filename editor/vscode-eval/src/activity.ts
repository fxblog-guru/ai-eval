/**
 * The shared activity format (docs/activity-format.md): parse `<root>/logs/activity.jsonl` and work
 * out what still needs a human.
 *
 * vscode-sdlc, vscode-stlc and vscode-qa-standup carry a copy of this file, by convention, so each
 * addon stays standalone. ai-eval writes the log from workspace/evals/scripts/shared/activity.py.
 * `activity.test.ts` in each checks the same cases; change all four together.
 * This file must not import `vscode`.
 */

export const KINDS = ['gate', 'decision', 'run', 'stop', 'finding', 'heal', 'lesson', 'score'] as const;
export const OUTCOMES = ['pass', 'fail', 'changes', 'blocked', 'stale', 'stopped', 'info'] as const;
export const NEEDS = ['approve-ui', 'confirm-dec', 'sign-off', 'push', 'merge', 'answer-dec', 'review-stop'] as const;

export type EventKind = (typeof KINDS)[number];
export type Outcome = (typeof OUTCOMES)[number];
export type Need = (typeof NEEDS)[number];

export interface ActivityEvent {
  v: 1;
  at: string;
  source: 'sdlc' | 'stlc' | 'eval';
  kind: EventKind;
  slug: string | null;
  outcome: Outcome;
  title: string;
  link?: string | null;
  run_id?: string | null;
  needs?: Need | null;
}

const AT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;

export function isEvent(e: unknown): e is ActivityEvent {
  if (!e || typeof e !== 'object') return false;
  const o = e as Record<string, unknown>;
  return (
    o.v === 1 &&
    typeof o.at === 'string' && AT.test(o.at) &&
    (o.source === 'sdlc' || o.source === 'stlc' || o.source === 'eval') &&
    (KINDS as readonly string[]).includes(o.kind as string) &&
    (o.slug === null || typeof o.slug === 'string') &&
    (OUTCOMES as readonly string[]).includes(o.outcome as string) &&
    typeof o.title === 'string' && o.title.length > 0 && o.title.length <= 120 &&
    (o.needs == null || (NEEDS as readonly string[]).includes(o.needs as string))
  );
}

/** Valid events, newest first. A torn or foreign line is skipped, never fatal. */
export function parseActivity(text: string): ActivityEvent[] {
  const out: ActivityEvent[] = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try {
      const e: unknown = JSON.parse(line);
      if (isEvent(e)) out.push(e);
    } catch {
      /* a line cut short by a crash */
    }
  }
  return out.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}

export interface NeedItem {
  need: Need;
  slug: string | null;
  title: string;
  at: string;
  link: string | null;
}

/**
 * What still needs a human: each (slug, need, link) whose newest event asks for it. A later event
 * for the same key with `outcome: pass` and no `needs` clears it. `events` is newest first.
 */
export function openNeeds(events: ActivityEvent[]): NeedItem[] {
  const decided = new Set<string>();
  const out: NeedItem[] = [];
  for (const e of events) {
    const keyOf = (need: string) => `${e.slug ?? ''}|${need}|${e.link ?? ''}`;
    if (!e.needs) {
      if (e.outcome === 'pass') for (const n of NEEDS) decided.add(keyOf(n));
      continue;
    }
    const key = keyOf(e.needs);
    if (decided.has(key)) continue;
    decided.add(key);
    out.push({ need: e.needs, slug: e.slug, title: e.title, at: e.at, link: e.link ?? null });
  }
  return out;
}

/** A person-readable label for each need, shown beside the item. */
export const NEED_LABEL: Record<Need, string> = {
  'approve-ui': 'Approve the UI',
  'confirm-dec': 'Confirm an assumed decision',
  'sign-off': 'Sign off',
  push: 'Push',
  merge: 'Merge',
  'answer-dec': 'Answer a decision',
  'review-stop': 'Review a stopped run',
};
