// @ts-check
/**
 * The Agents tab, shared verbatim by the sdlc, stlc and ai-eval boards: each Claude Code chat is a
 * room, agents that worked together sit at one round table, and each agent is a figure with a name.
 *
 * The webview's Content-Security-Policy forbids inline `style` attributes, so nothing here sets
 * one: positions and per-agent colours are SVG attributes, everything else is a class in
 * agents.css. Every class and data attribute is prefixed `ag-`, so the board's own click handler
 * and stylesheet never see them.
 *
 * The board owns the page and the vscode API. It calls `AgentsView.init(api, onCount)` once,
 * `mount(el)` after each redraw (an element, or null when the tab is not shown), and the host
 * posts `{command: 'agents', snapshot, titles}` whenever it has read the transcripts.
 */
(function (root) {
  /** @type {any} */
  let vscode = null;
  /** @type {any} */
  let data = null;
  /** @type {HTMLElement | null} */
  let mountEl = null;
  let watching = false;
  /** @type {((running: number | null) => void) | null} */
  let onCount = null;
  /** @type {{open?: string, showDone: boolean, collapsed: string[]}} */
  const ui = { open: undefined, showDone: false, collapsed: [] };

  const esc = (v) =>
    String(v ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');

  function ago(at) {
    if (!at) return '';
    const s = Math.max(0, Math.round((Date.now() - at) / 1000));
    if (s < 60) return `${s}s ago`;
    const m = Math.round(s / 60);
    if (m < 60) return `${m} min ago`;
    const h = Math.round(m / 60);
    if (h < 48) return `${h} h ago`;
    return `${Math.round(h / 24)} d ago`;
  }
  const when = (at) => `<span class="ag-when" data-ag-at="${Number(at) || 0}">${esc(ago(at))}</span>`;

  const STATUS = {
    running: ['Working', 'ag-run', '●'],
    quiet: ['Idle', 'ag-quiet', '◐'],
    done: ['Done', 'ag-done', '✓'],
    stopped: ['Stopped', 'ag-stop', '■'],
  };
  const look = (s) => STATUS[s] ?? STATUS.stopped;
  const live = (a) => a.status === 'running' || a.status === 'quiet';
  const MAX_SEATS = 10;

  /** A hue per id, so the same person keeps the same shirt across redraws. */
  function hue(id) {
    let h = 0;
    for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
    return h % 360;
  }

  /** Head, shoulders and a status badge in a 48-unit box, as SVG children. `lead` adds a headset. */
  function person(id, status, lead) {
    const h = hue(id);
    const [, cls, glyph] = look(status);
    return `<g class="ag-fig ${cls}">
      <circle class="ag-halo" cx="24" cy="24" r="22" />
      <path d="M9 45c0-9 6.7-14.5 15-14.5S39 36 39 45z" fill="hsl(${h} 55% 52%)" />
      <circle cx="24" cy="18" r="8.5" fill="hsl(${h} 32% 80%)" />
      <circle cx="21" cy="18" r="1.1" fill="#2a2a2a" /><circle cx="27" cy="18" r="1.1" fill="#2a2a2a" />
      ${lead ? '<path class="ag-set" d="M14.5 18a9.5 9.5 0 0 1 19 0" fill="none" /><rect class="ag-set-ear" x="13" y="16.5" width="3" height="5" rx="1.2" /><rect class="ag-set-ear" x="32" y="16.5" width="3" height="5" rx="1.2" />' : ''}
      <circle class="ag-badge" cx="40" cy="40" r="7" />
      <text class="ag-badge-t" x="40" y="40" dy="0.35em" text-anchor="middle">${glyph}</text>
    </g>`;
  }

  function figure(id, status, lead, size = 40) {
    return `<svg class="ag-figure" viewBox="0 0 48 48" width="${size}" height="${size}" aria-hidden="true">${person(id, status, lead)}</svg>`;
  }

  function chips(items, max) {
    if (!items || !items.length) return '';
    const titles = (data && data.titles) || {};
    return `<span class="ag-items">${items
      .slice(0, max)
      .map((i) => `<span class="ag-chip" title="${esc(titles[i] || i)}">${esc(i)}</span>`)
      .join('')}${items.length > max ? `<span class="ag-chip ag-more">+${items.length - max}</span>` : ''}</span>`;
  }

  function card(a) {
    const [word, cls] = look(a.status);
    const x = a.actions && a.actions[a.actions.length - 1];
    return `<li class="ag-card ${cls} ${ui.open === a.id ? 'ag-open' : ''}" data-ag-agent="${esc(a.id)}" tabindex="0" title="${esc(a.description)}">
      ${figure(a.id, a.status, false, 40)}
      <div class="ag-card-body">
        <div class="ag-who"><span class="ag-name">${esc(a.name)}</span><span class="ag-state ${cls}">${word}</span>${when(a.lastAt)}</div>
        <div class="ag-what">${esc(a.description)}</div>
        ${chips(a.items, 4)}
        ${x && live(a) ? `<div class="ag-act"><b>${esc(x.tool)}</b> ${esc(x.target)}</div>` : ''}
      </div>
    </li>`;
  }

  function detail(a) {
    const rows = (a.actions || [])
      .slice()
      .reverse()
      .map((x) => `<li><span class="ag-t">${esc(x.tool)}</span><span class="ag-g">${esc(x.target)}</span>${when(x.at)}</li>`)
      .join('');
    return `<li class="ag-detail" role="region" aria-label="${esc(a.name)}">
      <div class="ag-d-head">${figure(a.id, a.status, false, 40)}
        <div class="ag-grow"><strong>${esc(a.name)}</strong> <span class="ag-muted">· ${esc(a.role)} · agent ${esc(a.id.slice(0, 8))}</span>
        <div class="ag-muted ag-path">${esc(a.where)}${a.branch ? ` · ⎇ ${esc(a.branch)}` : ''}</div></div>
        <button class="ag-x" data-ag-close aria-label="Close">✕</button></div>
      <h4>Asked to</h4><pre class="ag-prompt">${esc(a.prompt)}</pre>
      ${rows ? `<h4>Last steps</h4><ul class="ag-steps">${rows}</ul>` : ''}
      <button class="ag-btn" data-ag-transcript="${esc(a.file)}">Open transcript</button>
    </li>`;
  }

  /**
   * A round table seen from above, all in one SVG so it scales with the column. Up to ten seats:
   * agents still working first, then the most recent. A dashed line joins an agent to the one that
   * spawned it; the work items more than one of them named are written on the table.
   */
  function roundTable(t, list, n) {
    const seated = [...list].sort((a, b) => Number(live(b)) - Number(live(a)) || b.lastAt - a.lastAt).slice(0, MAX_SEATS);
    const extra = list.length - seated.length;
    const N = seated.length;
    const R = Math.max(72, 30 + N * 11);
    const size = 2 * (R + 44);
    const c = size / 2;
    const top = Math.max(48, R - 32);
    const seat = new Map();
    seated.forEach((a, k) => {
      const ang = -Math.PI / 2 + (2 * Math.PI * k) / Math.max(1, N);
      seat.set(a.id, [c + R * Math.cos(ang), c + R * Math.sin(ang)]);
    });
    const links = seated
      .filter((a) => a.parentId && seat.has(a.parentId))
      .map((a) => {
        const [x1, y1] = seat.get(a.parentId);
        const [x2, y2] = seat.get(a.id);
        return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" />`;
      })
      .join('');
    const [word, cls] = look(t.status);
    const lines = [`<tspan class="ag-tt" x="${c}" dy="0">Table ${n}</tspan>`, `<tspan class="ag-state ${cls}" x="${c}" dy="1.35em">${word}</tspan>`, `<tspan class="ag-tm" x="${c}" dy="1.3em">${list.length} agent${list.length === 1 ? '' : 's'}</tspan>`];
    for (const i of t.shared.slice(0, top > 60 ? 3 : 1)) lines.push(`<tspan class="ag-ti" x="${c}" dy="1.35em">${esc(i)}</tspan>`);
    const labelY = c - (lines.length - 1) * 8;
    const seats = seated
      .map((a) => {
        const [x, y] = seat.get(a.id);
        const [, acls] = look(a.status);
        const w = a.name.length * 6.6 + 14;
        return `<g class="ag-seat ${acls} ${ui.open === a.id ? 'ag-open' : ''}" data-ag-agent="${esc(a.id)}" tabindex="0" role="button" aria-label="${esc(`${a.name}, ${look(a.status)[0]}: ${a.description}`)}">
          <title>${esc(`${a.name} — ${a.description}`)}</title>
          <g transform="translate(${(x - 20).toFixed(1)} ${(y - 26).toFixed(1)}) scale(0.84)">${person(a.id, a.status, false)}</g>
          <rect class="ag-tag" x="${(x - w / 2).toFixed(1)}" y="${(y + 15).toFixed(1)}" width="${w.toFixed(1)}" height="17" rx="8.5" />
          <text class="ag-tag-t" x="${x.toFixed(1)}" y="${(y + 23.5).toFixed(1)}" dy="0.35em" text-anchor="middle">${esc(a.name)}</text>
        </g>`;
      })
      .join('');
    return `<svg class="ag-table ${cls}" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="group" aria-label="Table ${n}: ${list.length} agents, ${word}">
      <circle class="ag-top" cx="${c}" cy="${c}" r="${top}" />
      <g class="ag-links">${links}</g>
      <text class="ag-label" x="${c}" y="${labelY}" text-anchor="middle">${lines.join('')}</text>
      ${seats}
      ${extra ? `<text class="ag-tm" x="${c}" y="${size - 6}" text-anchor="middle">+${extra} more at this table</text>` : ''}
    </svg>`;
  }

  function room(s) {
    const byId = new Map(s.agents.map((a) => [a.id, a]));
    let n = 0;
    return (s.tables || [])
      .map((t) => {
        n++;
        const list = t.agentIds.map((id) => byId.get(id)).filter(Boolean);
        const shown = ui.showDone ? list : list.filter(live);
        if (!shown.length) return '';
        const cards = shown
          .sort((a, b) => Number(live(b)) - Number(live(a)) || b.lastAt - a.lastAt)
          .map((a) => card(a) + (ui.open === a.id ? detail(a) : ''))
          .join('');
        return `<div class="ag-group">${roundTable(t, list, n)}<ul class="ag-crew">${cards}</ul></div>`;
      })
      .join('');
  }

  function session(s) {
    const hidden = ui.showDone ? 0 : s.agents.filter((a) => !live(a)).length;
    const running = s.agents.filter((a) => a.status === 'running').length;
    const collapsed = ui.collapsed.includes(s.id);
    const [word, cls] = look(s.status);
    const nTables = (s.tables || []).length;
    const last = s.actions.length ? s.actions[s.actions.length - 1] : null;
    const body = s.agents.length ? room(s) : `<p class="ag-muted ag-pad">Working alone, no agents spawned.${last ? ` Last: ${esc(last.tool)} ${esc(last.target)}` : ''}</p>`;
    return `<section class="ag-room ${cls}">
      <header class="ag-room-head" data-ag-toggle="${esc(s.id)}" tabindex="0" role="button" aria-expanded="${!collapsed}">
        ${figure(s.id, s.status, true, 40)}
        <div class="ag-grow"><div class="ag-room-title">${esc(s.title)}</div>
        <div class="ag-muted"><span class="ag-state ${cls}">${word}</span> · chat ${esc(s.id.slice(0, 8))} · ${s.agents.length} agent${s.agents.length === 1 ? '' : 's'}${nTables > 1 ? ` at ${nTables} tables` : ''}${running ? ` · <b>${running} working</b>` : ''} · ${when(s.lastAt)}</div></div>
        <span class="ag-chev" aria-hidden="true">${collapsed ? '▸' : '▾'}</span>
      </header>
      ${collapsed ? '' : `${body}${hidden ? `<button class="ag-link" data-ag-showdone>Show ${hidden} finished</button>` : ''}`}
    </section>`;
  }

  function html() {
    if (!data) return `<div class="ag-none">${figure('none', 'quiet', false, 48)}<p>Reading Claude Code transcripts…</p></div>`;
    const snap = data.snapshot;
    if (!snap.ok) return `<div class="ag-none">${figure('none', 'stopped', false, 48)}<p>${esc(snap.reason || 'Nothing to show.')}</p></div>`;
    const c = snap.counts;
    const sessions = ui.showDone ? snap.sessions : snap.sessions.filter((s) => s.status !== 'stopped' || s.agents.some(live));
    const older = snap.sessions.length - sessions.length;
    return `<div class="ag-bar">
        <span class="ag-tally"><span class="ag-run">● ${c.running} working</span><span class="ag-quiet">◐ ${c.quiet} idle</span><span class="ag-done">✓ ${c.done} done</span></span>
        <label class="ag-toggle"><input type="checkbox" data-ag-showdone ${ui.showDone ? 'checked' : ''}/> Show finished${older ? ` (+${older} chat${older === 1 ? '' : 's'})` : ''}</label>
      </div>
      <p class="ag-hint ag-muted">Claude Code chats on this project in the last 24 h. Agents that ran at the same time sit at one table.</p>
      ${sessions.length ? sessions.map(session).join('') : `<div class="ag-none">${figure('none', 'stopped', false, 48)}<p>No agent is working on this project right now.</p></div>`}`;
  }

  function render() {
    if (!mountEl || !mountEl.isConnected) return;
    if (!mountEl.classList.contains('ag')) mountEl.classList.add('ag');
    mountEl.innerHTML = html();
  }

  function running() {
    return data && data.snapshot && data.snapshot.ok ? data.snapshot.counts.running : null;
  }

  function setWatch(on) {
    if (on === watching || !vscode) return;
    watching = on;
    vscode.postMessage({ command: 'agents:watch', on });
  }

  setInterval(() => {
    for (const el of document.querySelectorAll('[data-ag-at]')) {
      const t = ago(Number(el.getAttribute('data-ag-at')));
      if (el.textContent !== t) el.textContent = t;
    }
  }, 1000);

  document.addEventListener('click', (e) => {
    const el = /** @type {Element} */ (e.target);
    if (!el || !el.closest || !el.closest('.ag')) return;
    const tr = el.closest('[data-ag-transcript]');
    if (tr) return vscode && vscode.postMessage({ command: 'agents:transcript', path: tr.getAttribute('data-ag-transcript') });
    if (el.closest('[data-ag-close]')) {
      ui.open = undefined;
      return render();
    }
    if (el.closest('[data-ag-showdone]')) {
      ui.showDone = !ui.showDone;
      return render();
    }
    const agent = el.closest('[data-ag-agent]');
    if (agent) {
      const id = agent.getAttribute('data-ag-agent') ?? undefined;
      ui.open = ui.open === id ? undefined : id;
      return render();
    }
    const toggle = el.closest('[data-ag-toggle]');
    if (toggle) {
      const id = toggle.getAttribute('data-ag-toggle') ?? '';
      ui.collapsed = ui.collapsed.includes(id) ? ui.collapsed.filter((x) => x !== id) : [...ui.collapsed, id];
      render();
    }
  });
  document.addEventListener('keydown', (e) => {
    const el = /** @type {Element} */ (e.target);
    if (!el || !el.closest || !el.closest('.ag')) return;
    if ((e.key === 'Enter' || e.key === ' ') && el.matches('[data-ag-agent], [data-ag-toggle]')) {
      e.preventDefault();
      /** @type {any} */ (el).dispatchEvent(new MouseEvent('click', { bubbles: true }));
    }
    if (e.key === 'Escape' && ui.open) {
      ui.open = undefined;
      render();
    }
  });

  window.addEventListener('message', (e) => {
    if (!e.data || e.data.command !== 'agents') return;
    data = e.data;
    if (onCount) onCount(running());
    render();
  });

  root.AgentsView = {
    /** The board's vscode API (it can be acquired only once per page) and a badge callback. */
    init(api, count) {
      vscode = api;
      onCount = count || null;
    },
    /** Draw into `el`, or stop drawing when it is null. The host polls faster while one is shown. */
    mount(el) {
      mountEl = el || null;
      setWatch(!!mountEl);
      render();
    },
    running,
  };
})(/** @type {any} */ (window));
