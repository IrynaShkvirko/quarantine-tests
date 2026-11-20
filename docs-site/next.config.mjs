import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

/** Static export so the site can be served from GitHub Pages. */
const config = {
  output: 'export',
  reactStrictMode: true,
  images: { unoptimized: true },
  // GitHub Pages serves project sites under /<repo>; set DOCS_BASE_PATH=/quarantine-tests in CI.
  basePath: process.env.DOCS_BASE_PATH || '',
  trailingSlash: true,
};

export default withMDX(config);
