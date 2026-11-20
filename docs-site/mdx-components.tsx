import defaultMdxComponents from 'fumadocs-ui/mdx';
import { Tab, Tabs } from 'fumadocs-ui/components/tabs';
import { Step, Steps } from 'fumadocs-ui/components/steps';
import type { MDXComponents } from 'mdx/types';
import { Mermaid } from '@/components/mermaid';

/** Components available in every page without importing them. */
export function getMDXComponents(components?: MDXComponents) {
  return {
    ...defaultMdxComponents, // Callout, Card, Cards, code blocks, headings
    Tab,
    Tabs,
    Step,
    Steps,
    Mermaid,
    ...components,
  } satisfies MDXComponents;
}

export const useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
