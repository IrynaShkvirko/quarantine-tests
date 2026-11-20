import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import { baseOptions } from '@/lib/layout.shared';
import { engineeringSource } from '@/lib/source';

export default function Layout({ children }: LayoutProps<'/engineering'>) {
  return (
    <DocsLayout tree={engineeringSource.getPageTree()} {...baseOptions()}>
      {children}
    </DocsLayout>
  );
}
