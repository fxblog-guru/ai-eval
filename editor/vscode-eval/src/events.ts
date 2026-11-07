/**
 * Read `<eval root>/logs/activity.jsonl` for a project. Kept apart from activity.ts so that file
 * stays an identical copy across the four addons. This file must not import `vscode`.
 */

import * as fs from 'fs';
import * as path from 'path';
import { ActivityEvent, parseActivity } from './activity';

/** Read at most the last MAX_BYTES: the log rolls at 5 MB, and the views show the newest events. */
const MAX_BYTES = 1024 * 1024;

export function readEvents(projectRoot: string, evalRoot: string): ActivityEvent[] {
  const file = path.join(projectRoot, ...evalRoot.split('/').filter(Boolean), 'logs', 'activity.jsonl');
  try {
    const size = fs.statSync(file).size;
    const fd = fs.openSync(file, 'r');
    try {
      const len = Math.min(size, MAX_BYTES);
      const buf = Buffer.alloc(len);
      fs.readSync(fd, buf, 0, len, size - len);
      // A cut first line fails to parse and is skipped, like a torn last one.
      return parseActivity(buf.toString('utf8'));
    } finally {
      fs.closeSync(fd);
    }
  } catch {
    return [];
  }
}
