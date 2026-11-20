import './global.css';
import { RootProvider } from 'fumadocs-ui/provider/next';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: {
    template: '%s | Flaky Test Quarantine',
    default: 'Flaky Test Quarantine',
  },
  description: 'Detect, quarantine and fix flaky tests across GitHub Actions and Jenkins.',
};

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="flex min-h-screen flex-col">
        {/* Static export: the search index is a prebuilt JSON file. */}
        <RootProvider search={{ options: { type: 'static' } }}>{children}</RootProvider>
      </body>
    </html>
  );
}
