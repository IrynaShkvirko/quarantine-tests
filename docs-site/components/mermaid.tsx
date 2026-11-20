'use client';

import { useEffect, useId, useState } from 'react';
import { useTheme } from 'next-themes';

/** Renders a Mermaid diagram on the client, following the light/dark theme. */
export function Mermaid({ chart }: { chart: string }) {
  const id = `mermaid-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const { resolvedTheme } = useTheme();
  const [svg, setSvg] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void import('mermaid').then(async ({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        fontFamily: 'inherit',
        theme: resolvedTheme === 'dark' ? 'dark' : 'default',
      });
      try {
        const result = await mermaid.render(id, chart);
        if (!cancelled) {
          setSvg(result.svg);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [chart, id, resolvedTheme]);

  if (error) {
    return (
      <pre className="my-6 overflow-x-auto rounded-lg border p-4 text-sm text-fd-muted-foreground">
        Diagram failed to render: {error}
      </pre>
    );
  }

  return (
    <div
      className="not-prose my-6 flex justify-center overflow-x-auto [&_svg]:max-w-full"
      // Mermaid output with securityLevel 'strict' (labels sanitized).
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
