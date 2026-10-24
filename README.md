# Metis — Market Intelligence System

[![Checks](https://github.com/fuadsn/metis/actions/workflows/checks.yml/badge.svg)](https://github.com/fuadsn/metis/actions/workflows/checks.yml)

Find unmet needs faced by small businesses and everyday people in public discussions. Metis searches community discussions for firsthand problems, recurring work, and requests for solutions. It groups specific tasks and obstacles, screens for economic evidence, and exports recurring opportunity hypotheses with dates, excerpts, and links. GitHub issues remain supporting research.

V1 uses **Hacker News, topic communities on Stack Exchange, and supporting GitHub Issues** with no API fees or required credentials. Reddit, X, and the product-specific Shopify/Monzo forum adapter are retained but disabled by default.

The optional source pilot adds **YouTube comments** through a free-quota API key, plus **manual research notes from UK Business Forums, MoneySavingExpert, and Capterra**. Manual notes are stored separately from scored posts. See [setup and pilot findings](docs/source-pilot.md).

## Sources

| Source | Focus | V1 status / access |
| --- | --- | --- |
| Hacker News | Text searches of Ask HN and discussion replies, including older threads | Enabled; no credentials or API fees |
| Reddit | SaaS, startups, smallbusiness, webdev, devops, selfhosted | Disabled; requires approved access, free eligibility varies |
| X | People seeking tools, alternatives, and missing products | Disabled; paid API credits required |
| GitHub Issues | Public open issues relevant to the selected audiences, as supporting evidence | Enabled; public reads, token optional |
| Stack Exchange | Freelancing, The Workplace, Parenting, Seasoned Advice (cooking), Home Improvement, Travel, and Personal Finance & Money | Enabled; public reads, API key optional |
| Product forums (`discourse`) | Shopify and Monzo workflow problems; useful reports can be candidates | Collection disabled by default; public access policy must permit reads |
| YouTube (`youtube`) | Comments on focused business and everyday-life videos | Optional; YouTube Data API key and allocated quota required |
| UK Business Forums / MoneySavingExpert / Capterra | Linked analyst notes on business workflows, household tasks, and product reviews | Manual pilot only; no automated collector |

These are research leads, not verified buyers. GitHub issues and Stack Exchange questions can indicate ordinary support needs rather than product demand. The default lookback is **180 days**. HN and Stack Exchange sample the last 30 days and days 31–180 separately, ordered by search relevance within each band. GitHub uses best-match search over the requested window. Searches use the first page only; this is a sample, not an exhaustive archive.

Sources are selected for task-related discussions, complete evidence with dates and author/thread attribution, and usable public access. Convenience of an endpoint is insufficient. `metis sources` explains each source's selection reason, evidence role, and coverage limit. HN remains technology-biased; Stack Exchange contains many advice questions. These sources do not represent the whole market.

## Audiences

The default is **small businesses and everyday life**. Problems can concern services, physical products, coordination, or paperwork; technical vocabulary is not required.

- `small_business`: appointments, invoices, inventory, shipping, and client work.
- `everyday_life`: family coordination, meals, travel, home maintenance, and household administration.
- `developer_tools`: optional technical research using the earlier developer-focused searches.

Use `--audiences small_business,everyday_life` on `run`, `collect`, or `analyze`; use `--audience everyday_life` to filter saved leads, clusters, or ideas. Set `METIS_AUDIENCES` for persistent defaults. Leads must match the selected audience scope. `candidates` still exposes collected evidence outside that scope for auditing.

Audience labels describe the subject of a post using explicit text and community context, not a verified personal profile. Related labels can overlap. `primary_audience` uses the title, explicit terms, and community context to choose the main topic; lead inclusion and audience counts use that primary label, so incidental words such as software “clients” do not by themselves turn developer problems into business leads. A community label alone cannot qualify a post: firsthand intent or burden is still required. Existing site/query overrides in `.env` remain authoritative; remove old developer-only overrides to adopt the new defaults. `metis sources` shows the effective Stack Exchange search plan.

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
metis run --sources hackernews,github,stackexchange --limit 50 --days 180

# Default v1: free sources, small businesses and everyday life.
metis run --limit 50

metis collect --sources github --limit 20
metis analyze --days 180
metis leads --limit 20
# Preliminary problem candidates, including those excluded by the commercial filter:
metis problems --limit 20
metis leads --audience everyday_life --limit 10
metis run --audiences developer_tools --sources hackernews,github,stackexchange --limit 30
metis supporting_evidence --source github --limit 10
metis candidates --quality support --limit 10
metis clusters
metis ideas

# Optional YouTube pilot, after setting YOUTUBE_API_KEY locally:
metis run --sources youtube --limit 50 --days 180

# Local research notes; no network calls or automatic lead scoring:
metis research-import /path/to/research-notes.json
metis research --limit 20

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
METIS_HACKERNEWS_QUERIES='["\"looking for\" \"tool\"", "\"manually\" \"every\""]'
METIS_STACKEXCHANGE_QUERIES='["workflow", "alternative"]'
```

GitHub searches always restrict results to public open issues. Lookback is based on creation time. Limits are ceilings, not guaranteed result counts. Each source has a shared 60-second budget for posts and comments (an in-flight request may finish later). Search collection allows at most 20 HTTP attempts for HN, Stack Exchange, and YouTube, 30 for public forums including full-post reads, and 10 for the other sources, including retries. Custom query lists that exceed the cap produce an explicit partial result; YouTube explicitly samples only the first four discovery queries. `--limit` caps search matches per source, including HN comment matches; bounded thread enrichment is additional. For YouTube it caps collected comments. Rate limits stop that source for the current run. Transient network/server failures receive bounded retries.

## Deferred product forums

The retained `discourse` collector targets [Shopify Community](https://community.shopify.com/) and [Monzo Community](https://community.monzo.com/). Firsthand workflow problems can qualify as candidates for add-ons, services, or other solutions. Version 0.7 removes the blanket supporting-only rule from 0.6. Ordinary support and promotional posts still fail the intent rules. A product complaint alone does not verify a broader market or willingness to pay. Reanalyze with `--sources hackernews,github,stackexchange,discourse` to include saved forum evidence without collecting again.

If explicitly enabled for collection, the adapter checks `robots.txt` before searching or fetching full posts; denied, redirected, or unreadable policy stops that forum. At the October 23, 2026 check, both forums disallowed their search paths. It never switches identities or endpoints to bypass a denial. When access permits, requests are bounded to one query per forum and age band and up to five full opening posts per search, with a shared 30-attempt budget. Search snippets are never scored.

The source review also checked general forums: the smaller `businessforum.uk` RSS feed exposed truncated bodies and activity dates belonging to old threads; this is a different site from `ukbusinessforums.co.uk`. Direct access to UK Business Forums' robots policy returned 403, and MoneySavingExpert failed in the local HTTP runtime. They are manual research sources in the pilot. Oh My Dollar/Penny Hoarder searches returned no sampled matches and their crawl policies restrict search. None was added as an automated collector.

## Optional YouTube and manual research

YouTube searches up to four audience-specific video queries, two results each, then samples one page of the newest top-level comments per unique video. Set `METIS_YOUTUBE_VIDEO_IDS` to up to eight known video IDs to skip discovery. `METIS_YOUTUBE_COMMENTS_PER_VIDEO` controls the page size (1–100, default 25). These settings are separate from the existing HN/GitHub/Stack Exchange enrichment flags. `--days` filters original comment dates, so a current edit does not make an old comment new; older videos remain eligible. Replies and video descriptions are not collected or scored. The key stays in an HTTP header rather than request URLs. Missing keys produce `unconfigured`; disabled comments skip that video; quota or access errors stop the source.

`metis research-import` accepts an explicit local JSON batch for the three pilot sites. It validates every note before writing, deduplicates by source URL and locator, and never fetches links. `metis research` reports source yield and distinguishes problem reports, researcher questions, existing solutions, and positive experiences. Original dates, unknown-date explanations, review incentives, caveats, and next validation steps are retained. Notes are analyst summaries and cannot enter lead scoring or repeated-demand counts. This is a manual pilot, not background monitoring of these websites. [Import schema and findings](docs/source-pilot.md).

## Selective comments

HN searches comment text directly, including nested replies, within the search-match budget. This can find firsthand needs even when the original story is news or a product launch. Additionally, Metis samples up to **3 comments from 3 promising threads each on HN, GitHub, and Stack Exchange**. It selects opportunity candidates first; relevant Ask HN questions can also qualify because the need may appear only in replies. It samples top-level HN replies in display order, the first GitHub issue comments, and Stack Exchange question comments ordered by votes. It skips deleted HN comments and GitHub bot replies. Thread enrichment does not walk nested HN replies; nested replies are available through text search. Pull-request reviews and Stack Exchange answers are not fetched.

`--comment-threads` / `METIS_COMMENT_THREADS` accepts 0–5; zero disables both HN comment search and thread enrichment. `--comments-per-thread` / `METIS_COMMENTS_PER_THREAD` accepts 1–10. The comment phase allows at most `threads × (1 + comments)` additional HTTP attempts on HN (one root lookup plus replies) and `threads` on GitHub or Stack Exchange, including retries. The default adds at most 12 HN attempts and 3 attempts for each other source, within the same time budget.

Comments have their own IDs, authors, timestamps, and URLs, plus `kind: comment`, `parent_id`, and `parent_url`. A parent's title supplies subject context but never buying intent to a reply. For HN search results, `parent_id` identifies the root conversation; the immediate parent is retained in metadata when available. `comment_requests` counts enrichment requests, while direct comment searches count toward total `requests`. Collection summaries separate `collected` posts from `comments_collected`; `new`, `updated`, and `total_stored` count both. A comment failure keeps the collected posts and reports a partial result.

## Output and failure handling

CLI stdout is JSON; progress logs go to stderr. Exit codes: `0` success, `2` partial collection, `1` failure. Reddit/X/product forums appear as `disabled` in the default configuration. If explicitly enabled later, missing credentials appear as `unconfigured` while other sources continue. `metis sources` reports configuration readiness, not verified API permission.

A completely failed collection preserves the last analysis on disk. The failed run includes cached analysis only when its analysis version, `selected_sources`, `selected_audiences`, and `window_days` match the request, with `analysis_reused: true`. Retrieval commands return the saved analysis scope, timestamp, and `latest_collection`; `collection_newer_than_analysis` flags a subsequent collection attempt. Check these fields before treating saved leads as current. Watch mode reports temporary storage errors as JSON and tries again at the next scheduled interval. After upgrading, run `metis analyze` to refresh older saved output with the current rules.

Each lead includes `source`, `community`, source-qualified `post_id`, full body, discussion URL, author, creation time, matched phrases, evidence excerpt, lead type, `lead_quality`, and a heuristic priority score with `score_breakdown`. `leads` contains primary community opportunity candidates that pass the commercial filter. `problems` preserves all preliminary in-scope problem candidates before that filter; these can still include advice or weak signals. Every candidate carries `commercial.eligible`, evidence excerpts, and exclusion reasons. Every GitHub issue/comment has `evidence_role: supporting` and appears in `supporting_evidence` when it has a non-noise signal; it cannot create an opportunity or increase repeat/priority counts. `source_context` and `coverage_limit` explain source bias. `validation_stage` describes the strength of the problem signal; `willingness_to_pay` distinguishes an unverified statement in the text from no established payment signal. Neither verifies a buyer. `candidates` exposes all quality classes and both evidence roles for review. Popularity alone does not qualify a post. Scores are not purchase probabilities.

`community_coverage` in analysis and retrieval output reports analyzed records, primary candidates, supporting records, and noise per community, including empty selected Stack Exchange communities. These are observed yields, not measured precision. Clusters expose `independent_community_count`, `independent_platform_count` (collector sources), and `corroboration`: `not_established`, `same_community_problem`, `cross_community_problem`, or `cross_platform_problem`. Counts use the selected independent reports, not every source present in a group. Supporting product evidence never changes these counts. These are rule-based matches requiring review, not verified identities or demand.

The rules favor explicit willingness to pay, searches for products, unmet capabilities, and recurring or costly work in the selected business, household, or developer contexts. They discount ordinary support, common negations, promotions, hiring, bots, code samples, and blockquotes. Recency adds no score. `age_days`, `freshness` (recent/historical/unknown), and `current_need_verified: false` keep age separate from intent. Historical requests need a fresh check before outreach; publication age alone does not show that a problem persists. Headlines that merely describe alternatives, recruiting, surveys, and tutorial instructions are discounted. These are English rules and can miss intent or mistake implementation tasks for market demand.

Grouping requires the **same task, obstacle, and primary audience**, rather than a shared topic such as “budget” or “automation.” For example, bank CSV import problems stay separate from monthly budget adjustments, and entering invoices stays separate from chasing overdue invoices. Each group includes `problem_signature`, an obstacle excerpt, and `match_explanation`. Broad topic/need labels are for display only. Unknown tasks, ambiguous posts describing multiple tasks, and posts without a clear obstacle stay separate. Parent titles never supply a comment's task or obstacle.

The current English task vocabulary covers transaction imports, budget maintenance, physical inventory counts, inventory synchronization, invoice entry/reconciliation/collection, appointments, childcare shift coverage, school payments, meal plans, spreadsheet tax filing, and software releases/rollbacks. This deliberately bounded vocabulary can miss valid matches and opportunities; it is not semantic understanding. Add task rules with positive paraphrases and nearby negative cases when reviewing missed opportunities.

A recurring group needs **at least two distinct accounts, threads, and nonduplicate texts**. Exact and long near-duplicate copies are collapsed before ranking; later copies cannot add a platform or economic evidence. Unknown authors do not establish independence. `independent_evidence_ids` and `excluded_from_repeat` explain the count. Accounts on different platforms are not verified as different people. `evidence_span_days` uses independent reports; age alone does not establish recurrence. Matching GitHub evidence attaches by task/obstacle/audience and never contributes to commercial eligibility, repeat counts, or ranking.

The commercial filter is on by default:

- **Individual lead:** an unresolved primary problem plus stated interest in paying for a solution, spending on an existing solution, quantified recurring time cost, or inferred recurring business labor. An unrelated car budget, a satisfied workaround, a free-only request, and ordinary advice do not establish commercial demand. Economic excerpts retain their `stated` or `inferred` basis.
- **Idea:** at least two independent matching problem reports, with either one stated economic signal or recurring business labor reported by at least two independent accounts. A single buyer request stays a lead until corroborated. Repetition alone without economic evidence stays research.
- **Priority:** qualified ideas come first, then independent cross-platform corroboration, recurrence, and intent. Multiple platforms strengthen the case but are not mandatory. Recency and popularity add no points.

All ideas are evidence briefs (`scoring_method: evidence_brief`) describing the task, obstacle, desired outcome, linked economic evidence, and validation questions. Generic developer templates and invented novelty/build/market scores have been removed. `hypothesis: true` and `payment_verified: false` remain explicit: a statement about paying is not a verified purchase, and labor savings are not proof of willingness to pay. Zero ideas is a valid result when the sample does not meet the filter. `commercial_filter` in analysis/retrieval output explains the requirements and excluded counts.

## Review lead quality

Review the original evidence, then label posts locally:

```bash
metis candidates --limit 30
# Replace the example ID with a post_id from your own output.
metis review hackernews:123 --label opportunity --note "Explicit need for a paid workflow tool"
metis review github:456 --label support
metis review hackernews:789 --label noise
metis evaluate
```

Labels are `opportunity`, `support`, or `noise`. Reviews stay in SQLite and do not post anything to the source platform or automatically retrain the rules. Evaluation reports a confusion matrix and opportunity precision/recall for the underlying intent classifier on your labelled sample only; it does not measure grouping accuracy, commercial-filter precision, or market viability. Metrics are null when their denominator is zero. Reviews of edited evidence are marked stale and excluded until reviewed again. The test suite's illustrative examples are regression checks, not an independent accuracy benchmark.

## Deferred sources

Reddit and X code remains available for later use, but neither runs in the default v1 configuration. Re-enabling requires an explicit change to `METIS_SOURCES` or a `--sources` override as well as the necessary access.

Reddit offers both free and paid access. Eligibility depends on use and approval; commercial use requires permission and may require a contract. See [Reddit access and fees](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data). The retained adapter uses approved OAuth access; Pushshift and PRAW are not dependencies.

Reddit also documents [public RSS feeds](https://www.reddit.com/wiki/rss/). A small subreddit-feed check succeeded without credentials on 2026-10-21. RSS is not integrated or enabled in v1; it is a candidate for later evaluation, not a replacement for approved API access.

X uses paid [recent search](https://docs.x.com/x-api/posts/search/introduction), covering at most seven days, with [usage-based credits](https://docs.x.com/x-api/getting-started/pricing). No X requests are made by the v1 defaults.

## Storage

Evidence is upserted into `data/metis.sqlite3` by source and external ID. Subsequent collections refresh engagement without inflating evidence counts. Stack Exchange and public-forum IDs and author-account counts also include their host/site. Old `data/raw/*.json` snapshots are imported once, transactionally, without changing the originals. Use `metis analyze --days 365` to include older locally collected evidence within the past year. Analysis reads all stored posts in the selected sources and window; collection limits do not truncate it.

Latest analysis and collection summaries are exported to `data/processed/`. Run history is retained in SQLite. Set `METIS_DATA_DIR` for a different location. An installed wheel defaults to `$XDG_DATA_HOME/metis` or `~/.local/share/metis`; an editable checkout uses its `data/` directory.

## Development

```bash
python -m pip install -e '.[dev]'
python -m ruff check .
python -m pytest -q
python -m build
python scripts/check_wheel.py dist/metis-0.8.0-py3-none-any.whl
```

GitHub Actions runs these checks on Python 3.9 and 3.14 for pushes and pull requests. Tests use mocked HTTP responses and temporary databases; they do not consume API credits. The wheel check installs dependencies from PyPI, then verifies configuration, local analysis, and storage outside the checkout without contacting source platforms. It does not schedule collection.

`pipeline.py` is shared by the CLI, scheduler, and legacy agent command wrappers. Despite their historical filenames, `mcp_server.py` and `mcp_simple.py` are JSON command adapters, not MCP protocol servers. See [CHANGELOG.md](CHANGELOG.md) for the v1 changes.

## Remaining limitations

Incremental collection checkpoints, exhaustive pagination, full conversation trees, semantic grouping, and an independently reviewed quality benchmark remain future work. Search wording and relevance ranking can miss useful discussions or overrepresent some themes. Rules still need human review and do not establish willingness to purchase. Reddit and X remain deferred.
