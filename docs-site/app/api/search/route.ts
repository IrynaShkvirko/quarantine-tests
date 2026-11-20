import { createFromSource } from 'fumadocs-core/search/server';
import { source } from '@/lib/source';

// Static export: the search index is built once and served as JSON (user docs).
export const revalidate = false;
export const { staticGET: GET } = createFromSource(source, { language: 'english' });
