import repo from './repo.json';

/** Also read by scripts/sync-engineering.mjs, so the repo is named in one place. */
export const gitConfig = repo;

export const repoUrl = `https://github.com/${gitConfig.user}/${gitConfig.repo}`;

/** Where each tab's pages live in the repo, for the "Open on GitHub" action. */
export const contentPaths = {
  docs: 'docs-site/content/docs',
  engineering: 'docs', // synced from the repo's docs/ folder
} as const;
