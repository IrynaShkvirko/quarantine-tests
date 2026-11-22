/**
 * Copies the repo's docs/ folder (source of truth for design docs) into
 * content/engineering/ so Fumadocs can render it under /engineering.
 *
 * - Title comes from the first "# " heading (removed from the body, the page shows it).
 * - Description comes from the first paragraph after it.
 * - "<", "{" and "}" outside code are escaped so the files parse as MDX as well as Markdown.
 * - Relative links to other synced pages become /engineering/... paths; links to repo files that are
 *   not site pages (examples, CLAUDE.md, code) become GitHub links.
 * - meta.json files set the sidebar order.
 *
 * Generated files are gitignored. Run with `pnpm sync` (also runs before dev and build).
 */
import { realpathSync } from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';

const here = import.meta.dirname;
const SRC = path.resolve(process.env.DOCS_SRC ?? path.join(here, '../../docs'));
const OUT = path.resolve(process.env.DOCS_OUT ?? path.join(here, '../content/engineering'));
const REPO_ROOT = path.resolve(here, '../..');
const repo = JSON.parse(await fs.readFile(path.join(here, '../lib/repo.json'), 'utf8'));
const GITHUB = `https://github.com/${repo.user}/${repo.repo}`;

/** Sidebar order and titles. Files/folders not listed are appended alphabetically. */
const ROOT_ORDER = [
  'index',
  '---Design---',
  'architecture',
  'ingestion-flow',
  'ingestion-backend',
  '---Process---',
  'development-setup',
  'agents',
  'writing-docs',
  '---Feature work---',
  'feature-requirements',
  'requirements',
  'plans',
  'contracts',
  'spikes',
];
const FOLDER_TITLES = {
  'feature-requirements': 'Feature requirements',
  requirements: 'Requirements',
  plans: 'Plans',
  contracts: 'Contracts',
  spikes: 'Spikes',
  tasks: 'Tasks',
};

