import { notFound } from 'next/navigation';
import { getLLMText, getPageMarkdownUrl, engineeringSource } from '@/lib/source';

export const revalidate = false;

/** Raw Markdown of one page, e.g. /llms.mdx/engineering/<slug>/content.md */
export async function GET(_req: Request, { params }: RouteContext<'/llms.mdx/engineering/[[...slug]]'>) {
  const { slug } = await params;
  const page = engineeringSource.getPage(slug?.slice(0, -1));
  if (!page) notFound();
  return new Response(await getLLMText(page), {
    headers: { 'Content-Type': 'text/markdown' },
  });
}

export function generateStaticParams() {
  return engineeringSource.getPages().map((page) => ({ slug: getPageMarkdownUrl('engineering', page).segments }));
}
