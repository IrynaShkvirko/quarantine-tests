# Docs site

Fumadocs (Next.js) site for the Flaky Test Quarantine system, exported as static HTML.

- **Docs tab** (`/docs`): user docs in `content/docs/` — edit here.
- **Engineering tab** (`/engineering`): rendered from the repo's `docs/` folder by `scripts/sync-engineering.mjs` — edit `docs/`, not `content/engineering/` (generated, gitignored).

```bash
pnpm install
pnpm dev            # http://localhost:3000/docs
pnpm build          # static site in out/
pnpm check:mermaid  # render every Mermaid diagram (CI runs this)
```

Writing guide: `docs/writing-docs.md` (also at `/engineering/writing-docs`).

## Versions

Pinned to the Fumadocs 16 set that the Headroom docs site builds with (`fumadocs-core` / `fumadocs-ui` 16.18.3, `fumadocs-mdx` 15.5.2, Next.js 16). The layout, page actions ("Copy Markdown", "Open"), `llms.txt` routes and source setup are adapted from `github.com/headroomlabs-ai/headroom/tree/main/docs` (Apache-2.0).

Differences from Headroom's site:
- **Static export** for GitHub Pages (`output: 'export'`, static search index) instead of Vercel.
- **Two tabs** (Docs, Engineering) with two content collections; Engineering is synced from `../docs`.
- **Mermaid diagrams render** (Headroom only highlights them) via `lib/remark-mermaid.mjs` and `components/mermaid.tsx`.

## First build checklist (M0-13)

The scaffold was written without installing packages. On the first `pnpm install && pnpm build`:

1. Commit the lockfile; keep the Fumadocs versions above unless a newer patch is needed.
2. Check `pnpm typecheck` (runs `fumadocs-mdx`, `next typegen`, `tsc`).
3. Check that the synced `.md` engineering pages, Mermaid diagrams, page actions and `/llms.txt` work in `out/`.
4. API reference pages come in M1 with `fumadocs-openapi` from the FastAPI schema.
