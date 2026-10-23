"""The single collection/analysis workflow used by every entry point."""

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from collectors import COLLECTORS
from config import ANALYSIS_VERSION, DEFAULT_WINDOW_DAYS, SOURCE_NAMES, Settings
from generators import generate_ideas
from processors import clean_posts, cluster_pain_points
from processors.cleaner import rank_candidates
from processors.source_context import community_coverage, source_context
from storage import Store

logger = logging.getLogger(__name__)


def source_status(settings=None):
    settings = settings or Settings()
    result = []
    for name in SOURCE_NAMES:
        missing = COLLECTORS[name](settings).missing_configuration()
        result.append(
            {
                "source": name,
                "enabled": name in settings.sources,
                "status": "disabled"
                if name not in settings.sources
                else "unconfigured"
                if missing
                else "ready",
                "missing": missing,
                "access_verified": False,
                **source_context(name),
            }
        )
    return {
        "status": "success",
        "selected_audiences": settings.audiences,
        "sources": result,
        "stackexchange_searches": settings.stackexchange_searches(),
    }


def collect_posts(settings=None, store=None, limit=50, days=DEFAULT_WINDOW_DAYS):
    settings, store = settings or Settings(), store or Store()
    summaries = []
    for source in settings.sources:
        logger.info("Collecting %s", source)
        result = COLLECTORS[source](settings).collect(limit=limit, days=days)
        counts = store.upsert(result.posts + result.comments)
        summaries.append({**result.summary(), **counts})
    succeeded = any(row["status"] in {"success", "partial"} for row in summaries)
    status = (
        "success"
        if all(row["status"] == "success" for row in summaries)
        else "partial"
        if succeeded
        else "error"
    )
    result = {
        "schema_version": 2,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "selected_sources": list(settings.sources),
        "selected_audiences": list(settings.audiences),
        "window_days": days,
        "collected": sum(row["collected"] for row in summaries),
        "comments_collected": sum(row["comments_collected"] for row in summaries),
        "new": sum(row["new"] for row in summaries),
        "updated": sum(row["updated"] for row in summaries),
        "total_stored": sum(store.counts().values()),
        "sources": summaries,
    }
    store.record_run(result)
    return result


def run_analysis(settings=None, store=None, days=DEFAULT_WINDOW_DAYS):
    settings, store = settings or Settings(), store or Store()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    posts = store.load_posts(sources=settings.sources, since=since, limit=None)
    cleaned = clean_posts(posts)
    candidates = rank_candidates(cleaned)
    points = [p for p in candidates if p["lead_quality"] != "noise"]
    leads = [
        p
        for p in points
        if p["lead_quality"] == "opportunity"
        and p["evidence_role"] == "primary"
        and p["primary_audience"] in settings.audiences
    ]
    supporting = [p for p in points if p["evidence_role"] == "supporting"]
    clusters = cluster_pain_points(leads, supporting)
    ideas = generate_ideas(clusters)
    result = {
        "schema_version": 2,
        "analysis_version": ANALYSIS_VERSION,
        "status": "success",
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "selected_sources": list(settings.sources),
        "selected_audiences": list(settings.audiences),
        "window_days": days,
        "posts_processed": len(posts),
        "comments_processed": sum(post.get("kind") == "comment" for post in posts),
        "quality_counts": dict(Counter(p["lead_quality"] for p in candidates)),
        "leads_count": len(leads),
        "lead_source_counts": dict(Counter(p["source"] for p in leads)),
        "lead_age_counts": dict(Counter(p["freshness"] for p in leads)),
        "lead_audience_counts": dict(Counter(p["primary_audience"] for p in leads)),
        "supporting_evidence_count": len(supporting),
        "source_counts": dict(Counter(p["source"] for p in posts)),
        "community_coverage": community_coverage(candidates, leads, settings),
        "pain_points_count": len(points),
        "clusters_count": len(clusters),
        "ideas_count": len(ideas),
        "pain_points": points,
        "leads": leads,
        "supporting_evidence": supporting,
        "candidates": candidates,
        "clusters": clusters,
        "ideas": ideas,
    }
    store.save_result(result, "latest_analysis.json")
    return result


def run_pipeline(settings=None, store=None, limit=50, days=DEFAULT_WINDOW_DAYS):
    settings, store = settings or Settings(), store or Store()
    collection = collect_posts(settings, store, limit, days)
    if collection["status"] == "error":
        previous = store.load_result("latest_analysis.json") or {}
        compatible = (
            previous.get("schema_version") == 2
            and previous.get("analysis_version") == ANALYSIS_VERSION
            and set(previous.get("selected_sources", [])) == set(settings.sources)
            and set(previous.get("selected_audiences", [])) == set(settings.audiences)
            and previous.get("window_days") == days
        )
        return {
            **(previous if compatible else {}),
            "status": "error",
            "collection": collection,
            "selected_sources": list(settings.sources),
            "selected_audiences": list(settings.audiences),
            "window_days": days,
            "analysis_reused": compatible,
            "message": "Collection failed; no new analysis was produced. Any saved analysis is unchanged.",
        }
    analysis = run_analysis(settings, store, days)
    result = {**analysis, "status": collection["status"], "collection": collection}
    store.save_result(result, "latest_analysis.json")
    return result
