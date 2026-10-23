# Changelog

## 0.5.0 — Small businesses and everyday life

- Default research audiences now cover small businesses and everyday people. Developer tools remain selectable with `--audiences developer_tools`.
- Search freelancing, household, cooking, parenting, travel, and home-maintenance communities with audience-specific plans; add bounded public Shopify and Monzo forum reads without credentials.
- Fetch complete forum opening posts, preserve provenance, strip quoted intent, and isolate per-forum rate/access failures while retaining successful evidence.
- Recognize nontechnical recurring burdens and coordination needs; expose topic-based audience labels and filtering without treating the community as proof of demand.
- Generate evidence-led research briefs for nontechnical opportunities instead of unrelated software templates.
- Version saved analysis to 5, include audience scope in cache compatibility, and retain Reddit/X disabled. Remove stale developer-only `.env` overrides to adopt the new defaults.

## 0.4.0 — Community discovery with historical evidence

- Search Ask HN and comment text instead of sampling current story feeds. Query recent and historical periods separately, with bounded requests and original author/thread attribution.
- Default to 180 days; expose evidence age and remove recency score bonuses. Add Software Recommendations to Stack Exchange defaults and use relevance ordering.
- Keep GitHub issues as supporting evidence, with a separate CLI view. Related issues cannot create opportunities or increase primary recurrence counts.
- Tighten firsthand intent checks to reject generic comparisons, tutorials, recruiting, research solicitations, and product promotions.
- Report cluster age spans and clearly label thematic repeats and supporting matches as unverified.
- Upgrade analysis format to version 4; run `metis analyze` to refresh saved results. Existing `.env` source/site/query overrides remain authoritative; use the new `.env.example` values to adopt the new discovery defaults.

## 0.3.0 — 2026-10-23

- Rank opportunities using explicit intent, workflow burden, context, and recency, with a score breakdown. Separate support/weak signals and noise into review candidates; suppress common negations, promotions, hiring, bots, quoted examples, and code blocks.
- Group subject synonyms and needs across sources. Track threads, author accounts, and distinct texts; avoid boosting same-thread replies, one author's reposts, and exact copies as repeated demand. Order idea hypotheses by intent and repeat evidence instead of cross-platform upvotes.
- Sample bounded comments from promising HN, GitHub, and Stack Exchange discussions with separate IDs and original attribution. Keep provider rate-limit and time-budget handling across both phases. Reddit and X remain disabled.
- Add local `review`, `evaluate`, and `candidates` commands. Evaluate only explicit labels and exclude stale reviews when evidence changes.
- Extend offline regression coverage for scoring, grouping, comments, review persistence, and evaluation. Stored analysis has `analysis_version: 3`; run `metis analyze` after upgrading.

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
