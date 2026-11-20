/**
 * Copies the repo's docs/ folder (source of truth for design docs) into
 * content/engineering/ so Fumadocs can render it under /engineering.
 *
 * - Title comes from the first "# " heading (removed from the body, the page shows it).
 * - Description comes from the first paragraph after it.
 * - "<", "{" and "}" outside code are escaped so the files parse as MDX as well as Markdown.
 * - meta.json files set the sidebar order.
 *
 * Generated files are gitignored. Run with `pnpm sync` (also runs before dev and build).
 */
import fs from 'node:fs/promises';
import path from 'node:path';

const here = path.dirname(new URL(import.meta.url).pathname);
const SRC = path.resolve(process.env.DOCS_SRC ?? path.join(here, '../../docs'));
const OUT = path.resolve(path.join(here, '../content/engineering'));

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

function plain(text) {
  return text
    .replace(/\*\*|__|`/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

function toPage(raw, fallbackTitle) {
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
  return fm.join('\n') + escapeOutsideCode(body.replace(/^\s+/, ''));
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
    await fs.writeFile(target, toPage(await fs.readFile(file, 'utf8'), slug));
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

  // meta.json files
  for (const [folder, slugs] of folders) {
    const dir = path.join(OUT, folder);
    if (folder === '.') {
      const subfolders = [...folders.keys()].filter((f) => f !== '.' && !f.includes(path.sep));
      const present = new Set([...slugs, ...subfolders]);
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
        JSON.stringify({ title: FOLDER_TITLES[name] ?? name, pages: [...slugs].sort().reverse() }, null, 2),
      );
    }
  }

  console.log(`[sync-engineering] ${files.length} files from ${SRC} -> ${OUT}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