function escapeOutsideCode(markdown) {
  const lines = markdown.split('\n');
  let fence = null;
  return lines
    .map((line) => {
      const m = line.match(/^\s*(```+|~~~+)/);
      if (m) {
        if (!fence) fence = m[1][0];
        else if (m[1][0] === fence) fence = null;
        return line;
      }
      if (fence) return line;
      // split on inline code spans and escape only the text between them
      return line
        .split(/(`+[^`]*`+)/g)
        .map((part, i) => (i % 2 === 1 ? part : part.replace(/([<{}])/g, '\\$1')))
        .join('');
    })
    .join('\n');
}

/**
 * Markdown links in docs/ are relative to the repo. Pages that become site pages keep working;
 * links to other repo files (JSON examples, CLAUDE.md, code) are pointed at GitHub, and
 * `../blob/main/...` (the form issue bodies use) is expanded.
 */
async function rewriteLinks(markdown, file) {
  const out = [];
  let fence = null;
  for (const line of markdown.split('\n')) {
    const m = line.match(/^\s*(```+|~~~+)/);
    if (m) {
      if (!fence) fence = m[1][0];
      else if (m[1][0] === fence) fence = null;
      out.push(line);
      continue;
    }
    if (fence) {
      out.push(line);
      continue;
    }
    const parts = [];
    let last = 0;
    for (const link of line.matchAll(/(?<!!)\[([^\]]*)\]\(([^)\s]+)((?:\s+"[^"]*")?)\)/g)) {
      const [whole, text, href, title] = link;
      const fixed = await githubHref(href, file);
      parts.push(line.slice(last, link.index));
      parts.push(fixed ? `[${text}](${fixed}${title})` : whole);
      last = link.index + whole.length;
    }
    parts.push(line.slice(last));
    out.push(parts.join(''));
  }
  return out.join('\n');
}

export async function githubHref(href, file) {
  if (/^([a-z][a-z0-9+.-]*:|#|\/)/i.test(href)) return null;
  const [target, fragment] = href.split('#');
  const suffix = fragment ? `#${fragment}` : '';
  const blob = target.match(/^(?:\.\.\/)+blob\/main\/(.+)$/);
  if (blob) return `${GITHUB}/blob/${repo.branch}/${blob[1]}${suffix}`;
  const abs = path.resolve(path.dirname(file), target);
  if (abs.endsWith('.md') && abs.startsWith(SRC + path.sep)) {
    // A synced page: use its site path, which doesn't depend on Fumadocs resolving relative .md links.
    if (!(await fs.stat(abs).catch(() => null))) return null;
    const slug = path.relative(SRC, abs).slice(0, -3).split(path.sep).join('/').replace(/(^|\/)index$/, '');
    return `/engineering/${slug ? `${slug}/` : ''}${suffix}`;
  }
  const rel = path.relative(REPO_ROOT, abs);
  if (rel.startsWith('..')) return null;
  const stat = await fs.stat(abs).catch(() => null);
  if (!stat) return null; // missing target: leave it so the link check reports it
  return `${GITHUB}/${stat.isDirectory() ? 'tree' : 'blob'}/${repo.branch}/${rel.split(path.sep).join('/')}${suffix}`;
}

function plain(text) {
  return text
    .replace(/\*\*|__|`/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

async function toPage(raw, fallbackTitle, file) {
  let body = raw.replace(/^---\n[\s\S]*?\n---\n/, ''); // drop existing frontmatter, we regenerate it
  const h1 = body.match(/^#\s+(.+)$/m);
  const title = h1 ? plain(h1[1]) : fallbackTitle;
  if (h1) body = body.replace(h1[0], '');

  const para = body
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .find((p) => p && !/^(#|```|\||-|\*\s|>|<|!\[|\d+\.)/.test(p));
  let description = para ? plain(para) : '';
  if (description.length > 180) description = `${description.slice(0, 177).trimEnd()}...`;

  const fm = ['---', `title: ${JSON.stringify(title)}`];
  if (description) fm.push(`description: ${JSON.stringify(description)}`);
  fm.push('---', '');
  return fm.join('\n') + escapeOutsideCode(await rewriteLinks(body.replace(/^\s+/, ''), file));
}

async function walk(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = [];
  for (const e of entries) {
    if (e.name.startsWith('.')) continue;
    const full = path.join(dir, e.name);
    if (e.isDirectory()) files.push(...(await walk(full)));
    else if (e.name.endsWith('.md')) files.push(full);
  }
  return files;
}

async function main() {
  await fs.rm(OUT, { recursive: true, force: true });
  await fs.mkdir(OUT, { recursive: true });

  const files = await walk(SRC);
  const folders = new Map(); // relative folder -> [slugs]

  for (const file of files) {
    const rel = path.relative(SRC, file);
    const slug = path.basename(rel, '.md');
    const folder = path.dirname(rel);
    const target = path.join(OUT, folder, `${slug}.md`);
    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.writeFile(target, await toPage(await fs.readFile(file, 'utf8'), slug, file));
    if (!folders.has(folder)) folders.set(folder, []);
    folders.get(folder).push(slug);
  }

  // Landing page for the tab, unless docs/index.md exists.
  if (!files.some((f) => path.relative(SRC, f) === 'index.md')) {
    await fs.writeFile(
      path.join(OUT, 'index.md'),
      [
        '---',
        'title: "Engineering"',
        'description: "How the system is designed and built: the design spec, flows, feature requirements, plans and the agent workflow."',
        '---',
        '',
        'These pages are rendered from the repository\'s `docs/` folder, which is the source of truth. Edit the files there, not here.',
        '',
        '- **Design spec:** `docs/architecture.md`, referenced by section number (§3.4) from requirements, plans and agents.',
        '- **Feature work:** each feature has a design (feature requirements), detailed requirements and an agent implementation plan.',
        '- **Process:** development setup, the `.claude/` agents and skills, and how to write docs.',
        '',
      ].join('\n'),
    );
    if (!folders.has('.')) folders.set('.', []);
    folders.get('.').push('index');
  }

  // Folders that hold only subfolders (docs/tasks/ holds only M0/) need a sidebar entry too.
  for (const folder of [...folders.keys()]) {
    for (let parent = path.dirname(folder); parent !== '.'; parent = path.dirname(parent)) {
      if (!folders.has(parent)) folders.set(parent, []);
    }
  }
  const childFolders = (parent) =>
    [...folders.keys()].filter((f) => f !== '.' && path.dirname(f) === parent).map((f) => path.basename(f));

  // meta.json files
  for (const [folder, slugs] of folders) {
    const dir = path.join(OUT, folder);
    if (folder === '.') {
      const present = new Set([...slugs, ...childFolders('.')]);
      const ordered = ROOT_ORDER.filter((x) => x.startsWith('---') || present.has(x));
      const rest = [...present].filter((x) => !ROOT_ORDER.includes(x)).sort();
      await fs.writeFile(
        path.join(dir, 'meta.json'),
        JSON.stringify({ title: 'Engineering', pages: [...ordered, ...rest] }, null, 2),
      );
    } else {
      const name = path.basename(folder);
      await fs.writeFile(
        path.join(dir, 'meta.json'),
        JSON.stringify(
          { title: FOLDER_TITLES[name] ?? name, pages: [...slugs, ...childFolders(folder)].sort().reverse() },
          null,
          2,
        ),
      );
    }
  }

  console.log(`[sync-engineering] ${files.length} files from ${SRC} -> ${OUT}`);
}

// Run only as a script, so the tests can import githubHref.
// import.meta.filename has symlinks resolved and argv[1] doesn't, so resolve argv[1] too.
if (process.argv[1] && realpathSync(process.argv[1]) === import.meta.filename) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
