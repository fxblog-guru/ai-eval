/**
 * The two webviews — the sidebar Overview and the full-width Board tab — share one host.
 *
 * The extension turns the index into a view model (`viewmodel.ts`) and posts it to the page. The
 * page (`media/board.js`) only draws it. A refresh arrives as a message, not a page reload.
 *
 * The board never writes a file. The only things it starts are terminals, and only after the
 * reader confirmed the exact command (a suite dry run, the linter, the installer's update).
 */

import * as vscode from 'vscode';
import { AgentsFeed } from './agentsView';
import { BoardVM } from './viewmodel';

export type Layout = 'page' | 'sidebar';

export interface BoardSource {
  viewModel(): BoardVM;
  accent(): string;
  projectLabel?(): string | undefined;
  /** Feeds the Agents tab; without it the tab is not offered. */
  agents?: AgentsFeed;
}

/** Messages the page may send; the host validates each before acting. */
export type PageMessage =
  | { command: 'ready' }
  | { command: 'open'; path: string }
  | { command: 'copy'; text: string }
  | { command: 'openBoard' }
  | { command: 'runSuite'; suite: string; dryRun?: boolean }
  | { command: 'lint' }
  | { command: 'update' };

export const ACCENTS = ['coral', 'violet', 'theme'];

/** A path the page may ask to open: relative, inside the project, no traversal. */
export function isSafeRelative(p: string): boolean {
  if (!p || p.startsWith('/') || p.startsWith('\\') || /^[a-zA-Z]:/.test(p)) return false;
  return !p.split(/[\\/]/).some((seg) => seg === '..');
}

const SUITE_NAME = /^[a-z0-9][a-z0-9-]*$/;

class BoardHost {
  private readonly disposables: vscode.Disposable[] = [];

  constructor(
    private readonly webview: vscode.Webview,
    extensionUri: vscode.Uri,
    private readonly source: BoardSource,
    layout: Layout,
  ) {
    webview.options = { enableScripts: true, localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'media')] };
    webview.html = this.shell(extensionUri, layout);
    if (source.agents) this.disposables.push(source.agents.attach(webview));
    webview.onDidReceiveMessage((msg: PageMessage) => this.onMessage(msg), null, this.disposables);
  }

  private onMessage(msg: PageMessage): void {
    switch (msg?.command) {
      case 'ready':
        this.render();
        return;
      case 'open':
        if (typeof msg.path === 'string' && isSafeRelative(msg.path)) void vscode.commands.executeCommand('evalBoard.openArtifact', msg.path);
        return;
      case 'copy':
        if (typeof msg.text === 'string') void vscode.env.clipboard.writeText(msg.text).then(() => vscode.window.setStatusBarMessage(`Copied: ${msg.text}`, 2500));
        return;
      case 'openBoard':
        void vscode.commands.executeCommand('evalBoard.openBoard');
        return;
      case 'runSuite':
        if (typeof msg.suite === 'string' && SUITE_NAME.test(msg.suite)) void vscode.commands.executeCommand(msg.dryRun ? 'evalBoard.dryRunSuite' : 'evalBoard.runSuite', msg.suite);
        return;
      case 'lint':
        void vscode.commands.executeCommand('evalBoard.lint');
        return;
      case 'update':
        void vscode.commands.executeCommand('evalBoard.bundleUpdate');
        return;
    }
  }

  render(): void {
    const accent = ACCENTS.includes(this.source.accent()) ? this.source.accent() : 'coral';
    void this.webview.postMessage({ command: 'state', vm: this.source.viewModel(), accent, project: this.source.projectLabel?.() ?? null, agents: !!this.source.agents });
  }

  showTab(tab: string): void {
    void this.webview.postMessage({ command: 'tab', tab });
  }

  dispose(): void {
    while (this.disposables.length) this.disposables.pop()?.dispose();
  }

  private shell(extensionUri: vscode.Uri, layout: Layout): string {
    const uri = (name: string): vscode.Uri => this.webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, 'media', name));
    const accent = ACCENTS.includes(this.source.accent()) ? this.source.accent() : 'coral';
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; style-src ${this.webview.cspSource}; script-src ${this.webview.cspSource};" />
<link rel="stylesheet" href="${uri('board.css')}" />
<link rel="stylesheet" href="${uri('agents.css')}" />
<title>AI Eval</title>
</head>
<body data-layout="${layout}" data-accent="${accent}">
<div id="app" class="empty">Loading the eval index…</div>
<script src="${uri('agents.js')}"></script>
<script src="${uri('board.js')}"></script>
</body>
</html>`;
  }
}

/** The full-width board, opened as an editor tab. */
export class BoardPanel {
  private static current: BoardPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private readonly host: BoardHost;

  static show(context: vscode.ExtensionContext, source: BoardSource): void {
    if (BoardPanel.current) {
      BoardPanel.current.panel.reveal(vscode.ViewColumn.One);
      BoardPanel.current.retitle();
      BoardPanel.current.host.render();
      return;
    }
    BoardPanel.current = new BoardPanel(context, source);
  }

  static refreshIfOpen(): void {
    BoardPanel.current?.retitle();
    BoardPanel.current?.host.render();
  }

  /** Switch the open board to a tab, e.g. `agents` from Eval: Open Agents. */
  static showTab(tab: string): void {
    BoardPanel.current?.host.showTab(tab);
  }

  private retitle(): void {
    const label = this.source.projectLabel?.();
    this.panel.title = label ? `Eval Board — ${label}` : 'Eval Board';
  }

  private constructor(
    context: vscode.ExtensionContext,
    private readonly source: BoardSource,
  ) {
    this.panel = vscode.window.createWebviewPanel('evalBoard.board', 'Eval Board', vscode.ViewColumn.One, {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, 'media')],
    });
    this.panel.iconPath = vscode.Uri.joinPath(context.extensionUri, 'media', 'icon.svg');
    this.retitle();
    this.host = new BoardHost(this.panel.webview, context.extensionUri, source, 'page');
    this.panel.onDidDispose(() => {
      BoardPanel.current = undefined;
      this.host.dispose();
    });
  }
}

/** The sidebar Overview: the same page in its narrow layout. */
export class OverviewViewProvider implements vscode.WebviewViewProvider {
  static readonly viewType = 'evalBoard.overview';
  private host: BoardHost | undefined;
  private view: vscode.WebviewView | undefined;
  private description: string | undefined;

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly source: BoardSource,
  ) {}

  resolveWebviewView(view: vscode.WebviewView): void {
    this.host?.dispose();
    this.host = new BoardHost(view.webview, this.extensionUri, this.source, 'sidebar');
    this.view = view;
    view.description = this.description;
    view.onDidDispose(() => {
      this.host?.dispose();
      this.host = undefined;
      this.view = undefined;
    });
  }

  refresh(): void {
    this.host?.render();
  }

  setDescription(description: string | undefined): void {
    this.description = description;
    if (this.view) this.view.description = description;
  }
}
