/**
 * Activation, wiring, the watchers and the confirmed terminal commands. Nothing else belongs here.
 *
 * The extension is a viewer: it reads <root>/state.json (.evals/, or evals/ in an older project; built by build_state.py)
 * and the installer's two files in .claude/, renders them, and reopens the files they point at. It
 * never writes to the workspace. The only things it starts are VS Code terminals, each one after the
 * reader picked "Run" on a quick pick showing the exact command: a suite run or dry run, the linter,
 * or the installer's update (`afx update --bundle eval`, or `npx agentic-fx@latest update --bundle eval`).
 */

import * as cp from 'child_process';
import * as path from 'path';
import * as vscode from 'vscode';
import { AgentsFeed } from './agentsView';
import { BoardPanel, BoardSource, OverviewViewProvider } from './board';
import { readEvents } from './events';
import { LoadResult, ProjectRef, findProjectRoots, loadState, readInstallInfo, resolveInProject, resolveStatePath } from './model';
import { Throttle } from './throttle';
import { EvidenceTreeProvider, SuitesTreeProvider } from './tree';
import { BoardVM, buildViewModel, statusLine } from './viewmodel';

const SELECTED_KEY = 'evalBoard.selectedProject';
const DISMISSED_KEY = 'evalBoard.dismissedUpdate';

