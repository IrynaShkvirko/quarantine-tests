import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

// SRC is read at import time, so point it at a scratch docs/ folder first.
const src = await fs.mkdtemp(path.join(os.tmpdir(), 'sync-test-'));
await fs.writeFile(path.join(src, 'a.md'), '# A\n');
await fs.writeFile(path.join(src, 'b.md'), '# B\n');
process.env.DOCS_SRC = src;
const { githubHref } = await import('./sync-engineering.mjs');
const fromA = path.join(src, 'a.md');
const GH = 'https://github.com/IrynaShkvirko/quarantine-tests';

test('link to another synced page becomes a site path, keeping the anchor', async () => {
  assert.equal(await githubHref('b.md#sec', fromA), '/engineering/b/#sec');
});

test('link to a repo file that is not a page becomes a GitHub link', async () => {
  // docs-site/package.json exists in the repo; the path is resolved from a file in docs/.
  const inDocs = path.resolve(import.meta.dirname, '../../docs/x.md');
  assert.equal(await githubHref('../docs-site/package.json', inDocs), `${GH}/blob/main/docs-site/package.json`);
});

test('issue-body style ../blob/main/ link is expanded', async () => {
  assert.equal(await githubHref('../blob/main/docs/tasks/M0/README.md', fromA), `${GH}/blob/main/docs/tasks/M0/README.md`);
});

test('missing targets, absolute and external links are left alone', async () => {
  assert.equal(await githubHref('nope.md', fromA), null);
  assert.equal(await githubHref('https://example.com/x', fromA), null);
  assert.equal(await githubHref('#top', fromA), null);
});
