// Spike: one <testcase> per attempt, with fq.test_key and fq.attempt properties.
const fs = require('node:fs');
const path = require('node:path');

const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const plain = (s) => s.replace(/\u001b\[[0-9;]*m/g, '');
const firstLine = (s) => plain(s || '').split('\n').find((l) => l.trim()) || '';
const SKIPPED = ['pending', 'skipped', 'todo', 'disabled'];
const KNOWN = ['passed', 'failed', ...SKIPPED];

// Key paths are relative to the repo root (§3.1), not Jest's rootDir, and always use '/'.
// The adapter passes FQ_REPO_ROOT; otherwise walk up to the nearest .git.
function repoRoot(start) {
  if (process.env.FQ_REPO_ROOT) return path.resolve(process.env.FQ_REPO_ROOT);
  for (let d = path.resolve(start); ; d = path.dirname(d)) {
    if (fs.existsSync(path.join(d, '.git'))) return d;
    if (path.dirname(d) === d) return path.resolve(start);
  }
}

class FqReporter {
  constructor(globalConfig, options) {
    this.out = (options && options.outputFile) || 'fq.xml';
    this.root = repoRoot(globalConfig.rootDir);
    this.unknown = []; // statuses we don't know how to map: refuse, never write them as a pass
    this.rows = [];
    this.dump = [];
    this.seen = new Set(); // file + full name of tests that reached onTestCaseResult

  }

  // Jest 30 (jest-circus) calls this once per attempt: status/duration/failureMessages are
  // that attempt's own, and `invocations` is the attempt number (1, 2, 3).
  onTestCaseResult(test, r) {
    this.dump.push({ title: r.fullName, status: r.status, invocations: r.invocations, retryReasons: r.retryReasons, duration: r.duration, failureMessages: r.failureMessages });
    this.addRow(test.path, r);
  }

  // test.skip / describe.skip never reach onTestCaseResult; they only appear in the file result.
  onTestResult(test, fileResult) {
    for (const r of fileResult.testResults) {
      if (SKIPPED.includes(r.status) && !this.seen.has(this.id(test.path, r))) this.addRow(test.path, r);
    }
  }

  id(testPath, r) {
    return `${testPath}::${[...r.ancestorTitles, r.title].join(' > ')}`;
  }

  addRow(testPath, r) {
    this.seen.add(this.id(testPath, r));
    if (!KNOWN.includes(r.status)) {
      this.unknown.push(`${r.status}: ${r.fullName}`);
      return;
    }
    const file = path.relative(this.root, testPath).split(path.sep).join('/');
    const name = [...r.ancestorTitles, r.title].join(' > ');
    const key = `jest::${file}::${name}`;
    let body = '';
    if (r.status === 'failed') body = `<failure message="${esc(firstLine((r.failureMessages || [])[0]))}"/>`;
    else if (SKIPPED.includes(r.status)) body = '<skipped/>';
    this.rows.push(
      `  <testcase classname="${esc(file)}" name="${esc(name)}" file="${esc(file)}" time="${((r.duration || 0) / 1000).toFixed(3)}">` +
        `<properties><property name="fq.test_key" value="${esc(key)}"/><property name="fq.attempt" value="${r.invocations || 1}"/></properties>${body}</testcase>`,
    );
  }

  onRunComplete() {
    fs.writeFileSync(this.out, `<?xml version="1.0" encoding="UTF-8"?>\n<testsuite name="jest" tests="${this.rows.length}">\n${this.rows.join('\n')}\n</testsuite>\n`);
    fs.writeFileSync('native-testcase-results.json', JSON.stringify(this.dump, null, 2));
  }

  // A non-undefined return makes Jest exit non-zero.
  getLastError() {
    if (this.unknown.length) return new Error(`fq-reporter: unknown test status, not written: ${this.unknown.join('; ')}`);
    return undefined;
  }
}
module.exports = FqReporter;
