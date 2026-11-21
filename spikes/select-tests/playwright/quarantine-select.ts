/**
 * M0-11 prototype: select Playwright tests by quarantine key.
 *
 * Two mechanisms, both fed by a file path (FQ_QUARANTINE_FILE), never by the command line:
 *   1. grep / grepInvert regexes built in playwright.config.ts (works in any version).
 *   2. A --test-list file (Playwright >= 1.5x) written next to the YAML (see writeTestList).
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { parse } from 'yaml';

const PREFIX = 'playwright::';
const SEP = ' > ';

export interface TestKey {
  file: string;
  titles: string[]; // describe titles followed by the test title
}

export function loadKeys(path: string): TestKey[] {
  // An empty or comment-only file parses to null; `tests:` with no entries is null too.
  const doc = (parse(readFileSync(path, 'utf8')) ?? {}) as { tests?: { id?: unknown }[] | null };
  return (doc.tests ?? [])
    .filter((t): t is { id: string } => typeof t?.id === 'string')
    .map((t) => t.id)
    .filter((id) => id.startsWith(PREFIX))
    .map((id) => {
      const rest = id.slice(PREFIX.length);
      const i = rest.indexOf('::');
      return { file: rest.slice(0, i), titles: rest.slice(i + 2).split(SEP) };
    });
}

export function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\\/-]/g, '\\$&');
}

/**
 * Playwright matches grep against `test.titlePath().join(' ')`, which starts with the project
 * name, then the file, the describes and the test title. One alternation, anchored on both ends.
 */
export function keysToRegExp(keys: TestKey[]): RegExp | undefined {
  if (keys.length === 0) return undefined;
  const alts = keys.map((k) => `${escapeRegExp(k.file)} ${k.titles.map(escapeRegExp).join(' ')}`);
  return new RegExp(`(?:^|\\s)(?:${alts.join('|')})$`);
}

export function selection(): { grep?: RegExp; grepInvert?: RegExp } {
  const file = process.env.FQ_QUARANTINE_FILE;
  const mode = process.env.FQ_QUARANTINE_MODE ?? 'off';
  if (!file || mode === 'off') return {};
  const re = keysToRegExp(loadKeys(file));
  if (mode === 'only') {
    // An empty list must run nothing, not everything.
    return { grep: re ?? /^(?!)/ };
  }
  return re ? { grepInvert: re } : {};
}

/** Write the keys in `--test-list` format: `file > describe > title` per line. */
export function writeTestList(yamlPath: string, outPath: string): number {
  const keys = loadKeys(yamlPath);
  writeFileSync(outPath, keys.map((k) => [k.file, ...k.titles].join(SEP)).join('\n') + '\n');
  return keys.length;
}

if (process.argv[1]?.endsWith('quarantine-select.ts') && process.argv[2] && process.argv[3]) {
  writeTestList(process.argv[2], process.argv[3]);
}
