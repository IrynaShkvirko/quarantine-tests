import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { repoUrl } from './shared';

/** Shared header for both tabs: title, tab links, GitHub link. */
export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: <span className="font-semibold">Flaky Test Quarantine</span>,
    },
    links: [
      { text: 'Docs', url: '/docs', active: 'nested-url' },
      { text: 'Engineering', url: '/engineering', active: 'nested-url' },
    ],
    githubUrl: repoUrl,
  };
}
