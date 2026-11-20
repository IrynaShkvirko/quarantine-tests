import { engineeringSource, getLLMText, source } from '@/lib/source';

export const revalidate = false;

/** All pages as one Markdown file (user docs first, then engineering). */
export async function GET() {
  const pages = [...source.getPages(), ...engineeringSource.getPages()];
  const texts = await Promise.all(pages.map(getLLMText));
  return new Response(texts.join('\n\n'));
}
