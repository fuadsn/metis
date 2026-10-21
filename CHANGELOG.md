# Changelog

## 0.2.0 — 2026-10-21

First version focused on startup and developer-tool leads from free public sources.

- Enable Hacker News, GitHub Issues, and Stack Exchange by default without required credentials. Retain Reddit OAuth and X recent-search adapters, disabled until explicitly selected.
- Share the collection and analysis pipeline across CLI, scheduler, and legacy JSON adapters. Report per-source errors, partial results, and configuration readiness.
- Normalize source IDs, bodies, authors, timestamps, and discussion links. Preserve evidence excerpts and URLs through lead generation.
- Upsert evidence in SQLite and migrate legacy JSON snapshots once without changing the originals. Keep run history and atomic JSON exports.
- Require explicit pain or intent signals instead of accepting popularity alone. Fix substring topic matches and label generated ideas as template-based hypotheses.
- Bound requests and retries, respect provider rate-limit responses, and suppress HTTP logs that could contain query-string credentials.
- Preserve saved analysis after failed collection without returning results from an incompatible source/window. Expose newer collection attempts when retrieving saved leads.
- Support dotenv settings for installed wheels and an explicit METIS_ENV_FILE override. Recover from temporary storage failures in watch mode.
- Include root modules in distributable packages, remove generated package metadata from version control, and add tests, lint, build, and isolated wheel checks in GitHub Actions.

Collection samples posts; full comment threads, exhaustive pagination, semantic clustering, and buyer validation remain outside this version.
