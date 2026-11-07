/**
 * The sidebar trees: suites (with their latest run), and the evidence behind them — failure
 * modes, judges, datasets, red-team probes. Every leaf opens the file it was read from.
 */

import * as vscode from 'vscode';
import { BoardVM, ItemVM, SuiteVM, Tone } from './viewmodel';

const ICON: Record<Tone, string> = { ok: 'pass', bad: 'error', warn: 'warning', muted: 'circle-outline', accent: 'circle-filled' };
const COLOR: Partial<Record<Tone, string>> = { ok: 'testing.iconPassed', bad: 'errorForeground', warn: 'editorWarning.foreground' };

const icon = (tone: Tone): vscode.ThemeIcon => new vscode.ThemeIcon(ICON[tone], COLOR[tone] ? new vscode.ThemeColor(COLOR[tone]!) : undefined);

function openCommand(path: string | null): vscode.Command | undefined {
  return path ? { command: 'evalBoard.openArtifact', title: 'Open', arguments: [path] } : undefined;
}

type Node = { kind: 'suite'; suite: SuiteVM } | { kind: 'line'; label: string; detail?: string; path?: string | null; tone: Tone } | { kind: 'group'; label: string; items: ItemVM[] } | { kind: 'item'; item: ItemVM };

abstract class Provider implements vscode.TreeDataProvider<Node> {
  private readonly emitter = new vscode.EventEmitter<Node | undefined>();
  readonly onDidChangeTreeData = this.emitter.event;
  constructor(protected readonly vm: () => BoardVM) {}
  refresh(): void {
    this.emitter.fire(undefined);
  }
  abstract getChildren(node?: Node): Node[];
  getTreeItem(node: Node): vscode.TreeItem {
    switch (node.kind) {
      case 'suite': {
        const s = node.suite;
        const item = new vscode.TreeItem(s.suite, vscode.TreeItemCollapsibleState.Collapsed);
        item.description = `${s.layer} · ${s.verdict}${s.gated ? '' : ' (ungated)'}`;
        item.tooltip = `${s.suite} — ${s.verdict}\n${s.why}${s.passK ? `\npass^k ${s.passK}` : ''}`;
        item.iconPath = icon(s.tone);
        item.contextValue = 'evalBoard.suite';
        return item;
      }
      case 'line': {
        const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.None);
        item.description = node.detail;
        item.iconPath = icon(node.tone);
        item.command = openCommand(node.path ?? null);
        return item;
      }
      case 'group': {
        const item = new vscode.TreeItem(node.label, node.items.length ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.None);
        item.description = String(node.items.length);
        return item;
      }
      case 'item': {
        const i = node.item;
        const item = new vscode.TreeItem(i.id, vscode.TreeItemCollapsibleState.None);
        item.description = `${i.label} · ${i.detail}`;
        item.tooltip = `${i.id}\n${i.label}\n${i.detail}`;
        item.iconPath = icon(i.tone);
        item.command = openCommand(i.path);
        return item;
      }
    }
  }
}

export class SuitesTreeProvider extends Provider {
  getChildren(node?: Node): Node[] {
    const vm = this.vm();
    if (!vm.ok) return [];
    if (!node) return vm.suites.map((suite) => ({ kind: 'suite', suite }));
    if (node.kind !== 'suite') return [];
    const s = node.suite;
    const lines: Node[] = [{ kind: 'line', label: s.why, tone: s.tone, path: s.summary }];
    if (s.passK) lines.push({ kind: 'line', label: 'pass^k', detail: s.passK, tone: 'muted', path: s.summary });
    if (s.pass1) lines.push({ kind: 'line', label: 'pass^1', detail: s.pass1, tone: 'muted', path: s.summary });
    if (s.flaky) lines.push({ kind: 'line', label: 'flaky', detail: s.flaky, tone: 'muted', path: s.summary });
    for (const c of s.failing) lines.push({ kind: 'line', label: c, detail: 'failed on some repeat', tone: 'bad', path: s.summary });
    lines.push({ kind: 'line', label: 'suite file', detail: s.path, tone: 'muted', path: s.path });
    return lines;
  }
}

export class EvidenceTreeProvider extends Provider {
  getChildren(node?: Node): Node[] {
    const vm = this.vm();
    if (!vm.ok) return [];
    if (!node) {
      return [
        { kind: 'group', label: 'Failure modes', items: vm.failureModes },
        { kind: 'group', label: 'Judges', items: vm.judges },
        { kind: 'group', label: 'Datasets', items: vm.datasets },
        { kind: 'group', label: 'Red-team probes', items: vm.probes },
        { kind: 'group', label: 'Scorecards', items: vm.scorecards },
      ];
    }
    return node.kind === 'group' ? node.items.map((item) => ({ kind: 'item', item })) : [];
  }
}
