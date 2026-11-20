import { llms } from 'fumadocs-core/source';
import { engineeringSource, source } from '@/lib/source';

export const revalidate = false;

/** Index of every page for LLMs and agents (both tabs). */
export async function GET() {
  const [docsIndex, engIndex] = await Promise.all([llms(source).index(), llms(engineeringSource).index()]);
  return new Response(`${docsIndex}\n\n${engIndex}`);
}
