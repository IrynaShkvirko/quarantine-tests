export const gitConfig = {
  user: 'IrynaShkvirko',
  repo: 'quarantine-tests',
  branch: 'main',
};

export const repoUrl = `https://github.com/${gitConfig.user}/${gitConfig.repo}`;

/** Where each tab's pages live in the repo, for the "Open on GitHub" action. */
export const contentPaths = {
  docs: 'docs-site/content/docs',
  engineering: 'docs', // synced from the repo's docs/ folder
} as const;
