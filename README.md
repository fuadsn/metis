# Metis — Market Intelligence System

[![Checks](https://github.com/fuadsn/metis/actions/workflows/checks.yml/badge.svg)](https://github.com/fuadsn/metis/actions/workflows/checks.yml)

Find startup and developer-tool opportunities in public discussions. Metis collects evidence, identifies explicit pain and buying-intent phrases, groups related posts, and exports leads with excerpts and links for review.

V1 uses **Hacker News, GitHub Issues, and Stack Exchange** with no API fees or required credentials. Reddit and X adapters are retained but disabled by default for a later version.

## Sources

| Source | Focus | V1 status / access |
| --- | --- | --- |
| Hacker News | Ask HN, Show HN, new/top/best stories | Enabled; no credentials or API fees |
| Reddit | SaaS, startups, smallbusiness, webdev, devops, selfhosted | Disabled; requires approved access, free eligibility varies |
| X | People seeking tools, alternatives, and missing products | Disabled; paid API credits required |
| GitHub Issues | Public, open workflow/integration feature requests and workarounds | Enabled; public reads, token optional |
| Stack Exchange | Stack Overflow and Server Fault workflow/deployment questions | Enabled; public reads, API key optional |

These are research leads, not verified buyers. GitHub issues and Stack Exchange questions can indicate ordinary support needs rather than product demand. Collection samples recent listings, the first page per configured search, and a few comments from selected discussions; it is not an exhaustive archive.

## Setup

Python 3.9 or later:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
# Optional: copy only if you do not already have a .env file.
cp .env.example .env
```

The default sources work without credentials. `.env` is optional for community/query overrides and is ignored by Git. Setting a Reddit or X credential does not enable that source.

An editable checkout reads `.env` from the repository root. An installed wheel reads `.env` from the current working directory. Set `METIS_ENV_FILE=/absolute/path/to/metis.env` before invoking Metis to choose a specific file, including for scheduled runs. Exported environment variables take precedence over the file.

## Usage

```bash
# Configuration readiness only; this does not verify provider access.
metis sources

# Public sources, no credentials needed (subject to provider limits).
metis run --sources hackernews,github,stackexchange --limit 50 --days 30

# Default v1: Hacker News, GitHub Issues, and Stack Exchange only.
metis run --limit 50

metis collect --sources github --limit 20
metis analyze --days 30
metis leads --limit 20
metis leads --source github --limit 10
metis candidates --quality support --limit 10
metis clusters
metis ideas

# Collect posts without making any comment requests:
metis run --limit 30 --comment-threads 0

# Same commands without installation:
python cli.py sources

# Run immediately and every six hours while the process remains alive:
python main.py --watch --limit 50
```

`METIS_SOURCES` sets the default source list. Communities and queries are configurable in `.env.example`. Search overrides are JSON arrays, for example:

```dotenv
METIS_GITHUB_QUERIES='["repo:your-org/your-tool label:enhancement"]'
METIS_STACKEXCHANGE_QUERIES='["deployment workaround", "manual workflow"]'
```

GitHub searches always restrict results to public open issues. Lookback is based on creation time. Limits are ceilings, not guaranteed result counts. Each source has a shared 60-second budget for posts and comments (an in-flight request may finish later). Post collection allows at most 10 HTTP attempts, except HN, which allows `limit + 5`. Rate limits stop that source for the current run. Transient network/server failures receive bounded retries.

## Selective comments

By default, Metis samples up to **3 comments from 3 promising threads per free source**. It selects opportunity candidates first; relevant Ask HN questions can also qualify because the need may appear only in replies. It samples top-level HN replies in display order, the first GitHub issue comments, and Stack Exchange question comments ordered by votes. It skips deleted HN comments and GitHub bot replies. Nested HN replies, pull-request reviews, and Stack Exchange answers are not fetched.

`--comment-threads` / `METIS_COMMENT_THREADS` accepts 0–5; zero disables comment collection. `--comments-per-thread` / `METIS_COMMENTS_PER_THREAD` accepts 1–10. The comment phase allows at most `threads × comments` additional HTTP attempts on HN and `threads` on GitHub or Stack Exchange, including retries. The default adds at most 9 HN attempts and 3 attempts for each other source, within the same time budget.

Comments have their own IDs, authors, timestamps, and URLs, plus `kind: comment`, `parent_id`, and `parent_url`. A parent's title supplies subject context but never buying intent to a reply. Collection summaries separate `collected` posts from `comments_collected`; `new`, `updated`, and `total_stored` count both. A comment failure keeps the collected posts and reports a partial result.

## Output and failure handling

CLI stdout is JSON; progress logs go to stderr. Exit codes: `0` success, `2` partial collection, `1` failure. Reddit/X appear as `disabled` in the default configuration. If explicitly enabled later, missing credentials appear as `unconfigured` while other sources continue. `metis sources` reports configuration readiness, not verified API permission.

A completely failed collection preserves the last analysis on disk. The failed run includes cached analysis only when its analysis version, `selected_sources`, and `window_days` match the request, with `analysis_reused: true`. Retrieval commands return the saved analysis scope, timestamp, and `latest_collection`; `collection_newer_than_analysis` flags a subsequent collection attempt. Check these fields before treating saved leads as current. Watch mode reports temporary storage errors as JSON and tries again at the next scheduled interval. After upgrading, run `metis analyze` to refresh older saved output with the current rules.

Each lead includes `source`, `community`, source-qualified `post_id`, full body, discussion URL, author, creation time, matched phrases, evidence excerpt, lead type, `lead_quality`, and a heuristic priority score with `score_breakdown`. `leads` contains opportunity candidates; `candidates` also exposes support/weak signals and noise for review. Popularity alone does not qualify a post. Scores are not purchase probabilities.

The rules favor explicit willingness to pay, searches for products, unmet capabilities, and manual or costly workflows in startup/developer contexts. They discount ordinary support, common negations, promotions, hiring, bots, code samples, and blockquotes. Recency contributes at most five points. These are English rules and can miss intent or mistake implementation tasks for market demand.

Groups combine subject synonyms (such as deployment/CI/CD and authentication/SSO) with need categories such as automation, cost, or reliability. They expose evidence links, thread counts, and source-qualified author-account counts. A repeated-need flag requires at least two distinct threads, accounts, and texts; a conservative selection avoids boosting repeated replies, reposts by one author, or exact copies. Accounts across platforms are not verified as distinct people. Unknown topics do not receive a repeated-need boost. This is rule-based grouping, not semantic clustering.

Idea suggestions remain fixed-template hypotheses with `hypothesis: true` and `scoring_method: fixed_template`. Their demand ordering now follows intent and repeat evidence rather than comparing platform upvotes. Novelty/build/market template scores remain unvalidated.

## Review lead quality

Review the original evidence, then label posts locally:

```bash
metis candidates --limit 30
# Replace the example ID with a post_id from your own output.
metis review github:123 --label opportunity --note "Explicit need for a paid workflow tool"
metis review github:456 --label support
metis review hackernews:789 --label noise
metis evaluate
```

Labels are `opportunity`, `support`, or `noise`. Reviews stay in SQLite and do not post anything to the source platform or automatically retrain the rules. Evaluation reports a confusion matrix and opportunity precision/recall on your labelled sample only. Metrics are null when their denominator is zero. Reviews of edited evidence are marked stale and excluded until reviewed again. The test suite's illustrative examples are regression checks, not an independent accuracy benchmark.

## Deferred sources

Reddit and X code remains available for later use, but neither runs in the default v1 configuration. Re-enabling requires an explicit change to `METIS_SOURCES` or a `--sources` override as well as the necessary access.

Reddit offers both free and paid access. Eligibility depends on use and approval; commercial use requires permission and may require a contract. See [Reddit access and fees](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data). The retained adapter uses approved OAuth access; Pushshift and PRAW are not dependencies.

Reddit also documents [public RSS feeds](https://www.reddit.com/wiki/rss/). A small subreddit-feed check succeeded without credentials on 2026-10-21. RSS is not integrated or enabled in v1; it is a candidate for later evaluation, not a replacement for approved API access.

X uses paid [recent search](https://docs.x.com/x-api/posts/search/introduction), covering at most seven days, with [usage-based credits](https://docs.x.com/x-api/getting-started/pricing). No X requests are made by the v1 defaults.

## Storage

Evidence is upserted into `data/metis.sqlite3` by source and external ID. Subsequent collections refresh engagement without inflating evidence counts. Stack Exchange IDs also include their site. Old `data/raw/*.json` snapshots are imported once, transactionally, without changing the originals. Use `metis analyze --days 365` to include older locally collected evidence within the past year. Analysis reads all stored posts in the selected sources and window; collection limits do not truncate it.

Latest analysis and collection summaries are exported to `data/processed/`. Run history is retained in SQLite. Set `METIS_DATA_DIR` for a different location. An installed wheel defaults to `$XDG_DATA_HOME/metis` or `~/.local/share/metis`; an editable checkout uses its `data/` directory.

## Development

```bash
python -m pip install -e '.[dev]'
python -m ruff check .
python -m pytest -q
python -m build
python scripts/check_wheel.py dist/metis-0.3.0-py3-none-any.whl
```

GitHub Actions runs these checks on Python 3.9 and 3.14 for pushes and pull requests. Tests use mocked HTTP responses and temporary databases; they do not consume API credits. The wheel check installs dependencies from PyPI, then verifies configuration, local analysis, and storage outside the checkout without contacting source platforms. It does not schedule collection.

`pipeline.py` is shared by the CLI, scheduler, and legacy agent command wrappers. Despite their historical filenames, `mcp_server.py` and `mcp_simple.py` are JSON command adapters, not MCP protocol servers. See [CHANGELOG.md](CHANGELOG.md) for the v1 changes.

## Remaining limitations

Incremental collection checkpoints, exhaustive pagination, full conversation trees, semantic grouping, and an independently reviewed quality benchmark remain future work. Sampling only promising threads can miss opportunities whose root post has no detectable signal. Reddit and X remain deferred.
