import { defineConfig } from '@playwright/test';

export default defineConfig({
  retries: 2,
  workers: 1,
  reporter: [
    ['junit', { outputFile: 'native.xml' }],
    ['json', { outputFile: 'native.json' }],
    ['./fq-reporter.ts', { outputFile: 'fq.xml' }],
  ],
});
