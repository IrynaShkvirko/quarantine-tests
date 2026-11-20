// Adapted from the Headroom docs site (github.com/headroomlabs-ai/headroom, Apache-2.0).
import { loader } from 'fumadocs-core/source';
import { docs, engineering } from '../.source/server';

/** User-facing docs at /docs */
export const source = loader({
  baseUrl: '/docs',
  source: docs.toFumadocsSource(),
});

/** Engineering docs (synced from the repo's docs/ folder) at /engineering */
export const engineeringSource = loader({
  baseUrl: '/engineering',
  source: engineering.toFumadocsSource(),
});

export type Tab = 'docs' | 'engineering';
type AnySource = typeof source | typeof engineeringSource;
type Page = ReturnType<AnySource['getPages']>[number];

/** URL of the raw Markdown for a page (used by "Copy Markdown" and "Open in ..."). */
export function getPageMarkdownUrl(tab: Tab, page: Page) {
  const segments = page.slugs.length > 0 ? [...page.slugs, 'content.md'] : ['index', 'content.md'];
  return { segments, url: `/llms.mdx/${tab}/${segments.join('/')}` };
}

/** Processed Markdown of a page, for llms.txt and copy buttons. */
export async function getLLMText(page: Page) {
  try {
    return `# ${page.data.title}\n\n${await page.data.getText('processed')}`;
  } catch {
    return `# ${page.data.title}\n\n${page.data.description ?? ''}`;
  }
}
