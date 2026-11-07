// @ts-check
/**
 * The page: it draws the view model the host posts and sends back what the reader clicked.
 * It decides nothing — every verdict, tone and sentence arrives in the view model.
 * Text is always set with textContent; the page never builds HTML from data.
 */
(function () {
  // @ts-ignore — provided by the webview runtime
  const vscode = acquireVsCodeApi();
  const app = /** @type {HTMLElement} */ (document.getElementById('app'));
  const sidebar = document.body.dataset.layout === 'sidebar';

  /**
   * @param {string} tag
   * @param {Record<string, any>} [attrs]
   * @param {(Node|string|null|undefined|false)[]} [kids]
   */
  function h(tag, attrs, kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'onclick') el.addEventListener('click', v);
      else el.setAttribute(k, String(v));
    }
    for (const kid of kids || []) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(typeof kid === 'string' ? document.createTextNode(kid) : kid);
    }
    return el;
  }
  const ICON = { ok: '✓', bad: '✗', warn: '!', muted: '·', accent: '●' };
  const pill = (tone, text) => h('span', { class: `pill ${tone}` }, [`${ICON[tone] || ''} ${text}`]);
  const open = (path, text) => (path ? h('button', { class: 'link', title: path, onclick: () => vscode.postMessage({ command: 'open', path }) }, [text]) : h('span', {}, [text]));
  const copy = (text) => h('button', { class: 'btn', title: 'Copy to the clipboard', onclick: () => vscode.postMessage({ command: 'copy', text }) }, ['Copy']);

  function header(vm, project) {
    const kids = [
      h('div', { class: 'logo', 'aria-hidden': 'true' }, ['AI']),
      h('div', {}, [h('h1', {}, [project ? `${vm.project} — ${project}` : vm.project]), h('div', { class: 'sub' }, [`risk tier ${vm.tier || '?'} · phase ${vm.phase}`])]),
      h('div', { class: 'spacer' }),
    ];
    if (vm.version.update) {
      kids.push(h('span', { class: 'pill update', role: 'button', tabindex: '0', title: vm.version.update.command, onclick: () => vscode.postMessage({ command: 'update' }) }, [`↑ ${vm.version.update.label}`]));
    } else if (vm.version.bundle) kids.push(pill('muted', `ai-eval ${vm.version.bundle}`));
    if (sidebar) kids.push(h('button', { class: 'btn', onclick: () => vscode.postMessage({ command: 'openBoard' }) }, ['Open board']));
    else kids.push(h('button', { class: 'btn', onclick: () => vscode.postMessage({ command: 'lint' }) }, ['Lint…']));
    return h('header', { class: 'top' }, kids);
  }

  function stepper(vm) {
    return h(
      'div',
      { class: 'stepper', role: 'list', 'aria-label': 'Pipeline' },
      vm.steps.map((s, i) => h('div', { class: `step ${s.state}`, role: 'listitem', 'aria-current': s.state === 'current' ? 'step' : null }, [h('span', { class: 'n' }, [String(i + 1)]), s.label])),
    );
  }

  function next(vm) {
    if (!vm.nextCommand) return null;
    return h('div', { class: 'next' }, [h('span', { class: 'label' }, ['Next in Claude Code']), h('code', {}, [vm.nextCommand]), h('div', { class: 'spacer' }), copy(vm.nextCommand)]);
  }

  function warnings(vm) {
    if (!vm.warnings.length) return null;
    return h('ul', { class: 'warnings' }, vm.warnings.map((w) => h('li', { class: w.tone }, [w.path ? open(w.path, w.text) : w.text])));
  }

  function kpis(vm) {
    return h('div', { class: 'kpis' }, vm.kpis.map((k) => h('div', { class: `kpi ${k.tone}`, title: k.hint }, [h('div', { class: 'v' }, [k.value]), h('div', { class: 'l' }, [k.label])])));
  }

  function layers(vm) {
    return h(
      'div',
      { class: 'layers' },
      vm.layers.map((l) =>
        h('div', { class: `layer ${l.verdict === 'OFF' ? 'off' : l.tone}`, title: `${l.layer}: ${l.suites} suite(s)${l.enabled === false ? ' · disabled in EVAL-PROFILE' : ''}` }, [
          h('b', {}, [l.layer]),
          `${ICON[l.tone] || ''} ${l.verdict}`,
        ]),
      ),
    );
  }

  function suites(vm) {
    if (!vm.suites.length) return h('p', { class: 'none' }, ['No suites yet — /eval-data builds a dataset, /eval-judge binds evaluators.']);
    const arrow = { up: '↑', down: '↓', same: '→' };
    return h('table', { class: 'suites' }, [
      h('thead', {}, [h('tr', {}, [h('th', {}, ['Suite']), h('th', {}, ['Layer']), h('th', {}, ['Verdict']), h('th', { class: 'page-only' }, ['pass^k (95% CI)']), h('th', { class: 'page-only' }, ['Why']), h('th', { class: 'page-only' }, [''])])]),
      h(
        'tbody',
        {},
        vm.suites.map((s) =>
          h('tr', {}, [
            h('td', {}, [open(s.path, s.suite)]),
            h('td', {}, [s.layer]),
            h('td', {}, [pill(s.tone, s.verdict), s.gated ? null : h('span', { class: 'trend' }, [' ungated'])]),
            h('td', { class: 'page-only mono' }, [s.passK ? open(s.summary, s.passK) : '—', s.trend ? h('span', { class: 'trend' }, [` ${arrow[s.trend]}`]) : null]),
            h('td', { class: 'page-only why' }, [s.why]),
            h('td', { class: 'page-only' }, [h('button', { class: 'btn', title: 'Dry run: no model calls', onclick: () => vscode.postMessage({ command: 'runSuite', suite: s.suite, dryRun: true }) }, ['Dry-run…'])]),
          ]),
        ),
      ),
    ]);
  }

  function list(title, items, empty) {
    return h('div', {}, [
      h('h2', { class: 'section' }, [`${title} (${items.length})`]),
      items.length
        ? h('ul', { class: 'items' }, items.map((i) => h('li', {}, [h('span', {}, [ICON[i.tone] || '·']), open(i.path, i.id), h('span', { class: 'd', title: `${i.label} · ${i.detail}` }, [`${i.label} · ${i.detail}`])])))
        : h('p', { class: 'none' }, [empty]),
    ]);
  }

  // ---- the five views over the activity log ---------------------------------------------------
  const saved = vscode.getState() || {};
  const ui = { tab: saved.tab || 'summary', kind: saved.kind || 'all', view: saved.view || 'board' };
  /** Whether the host feeds the Agents tab (agents.js), and how many agents are working now. */
  let agentsOn = false;
  let agentsRunning = /** @type {number | null} */ (null);
  const AV = /** @type {any} */ (window).AgentsView;
  const countEl = () => h('span', { class: `n ag-count ${agentsRunning ? 'on' : ''}`, 'data-ag-count': '' }, [agentsRunning ? String(agentsRunning) : '']);
  if (AV)
    AV.init(vscode, (n) => {
      agentsRunning = n;
      for (const el of document.querySelectorAll('[data-ag-count]')) {
        el.textContent = n ? String(n) : '';
        el.classList.toggle('on', !!n);
      }
    });
  const agentsTab = () => agentsOn && !!AV;
  const agentsMount = () => h('div', { id: 'ag-mount' });
  /** Hand the Agents tab its element after a redraw, or tell it it is hidden. */
  const mountAgents = () => AV && AV.mount(document.getElementById('ag-mount'));
  /** The full board has two views: the eval pipeline, and who is working on it right now. */
  function viewSwitch() {
    if (!agentsTab()) return null;
    const b = (key, label, extra) => h('button', { class: `view-tab ${ui.view === key ? 'selected' : ''}`, role: 'tab', 'aria-selected': String(ui.view === key), onclick: () => setUi({ view: key }) }, [label, extra]);
    return h('nav', { class: 'view-tabs', role: 'tablist' }, [b('board', 'Board', null), b('agents', 'Agents', countEl())]);
  }
  let last = null;
  const setUi = (patch) => {
    Object.assign(ui, patch);
    vscode.setState(ui);
    if (last) render(last.vm, last.project);
  };
  const VS = { holding: ['ok', 'at or above baseline'], below: ['bad', 'below baseline'], 'no baseline': ['muted', 'no baseline'], untrusted: ['warn', 'judge not validated'], 'no run': ['muted', 'no run'] };
  const OUT = { pass: '✓', fail: '✗', changes: '!', blocked: '✗', stale: '↻', stopped: '■', info: '·' };
  const when = (at) => h('time', { class: 'when', datetime: at, title: at }, [String(at).slice(0, 16).replace('T', ' ')]);
  const section = (title, n) => h('h2', { class: 'section' }, [n == null ? title : `${title} (${n})`]);
  const emptyOk = (title, text) => h('div', { class: 'empty-ok' }, [h('span', { class: 'es', 'aria-hidden': 'true' }, ['✓']), h('div', {}, [h('strong', {}, [title]), h('p', {}, [text])])]);
  const row = (link, kids) => {
    if (!link) return h('li', {}, kids);
    const go = () => vscode.postMessage({ command: 'open', path: link });
    const li = h('li', { class: 'row-btn', role: 'button', tabindex: '0', title: link, onclick: go }, kids);
    li.addEventListener('keydown', (ev) => (ev.key === 'Enter' || ev.key === ' ') && (ev.preventDefault(), go()));
    return li;
  };

  function summary(vm) {
    const s = vm.summary;
    const at = s.atBaseline;
    const lr = s.latestRun;
    return h('div', {}, [
      section('Summary'),
      h('dl', { class: 'summary' }, [
        h('dt', {}, ['Evaluates']),
        h('dd', {}, [`${s.evaluates} · ${s.suites} suite(s)`]),
        h('dt', {}, ['Latest run']),
        h('dd', {}, lr ? [open(lr.path, `${lr.suite} ${lr.runId}`), ' ', pill(lr.tone, lr.verdict)] : [h('span', { class: 'muted' }, ['none yet'])]),
        h('dt', {}, ['Baseline']),
        h('dd', {}, [at.percent === null ? h('span', { class: 'muted' }, ['no layer has a baseline to compare']) : `${at.percent}% of layers at or above · ${at.held} of ${at.compared}`]),
        h('dt', {}, ['Next']),
        h('dd', {}, s.next ? [h('code', {}, [s.next]), ' ', copy(s.next)] : ['—']),
      ]),
      s.layers.length
        ? h(
            'ul',
            { class: 'layer-scores' },
            s.layers.map((l) => {
              const [tone, label] = VS[l.vsBaseline] || VS['no run'];
              return h('li', { class: tone }, [h('b', {}, [l.layer]), pill(l.tone, l.verdict), h('span', { class: `vs ${tone}` }, [`${ICON[tone] || ''} ${label}`]), h('span', { class: 'scores' }, [l.scores.join(' · ')])]);
            }),
          )
        : h('p', { class: 'none' }, ['No suites yet.']),
    ]);
  }

  function activity(vm, limit) {
    const kinds = [...new Set(vm.activity.map((e) => e.kind))].sort();
    const kind = kinds.includes(ui.kind) ? ui.kind : 'all';
    const items = vm.activity.filter((e) => kind === 'all' || e.kind === kind).slice(0, limit);
    const chip = (k) => h('button', { class: `chip ${k === kind ? 'selected' : ''}`, 'aria-pressed': String(k === kind), onclick: () => setUi({ kind: k }) }, [k]);
    return h('div', {}, [
      section('Activity', vm.activity.length),
      kinds.length > 1 ? h('div', { class: 'chips', role: 'group', 'aria-label': 'Filter by kind' }, ['all', ...kinds].map(chip)) : null,
      items.length
        ? h('ul', { class: 'feed' }, items.map((e) => row(e.link, [h('span', { class: `o ${e.tone}`, 'aria-label': e.outcome }, [OUT[e.outcome] || '·']), h('span', { class: 'k' }, [e.kind]), h('span', { class: 'grow' }, [e.title]), when(e.at)])))
        : h('p', { class: 'none' }, ['Nothing logged yet. A run writes its run, score and regression events to logs/activity.jsonl.']),
    ]);
  }

  function decisions(vm) {
    return h('div', {}, [section('Decisions', vm.decisions.length), emptyOk('No decisions', 'ai-eval keeps no decision ledger. Questions about scope live in the system card.')]);
  }

  function findings(vm) {
    if (!vm.findings.length) return h('div', {}, [section('Findings', 0), emptyOk('No regressions', 'A run that drops past its baseline margin is listed here, worst first.')]);
    return h('div', {}, [
      section('Findings', vm.findings.length),
      h(
        'ul',
        { class: 'feed findings' },
        vm.findings.map((f) =>
          row(f.link, [
            h('span', { class: `sev sev-${f.severity}` }, [f.severity]),
            h('span', { class: 'grow' }, [h('b', {}, [`${f.what === 'total' ? 'total score' : f.what} · ${f.suite}`]), h('span', { class: 'sub muted' }, [`${f.base}% → ${f.now}% vs baseline`])]),
            h('span', { class: 'side' }, [h('span', { class: 'drop' }, [`−${f.drop} pts`]), when(f.at)]),
          ]),
        ),
      ),
    ]);
  }

  function needs(vm) {
    if (!vm.needsYou.length) return h('div', {}, [section('Needs you', 0), emptyOk('Nothing waits on you', 'Sign-offs and stopped runs that the log asks a person for appear here.')]);
    return h('div', {}, [section('Needs you', vm.needsYou.length), h('ul', { class: 'feed needs' }, vm.needsYou.map((n) => row(n.link, [h('span', { class: 'tag' }, [n.label]), h('span', { class: 'grow' }, [n.title]), when(n.at)])))]);
  }

  function tabs(vm) {
    const t = (key, label, n) => h('button', { class: `vtab ${ui.tab === key ? 'selected' : ''}`, role: 'tab', 'aria-selected': String(ui.tab === key), onclick: () => setUi({ tab: key }) }, [label, n ? h('span', { class: 'n' }, [String(n)]) : null]);
    return h('nav', { class: 'vtabs', role: 'tablist' }, [t('summary', 'Summary'), t('activity', 'Activity'), t('decisions', 'Decisions'), t('findings', 'Findings', vm.findings.length), t('needs', 'Needs you', vm.needsYou.length), agentsTab() ? h('button', { class: `vtab ${ui.tab === 'agents' ? 'selected' : ''}`, role: 'tab', 'aria-selected': String(ui.tab === 'agents'), onclick: () => setUi({ tab: 'agents' }) }, ['Agents', countEl()]) : null]);
  }

  function footer(vm) {
    return h('footer', {}, [`index built ${vm.generatedAt}`, `board ${vm.version.board}`, `builder ${vm.version.builder}`, vm.version.bundle ? `ai-eval ${vm.version.bundle}` : 'ai-eval not installed by afx'].map((t) => h('span', {}, [t])));
  }

  function render(vm, project) {
    last = { vm, project };
    app.className = '';
    app.replaceChildren();
    if (!vm.ok) {
      app.className = 'empty';
      app.append(h('h2', {}, [vm.reason]), vm.detail ? h('p', {}, [vm.detail]) : '');
      mountAgents();
      return;
    }
    if (sidebar) {
      let body;
      if (ui.tab === 'activity') body = [activity(vm, 40)];
      else if (ui.tab === 'decisions') body = [decisions(vm)];
      else if (ui.tab === 'findings') body = [findings(vm)];
      else if (ui.tab === 'needs') body = [needs(vm)];
      else if (ui.tab === 'agents' && agentsTab()) body = [agentsMount()];
      else body = [warnings(vm) || '', vm.needsYou.length ? needs(vm) : '', summary(vm), stepper(vm), h('h2', { class: 'section' }, ['Suites — latest run']), suites(vm)];
      app.append(header(vm, project), tabs(vm), ...body, footer(vm));
      mountAgents();
      return;
    }
    if (ui.view === 'agents' && agentsTab()) {
      app.append(header(vm, project), viewSwitch() || '', agentsMount());
      mountAgents();
      return;
    }
    app.append(
      header(vm, project),
      viewSwitch() || '',
      stepper(vm),
      next(vm) || '',
      warnings(vm) || '',
      needs(vm),
      summary(vm),
      kpis(vm),
      h('h2', { class: 'section' }, ['Layers']),
      layers(vm),
      h('h2', { class: 'section' }, ['Suites — latest run']),
      suites(vm),
      h('div', { class: 'cols' }, [findings(vm), activity(vm, 12)]),
      h('div', { class: 'cols' }, [
        list('Failure modes', vm.failureModes, 'None yet — /eval-explore reads real traces first.'),
        list('Judges', vm.judges, 'No LLM judges — code assertions only, nothing to calibrate.'),
        list('Datasets', vm.datasets, 'No dataset yet.'),
        list('Red-team probes', vm.probes, 'No probes.'),
        list('Scorecards', vm.scorecards, 'No scorecard yet — /eval-report.'),
        decisions(vm),
      ]),
      footer(vm),
    );
    mountAgents();
  }

  window.addEventListener('message', (ev) => {
    const msg = ev.data;
    if (msg && msg.command === 'tab' && msg.tab === 'agents') {
      if (sidebar) setUi({ tab: 'agents' });
      else setUi({ view: 'agents' });
      return;
    }
    if (!msg || msg.command !== 'state') return;
    if (msg.accent) document.body.dataset.accent = msg.accent;
    agentsOn = !!msg.agents;
    render(msg.vm, msg.project);
  });
  vscode.postMessage({ command: 'ready' });
})();
