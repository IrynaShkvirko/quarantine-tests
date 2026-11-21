// Spike: one <testcase> per attempt, with fq.test_key and fq.attempt properties.
import type { FullConfig, Reporter, TestCase, TestResult } from '@playwright/test/reporter';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, relative, resolve, sep } from 'node:path';

const esc = (s: string): string =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
// strip ANSI colour codes Playwright puts in error messages
// eslint-disable-next-line no-control-regex
const plain = (s: string): string => s.replace(/\u001b\[[0-9;]*m/g, '');

// Key paths are relative to the repo root (§3.1), not Playwright's rootDir, and always use '/'.
// The adapter passes FQ_REPO_ROOT; otherwise walk up to the nearest .git.
export function repoRoot(start: string): string {
  if (process.env.FQ_REPO_ROOT) return resolve(process.env.FQ_REPO_ROOT);
  for (let d = resolve(start); ; d = dirname(d)) {
    if (existsSync(resolve(d, '.git'))) return d;
    if (dirname(d) === d) return resolve(start);
  }
}
const repoPath = (root: string, file: string): string => relative(root, file).split(sep).join('/');

export default class FqReporter implements Reporter {
  private rows: string[] = [];
  private root = process.cwd();
  constructor(private opts: { outputFile?: string } = {}) {}

  onBegin(config: FullConfig): void {
    this.root = repoRoot(config.rootDir);
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    // interrupted (run stopped mid-test) is not evidence either way; never write it as a pass
    if (result.status === 'interrupted') return;
    const file = repoPath(this.root, test.location.file);
    // titlePath() = ['', project, file, ...describes, title]; keep describes + title
    const path = test.titlePath().slice(3);
    const name = path.join(' > ');
    const key = `playwright::${file}::${name}`;
    // Compare with expectedStatus so test.fail() is handled: failing as expected is a pass,
    // passing unexpectedly is a failure.
    let body = '';
    if (result.status === 'skipped') body = '<skipped/>';
    else if (result.status !== test.expectedStatus) {
      const msg =
        result.status === 'passed'
          ? 'expected to fail (test.fail) but passed'
          : result.error?.message
            ? plain(result.error.message).split('\n')[0]
            : result.status;
      body = `<failure message="${esc(msg ?? '')}"/>`;
    }
    this.rows.push(
      `  <testcase classname="${esc(file)}" name="${esc(name)}" file="${esc(file)}" time="${(result.duration / 1000).toFixed(3)}">` +
        `<properties><property name="fq.test_key" value="${esc(key)}"/>` +
        `<property name="fq.attempt" value="${result.retry + 1}"/></properties>${body}</testcase>`,
    );
  }

  onEnd(): void {
    const out = this.opts.outputFile ?? 'fq.xml';
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(
      out,
      `<?xml version="1.0" encoding="UTF-8"?>\n<testsuite name="playwright" tests="${this.rows.length}">\n${this.rows.join('\n')}\n</testsuite>\n`,
    );
  }
}
