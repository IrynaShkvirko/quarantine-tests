/**
 * Offline internal-link check on the static export (out/).
 * Every site-internal href/src must resolve to a file in out/, and a #fragment
 * must match an id in the target page. External links (http, mailto) are skipped.
 *
 * Usage: node scripts/check-links.mjs [outDir]
 * Set DOCS_BASE_PATH (e.g. /quarantine-tests) when the site was built with a base path.
 */
import fs from 'node:fs/promises';
import path from 'node:path';

const outDir = path.resolve(process.argv[2] ?? 'out');
const basePath = (process.env.DOCS_BASE_PATH ?? '').replace(/\/$/, '');

async function* htmlFiles(dir) {
  for (const e of await fs.readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) yield* htmlFiles(full);
    else if (e.name.endsWith('.html')) yield full;
  }
}

const exists = (p) =>
  fs.stat(p).then(
    (s) => s,
    () => null,
  );

/** Maps a URL path to a file in out/, or null when nothing is served there. */
async function resolveFile(urlPath) {
  let rel;
  try {
    rel = decodeURIComponent(urlPath).replace(/^\/+/, '');
  } catch {
    return null; // malformed % escape: reported as a broken link
  }
  const base = path.join(outDir, rel);
  if (base !== outDir && !base.startsWith(outDir + path.sep)) return null;
  for (const candidate of [base, `${base}.html`, path.join(base, 'index.html')]) {
    const s = await exists(candidate);
    if (s?.isFile()) return candidate;
  }
  return null;
}

const safeDecode = (v) => {
  try {
    return decodeURIComponent(v);
  } catch {
    return v;
  }
};

const idCache = new Map();
async function idsOf(file) {
  if (!idCache.has(file)) {
    const html = await fs.readFile(file, 'utf8');
    idCache.set(file, new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1])));
  }
  return idCache.get(file);
}

let checked = 0;
const broken = [];
for await (const file of htmlFiles(outDir)) {
  const pageUrl = '/' + path.relative(outDir, file).replace(/index\.html$/, '').replace(/\\/g, '/');
  const html = await fs.readFile(file, 'utf8');
  // Only real tags: the RSC payload inside <script> also contains href="..." strings.
  for (const [, raw] of html.matchAll(/<(?:a|link|img|source|script|iframe)\b[^>]*?\s(?:href|src)="([^"]*)"/g)) {
    const url = raw.replace(/&amp;/g, '&');
    if (!url || /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(url)) continue; // external, mailto:, data:
    const [withoutHash, fragment] = url.split('#');
    const [pathname] = withoutHash.split('?');
    let target;
    if (!pathname) target = pageUrl;
    else if (pathname.startsWith('/')) {
      if (basePath && !(pathname === basePath || pathname.startsWith(`${basePath}/`))) {
        broken.push(`${pageUrl}: ${url} (outside base path ${basePath})`);
        continue;
      }
      target = basePath ? pathname.slice(basePath.length) || '/' : pathname;
    } else target = new URL(pathname, `http://x${pageUrl}`).pathname;

    checked += 1;
    const targetFile = await resolveFile(target);
    if (!targetFile) {
      broken.push(`${pageUrl}: ${url} (no such page or file)`);
    } else if (fragment && targetFile.endsWith('.html') && !(await idsOf(targetFile)).has(safeDecode(fragment))) {
      broken.push(`${pageUrl}: ${url} (no element with id "${fragment}")`);
    }
  }
}

for (const b of broken) console.error(`✗ ${b}`);
console.log(`[check-links] ${checked - broken.length}/${checked} internal links resolve`);
process.exit(broken.length ? 1 : 0);
