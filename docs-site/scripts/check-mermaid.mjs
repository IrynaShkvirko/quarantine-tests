/**
 * Renders every ```mermaid block in content/docs and ../docs with mermaid-cli,
 * so a broken diagram fails CI instead of showing an error on the site.
 * Needs network once to fetch @mermaid-js/mermaid-cli through npx.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const here = path.dirname(new URL(import.meta.url).pathname);
const roots = [path.join(here, '../content/docs'), path.join(here, '../../docs')];

async function* files(dir) {
  for (const e of await fs.readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) yield* files(full);
    else if (/\.(md|mdx)$/.test(e.name)) yield full;
  }
}

const tmp = await fs.mkdtemp(path.join(os.tmpdir(), 'mmd-'));
let count = 0;
let failed = 0;
for (const root of roots) {
  for await (const file of files(root)) {
    const text = await fs.readFile(file, 'utf8');
    for (const [, chart] of text.matchAll(/```mermaid\n([\s\S]*?)```/g)) {
      const input = path.join(tmp, `${count}.mmd`);
      await fs.writeFile(input, chart);
      try {
        execFileSync('npx', ['-y', '@mermaid-js/mermaid-cli', '-q', '-i', input, '-o', `${input}.svg`], { stdio: 'pipe' });
      } catch (e) {
        failed += 1;
        console.error(`✗ ${path.relative(process.cwd(), file)} (diagram ${count})\n${e.stderr?.toString() ?? e}`);
      }
      count += 1;
    }
  }
}
console.log(`[check-mermaid] ${count - failed}/${count} diagrams render`);
process.exit(failed ? 1 : 0);
