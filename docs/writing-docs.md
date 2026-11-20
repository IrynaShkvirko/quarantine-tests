# Writing docs

How the documentation is organized and how to write a page. The site is built with Fumadocs from `docs-site/`.

## Two tabs, two sources

| Tab | Audience | Source | Edited in |
|-----|----------|--------|-----------|
| **Docs** | People using the system: teams, QA, platform engineers | `docs-site/content/docs/**/*.mdx` | `docs-site/` |
| **Engineering** | People building it, and coding agents | `docs/**/*.md` (synced into the site by `docs-site/scripts/sync-engineering.mjs`) | `docs/` |

- `docs/architecture.md` is the design spec and the source of truth. Requirements, plans, agents and skills reference it by section number (§3.4), so it stays one file.
- User pages explain how to use a feature and link to the spec section for the full rules. They don't copy the spec.
- Never edit `docs-site/content/engineering/`; it is generated and gitignored.

## Page template (Docs tab)

```mdx
---
title: Flaky evidence
description: One sentence on what the reader gets from this page.
---

Opening paragraph: the answer or the main point, in two or three sentences.

## <Main section>
Steps (<Steps>/<Step>), explanation, tables, a diagram if the topic has a shape.

<Tabs items={['GitHub Actions', 'Jenkins']}> ... </Tabs>     for CI-specific snippets
<Tabs items={['pytest', 'Playwright', 'Jest']}> ... </Tabs>  for framework-specific snippets

<Callout title="..."> limits, gotchas, shadow-mode notes </Callout>

## Next steps
<Cards> 2–3 <Card title href> links </Cards>
```

Pages not written yet keep the stub: a "Planned for M#" callout linking to the spec sections, and the list of what the page will cover.

## Style

- First sentence of a page and of each section states its point.
- Short sentences (under 25 words), plain words, no marketing language.
- Numbers with units; real file names, commands and config keys in backticks.
- Diagrams as fenced `mermaid` code blocks; flows, states and architecture are drawn, not described.
- MDX treats `<` and `{` in text as code: write them inside backticks, or escape them (`\<`, `\{`).

## Adding a page

1. Create the `.mdx` file in the right section folder of `docs-site/content/docs/`.
2. Add its slug to that folder's `meta.json` (order = sidebar order).
3. Run `pnpm dev` in `docs-site/` and check the page, its diagrams and links.
4. `pnpm check:mermaid` must pass before the PR.

## Docs per milestone

Each milestone's definition of done includes its pages (see the Milestones tab of the implementation plan). A feature isn't done until its pages move from "Planned" to written.
