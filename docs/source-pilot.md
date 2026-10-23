# Broader source pilot — 23 October 2026

The pilot covers business and household problems through YouTube comments, two focused forums, and product-review research. It supplements the existing public sources. Reddit and X remain disabled. No paid API, subscription, or scheduler was started.

## Access and operating mode

| Source | Pilot mode | Observed access |
| --- | --- | --- |
| YouTube | Optional API collector | Implemented and tested with simulated API responses; live collection needs `YOUTUBE_API_KEY` |
| UK Business Forums | Manual linked notes | Direct robots request returned HTTP 403; public pages were readable in web research |
| MoneySavingExpert | Manual linked notes | Direct HTTPS failed in the tested local runtime; public pages were readable in web research |
| Capterra | Manual review notes | Direct review page returned HTTP 403; reviews were available through web research |

These are observations from this environment, not claims that a site is unavailable to everyone. Manual research has no scheduled collection. Mumsnet was also evaluated but not added: its [terms](https://www.mumsnet.com/i/terms-of-use) restrict unlicensed scraping. A readable page or permissive generic robots rule alone is not enough to select an automated source.

## YouTube setup

Follow Google's [getting started guide](https://developers.google.com/youtube/v3/getting-started): create/select a Google Cloud project, enable YouTube Data API v3, and create an API key restricted to that API. Put `YOUTUBE_API_KEY` in the ignored local `.env`, never in a commit or chat. Public comment reads use an API key, not channel OAuth.

```bash
metis sources --sources youtube
metis run --sources youtube --limit 50 --days 180
metis leads --source youtube
```

To include YouTube in regular runs, explicitly add `youtube` to `METIS_SOURCES`. Having a key alone does not enable it. The allocated API quota is suitable for a small free pilot; Metis does not buy quota or retry quota/access denials. Google's current [search reference](https://developers.google.com/youtube/v3/docs/search/list) lists a separate search quota, and [commentThreads.list](https://developers.google.com/youtube/v3/docs/commentThreads/list) describes comment quota and limits. Check the project's actual allocation before scheduling.

Defaults: four audience-specific queries at most, two videos per query, eight unique videos at most, one page of up to 25 top-level comments per video, and 20 total HTTP attempts including retries. The per-source deadline is 60 seconds. `--limit` caps comments across all videos. Only comments created within `--days` qualify; video upload dates do not limit discovery. This is a small sample and can miss older comments on busy videos. No replies are fetched.

Optional `.env` controls:

```dotenv
METIS_YOUTUBE_COMMENTS_PER_VIDEO=25
# JSON list, first four queries are sampled:
METIS_YOUTUBE_QUERIES='["small business bookkeeping problems", "family budgeting problems"]'
# Alternatively, comma-separated real video IDs (up to eight) skip discovery:
# METIS_YOUTUBE_VIDEO_IDS=
```

## Manual research workflow

Read the original discussion or review and its replies, then write a short summary in your own words. Retain uncertainty and solutions already suggested. A researcher asking whether a problem exists is not a customer reporting it. One reviewer complaining does not establish repeated demand, and an incentive should remain visible.

```json
{
  "schema_version": 1,
  "notes": [
    {
      "source": "ukbusinessforums",
      "url": "https://www.ukbusinessforums.co.uk/threads/customer-remittances-covering-lots-of-invoices-how-do-you-handle-them.431200/",
      "locator": "opening post",
      "title": "Research question about allocating bulk payments",
      "author_label": "Damonj7",
      "published_on": "2026-09-25",
      "observed_on": "2026-10-23",
      "audience": "small_business",
      "observation": "research_question",
      "summary": "The poster asks bookkeepers how they allocate bulk payments and whether the work is troublesome.",
      "incentive": "not_applicable",
      "caveat": "This asks others about a possible need; it is not a firsthand report of unmet demand.",
      "follow_up": "Look for independent customer reports and check existing accounting features."
    }
  ]
}
```

Save the batch locally, then run:

```bash
metis research-import /path/to/research-notes.json
metis research
metis research --source moneysavingexpert --limit 10
```

Allowed sources are exactly `ukbusinessforums`, `moneysavingexpert`, and `capterra`; URLs must use their listed HTTPS domains and discussion/review paths. No URLs are fetched on import. `locator` identifies the specific post or review on that page. Reimporting the same URL and locator updates the note without multiplying evidence. All notes validate before the batch is written.

`published_on` is the original publication date, not the latest reply, edit, or discovery time. If the year or date cannot be established, use `null` with a `date_note` explaining the uncertainty. `observed_on` records when the page was read. Optional `excerpt` is limited to 25 words; keep quotes across notes from the same page short. `incentive` accepts `incentivized`, `non_incentivized`, `unknown`, or `not_applicable`. `observation` accepts `problem_report`, `research_question`, `existing_solution`, or `positive_experience`.

Notes live in a separate SQLite table. Their summaries, labels, and excerpts never enter automated lead scoring, clustering, or repeat counts. `metis research` explicitly labels them as analyst notes and preserves unknown publication dates. A next step is to independently verify the problem, its persistence, available solutions, and payment interest before promoting it into an opportunity assessment.

## Initial findings

Six hand-selected notes were recorded locally: two per site, comprising four problem reports, one research question, and one positive experience. This is a source-quality probe, not a representative sample or precision measurement. Three publication dates were exact; three remained unknown because the displayed dates were relative or omitted a year.

| Evidence | Observation | What still needs checking |
| --- | --- | --- |
| [UKBF: manual-entry accounting workflow](https://www.ukbusinessforums.co.uk/threads/software-for-manual-entry-mtd.431312/) | An accountant describes recurring manual adjustments and asks for a usable submission workflow. | Replies already suggest spreadsheet bridging tools; assess whether a gap remains. |
| [UKBF: bulk invoice payment allocation](https://www.ukbusinessforums.co.uk/threads/customer-remittances-covering-lots-of-invoices-how-do-you-handle-them.431200/) | A research question rather than a customer's own pain report. | Exclude from customer-demand counts; existing matching features appear in replies. |
| [MSE: household transaction exports](https://forums.moneysavingexpert.com/discussion/6666813/downloading-transactions-from-barclays) | A household budgeter struggles to export card transactions; replies discuss conversion and account-specific access. | Determine whether current export options solve the problem for that account type. |
| [MSE: banking without a mobile](https://forums.moneysavingexpert.com/discussion/6687613/banking-without-a-mobile-possible) | A person seeks banking access without a mobile phone. | Replies name existing alternatives; useful access/discovery problem, not proof a new banking product is needed. |
| [Capterra: QuickBooks reviews](https://www.capterra.com/p/190778/QuickBooks-Online/reviews/) | One incentivized June 2 review reports recurring connection/reliability work; another incentivized review on that date is positive and reports resolving concerns. | Mixed experiences and incentives remain visible. Check persistence and independent corroboration. |

No willingness to pay or repeated, unresolved need was verified by these notes. No live YouTube results are claimed without a configured key. The useful next comparison is independently corroborated problems per source, rather than the number of complaints collected.

## Test-run outcome

The free-source regression run collected 99 records: 28 from HN, 21 from Stack Exchange, and 50 GitHub issues. All three collections succeeded. The fresh sample produced one primary household-budgeting candidate and 22 supporting GitHub records. This does not demonstrate improved automated coverage from the manual sources.

After merging the run into the existing local evidence and reanalyzing with saved Shopify/Monzo posts included, the store contained five primary candidates: a news-subscription request, retail inventory counting, garden-layout planning, school-payment tracking, and household budgeting. Two were restored vendor-community candidates; the five are not five newly discovered problems. The six manual notes remain separate.

The YouTube attempt reported `unconfigured`, with zero requests and zero comments. The new collector's success, date filtering, duplicate handling, disabled-comments, and quota-error paths were exercised through mocked HTTP tests. A live YouTube test remains pending a key.