export function activate(context: vscode.ExtensionContext): void {
  const addonVersion = String(context.extension.packageJSON.version ?? '');
  const folders = vscode.workspace.workspaceFolders ?? [];
  const folder = folders[0];
  if (!folder) return;

  const config = (): vscode.WorkspaceConfiguration => vscode.workspace.getConfiguration('evalBoard');
  // Empty setting = follow the bundle's root order: .evals/state.json, else evals/state.json (EVAL-CONTRACTS §2).
  const relPath = (): string => resolveStatePath(folder.uri.fsPath, config().get<string>('statePath'));
  const evalRoot = (): string => path.posix.dirname(relPath().replace(/\\/g, '/')) || '.evals';
  const python = (): string => config().get<string>('python') || (process.platform === 'win32' ? 'python' : 'python3');

  let cached: LoadResult | undefined;
  let vmCache: BoardVM | undefined;
  let projects: ProjectRef[] | undefined;

  const listProjects = (): ProjectRef[] => {
    if (!projects) {
      const seen = new Set<string>();
      projects = folders
        .flatMap((f) => findProjectRoots(f.uri.fsPath, relPath()))
        .filter((p) => !seen.has(p.root) && !!seen.add(p.root))
        .sort((a, b) => b.mtime - a.mtime);
    }
    return projects;
  };
  const selected = (): string | undefined => {
    const pinned = context.workspaceState.get<string>(SELECTED_KEY);
    const all = listProjects();
    if (pinned && all.some((p) => p.root === pinned)) return pinned;
    return all[0]?.root;
  };
  const projectLabel = (root: string): string => {
    const owner = vscode.workspace.getWorkspaceFolder(vscode.Uri.file(root));
    if (!owner) return path.basename(root);
    const rel = path.relative(owner.uri.fsPath, root).split(path.sep).join('/');
    return folders.length > 1 ? (rel ? `${owner.name}/${rel}` : owner.name) : rel || owner.name;
  };
  const getState = (): LoadResult => {
    if (!cached) cached = loadState(folder.uri.fsPath, relPath(), selected());
    return cached;
  };
  const projectRoot = (): string => getState().projectRoot;
  const currentLabel = (): string | undefined => {
    const cur = selected();
    return cur && listProjects().length > 1 ? projectLabel(cur) : undefined;
  };
  const getVM = (): BoardVM => {
    if (!vmCache) {
      vmCache = buildViewModel(getState(), {
        events: readEvents(projectRoot(), evalRoot()),
        install: readInstallInfo(projectRoot()),
        addonVersion,
        dismissedUpdate: context.workspaceState.get<string>(DISMISSED_KEY) ?? null,
      });
    }
    return vmCache;
  };
  // Who is working on the project: Claude Code chats and the agents they spawned, read from their
  // transcripts (agents.ts) and drawn in the board's Agents tab.
  const agents = new AgentsFeed({ projectRoot });
  context.subscriptions.push(agents);
  const source: BoardSource = { agents, viewModel: getVM, accent: () => config().get<string>('accent') ?? 'coral', projectLabel: currentLabel };

  const suites = new SuitesTreeProvider(getVM);
  const evidence = new EvidenceTreeProvider(getVM);
  const overview = new OverviewViewProvider(context.extensionUri, source);
  context.subscriptions.push(vscode.window.registerWebviewViewProvider(OverviewViewProvider.viewType, overview));
  const suitesView = vscode.window.createTreeView('evalBoard.suites', { treeDataProvider: suites });
  const evidenceView = vscode.window.createTreeView('evalBoard.evidence', { treeDataProvider: evidence });
  context.subscriptions.push(suitesView, evidenceView);

  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 98);
  status.command = 'evalBoard.openBoard';
  context.subscriptions.push(status);

  const refresh = (stateChanged = true): void => {
    if (stateChanged) cached = undefined;
    vmCache = undefined;
    const label = currentLabel();
    suitesView.description = label;
    evidenceView.description = label;
    overview.setDescription(label);
    void vscode.commands.executeCommand('setContext', 'evalBoard.multiProject', listProjects().length > 1);
    suites.refresh();
    evidence.refresh();
    BoardPanel.refreshIfOpen();
    overview.refresh();
    if (stateChanged) agents.refresh();
    if (!listProjects().length || !(config().get<boolean>('showStatusBar') ?? true)) {
      status.hide();
      return;
    }
    const vm = getVM();
    const line = statusLine(vm);
    const icon = line.tone === 'bad' ? '$(error)' : line.tone === 'warn' ? '$(warning)' : '$(pulse)';
    status.text = `${icon} Eval${label ? ` · ${label}` : ''}: ${line.text}${vm.version.update ? ' $(arrow-circle-up)' : ''}`;
    status.tooltip = vm.ok
      ? `${vm.project} — phase ${vm.phase}${vm.nextCommand ? `\nnext: ${vm.nextCommand}` : ''}\nboard ${vm.version.board} · eval bundle ${vm.version.bundle ?? '?'} · builder ${vm.version.builder}`
      : `${vm.reason}${vm.detail ? `\n${vm.detail}` : ''}`;
    status.show();
  };

  // ---- watching: the index, the installer's files, and a new index appearing anywhere. No polling.
  let timer: NodeJS.Timeout | undefined;
  const soon = (stateChanged: boolean): void => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => refresh(stateChanged), 300);
  };
  context.subscriptions.push({ dispose: () => timer && clearTimeout(timer) });

  // ---- the optional background rebuild (as in vscode-sdlc) -----------------------------------------
  // Off by default, because it is the one path that writes to the workspace (build_state.py rewrites
  // state.json, as the bundle's Stop hook does). It covers a Claude session opened outside the
  // project, where the project's own Stop hook never runs. Throttled, and never two at once.
  const rebuild = new Throttle(
    () =>
      new Promise<void>((resolve) => {
        const cwd = projectRoot();
        const root = evalRoot();
        const script = path.join(cwd, root, 'scripts', 'shared', 'build_state.py');
        const env = { ...process.env };
        delete env.ELECTRON_RUN_AS_NODE;
        cp.execFile(python(), [script, '--root', root, '--quiet'], { cwd, env, timeout: 120_000, windowsHide: true }, () => resolve());
      }),
    Math.max(15, config().get<number>('backgroundRebuildSeconds') ?? 120) * 1000,
  );
  context.subscriptions.push({ dispose: () => rebuild.dispose() });
  /** What build_state.py reads: a change to one of these makes the index out of date. */
  const sourceDirs = ['taxonomy', 'datasets', 'judges', 'baselines', 'suites', 'runs', 'redteam', 'reports'];

  let watchers: vscode.Disposable[] = [];
  const rewatch = (): void => {
    for (const w of watchers) w.dispose();
    watchers = [];
    for (const f of folders) {
      const glob = `{${relPath()},**/${relPath()},${evalRoot()}/logs/activity.jsonl,**/${evalRoot()}/logs/activity.jsonl,.claude/.agentic-fx.json,.claude/.agentic-fx-updates.json,**/.claude/.agentic-fx-updates.json}`;
      const w = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(f, glob));
      const on = (uri: vscode.Uri): void => {
        const rel = vscode.workspace.asRelativePath(uri, false);
        if (rel.endsWith('state.json')) {
          if (rel.split(/[\\/]/).some((p) => p.startsWith('.'))) return;
          projects = undefined;
          soon(true);
        } else soon(false);
      };
      w.onDidChange(on);
      w.onDidCreate(on);
      w.onDidDelete(on);
      watchers.push(w);
      // The pipeline's own files: only the optional rebuild listens, the board redraws on state.json.
      const sources = vscode.workspace.createFileSystemWatcher(
        new vscode.RelativePattern(f, `{${evalRoot()},**/${evalRoot()}}/{${sourceDirs.join(',')}}/**`),
      );
      const onSource = (uri: vscode.Uri): void => {
        if (!config().get<boolean>('backgroundRebuild')) return;
        // A dot folder other than the eval root itself (`.evals`) holds copies, such as .claude/worktrees.
        const rel = vscode.workspace.asRelativePath(uri, false);
        if (rel.split(/[\\/]/).some((p) => p.startsWith('.') && p !== evalRoot())) return;
        rebuild.request();
      };
      sources.onDidChange(onSource);
      sources.onDidCreate(onSource);
      sources.onDidDelete(onSource);
      watchers.push(sources);
    }
  };
  rewatch();
  context.subscriptions.push({ dispose: () => watchers.forEach((w) => w.dispose()) });

  // ---- confirmed terminal commands ---------------------------------------------------------------
  const confirmAndRun = async (title: string, cwd: string, commandLine: string, detail: string): Promise<void> => {
    const choice = await vscode.window.showQuickPick(
      [
        { label: '$(terminal) Run in a terminal', description: commandLine, detail: `in ${cwd}`, run: true },
        { label: '$(copy) Copy the command', description: commandLine, run: false },
      ],
      { title, placeHolder: detail },
    );
    if (!choice) return;
    if (!choice.run) {
      await vscode.env.clipboard.writeText(commandLine);
      vscode.window.setStatusBarMessage(`Copied: ${commandLine}`, 2500);
      return;
    }
    // A terminal spawned from the extension host inherits ELECTRON_RUN_AS_NODE; clear it.
    const term = vscode.window.createTerminal({ name: title, cwd, env: { ELECTRON_RUN_AS_NODE: null } });
    term.show();
    term.sendText(commandLine, true);
  };

  const runSuite = async (arg: unknown, dryRun: boolean): Promise<void> => {
    let name = typeof arg === 'string' ? arg : (arg as { suite?: { suite?: string } } | undefined)?.suite?.suite;
    const vm = getVM();
    if (!name && vm.ok) {
      const pick = await vscode.window.showQuickPick(
        vm.suites.map((s) => ({ label: s.suite, description: `${s.layer} · ${s.verdict}`, detail: s.why })),
        { title: dryRun ? 'Eval: Dry-run a suite' : 'Eval: Run a suite' },
      );
      name = pick?.label;
    }
    if (!name || !/^[a-z0-9][a-z0-9-]*$/.test(name)) return;
    const root = evalRoot();
    const cmd = `${python()} ${root}/scripts/shared/runner.py --suite ${name} --root ${root}${dryRun ? ' --dry-run' : ''}`;
    await confirmAndRun(
      dryRun ? `Dry-run ${name}` : `Run ${name}`,
      projectRoot(),
      cmd,
      dryRun ? 'Prints the call count, dataset hash and whether the gate is evaluable; calls no model.' : 'Calls the model k times per case and writes a run folder. It costs tokens.',
    );
  };

  const lint = async (): Promise<void> => {
    const root = evalRoot();
    await confirmAndRun('Eval lint', projectRoot(), `${python()} ${root}/scripts/shared/lint_evals.py --root ${root}`, 'Checks the eval root against EVAL-CONTRACTS. Reads only.');
  };

  const bundleUpdate = async (): Promise<void> => {
    const vm = getVM();
    const u = vm.version.update;
    if (!u) {
      void vscode.window.showInformationMessage(`ai-eval ${vm.version.bundle ?? ''} — no update notice. The installer writes one when it checks (afx outdated).`);
      return;
    }
    type Pick = vscode.QuickPickItem & { action: 'changelog' | 'update' | 'dismiss' };
    const items: Pick[] = [
      ...(u.changelogUrl ? [{ label: '$(book) Open CHANGELOG', description: u.changelogUrl, action: 'changelog' as const }] : []),
      { label: '$(terminal) Update in a terminal…', description: u.command, detail: 'You confirm the command on the next step. The board writes nothing.', action: 'update' },
      { label: '$(eye-closed) Dismiss for this version', description: u.latest, action: 'dismiss' },
    ];
    const choice = await vscode.window.showQuickPick(items, {
      title: `ai-eval ${vm.version.bundle ?? '?'} → ${u.latest}${u.kind === 'major' ? ' (MAJOR)' : ''}`,
      placeHolder: u.kind === 'major' ? 'A major update can change contracts — read the CHANGELOG first.' : `A ${u.kind} update is available.`,
    });
    if (!choice) return;
    if (choice.action === 'changelog' && u.changelogUrl) void vscode.env.openExternal(vscode.Uri.parse(u.changelogUrl));
    if (choice.action === 'dismiss') {
      await context.workspaceState.update(DISMISSED_KEY, u.latest);
      refresh(false);
    }
    if (choice.action === 'update') await confirmAndRun('agentic-fx update', projectRoot(), u.command, 'Runs the installer in this project. It rewrites the bundle-owned files it installed.');
  };

  const selectProject = async (): Promise<void> => {
    projects = undefined;
    const all = listProjects();
    if (!all.length) {
      void vscode.window.showInformationMessage(`No ${relPath()} found in this workspace.`);
      return;
    }
    const pinned = context.workspaceState.get<string>(SELECTED_KEY);
    const items: (vscode.QuickPickItem & { root?: string })[] = [
      { label: `${pinned ? '$(history)' : '$(pass-filled)'} Most recently updated`, description: projectLabel(all[0].root) },
      ...all.map((p) => ({ label: `${p.root === pinned ? '$(pass-filled)' : '$(folder)'} ${projectLabel(p.root)}`, root: p.root })),
    ];
    const choice = await vscode.window.showQuickPick(items, { title: 'Eval: Select Project', placeHolder: `${all.length} eval project(s) in this workspace` });
    if (!choice) return;
    await context.workspaceState.update(SELECTED_KEY, choice.root);
    refresh();
  };

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (!e.affectsConfiguration('evalBoard')) return;
      projects = undefined;
      rewatch();
      refresh();
    }),
    vscode.commands.registerCommand('evalBoard.refresh', () => {
      projects = undefined;
      refresh();
    }),
    vscode.commands.registerCommand('evalBoard.selectProject', selectProject),
    vscode.commands.registerCommand('evalBoard.openBoard', () => BoardPanel.show(context, source)),
    vscode.commands.registerCommand('evalBoard.openAgents', () => {
      BoardPanel.show(context, source);
      BoardPanel.showTab('agents');
    }),
    vscode.commands.registerCommand('evalBoard.runSuite', (arg?: unknown) => runSuite(arg, false)),
    vscode.commands.registerCommand('evalBoard.dryRunSuite', (arg?: unknown) => runSuite(arg, true)),
    vscode.commands.registerCommand('evalBoard.lint', lint),
    vscode.commands.registerCommand('evalBoard.bundleUpdate', bundleUpdate),
    vscode.commands.registerCommand('evalBoard.openArtifact', (relative: string) => {
      const abs = typeof relative === 'string' ? resolveInProject(projectRoot(), relative) : undefined;
      if (abs) void vscode.commands.executeCommand('vscode.open', vscode.Uri.file(abs));
    }),
  );

  refresh();
}

export function deactivate(): void {
  // Everything is a disposable on the context. No temp files, no background process.
}
