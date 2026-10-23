import argparse
import json
import logging
import sqlite3
import sys

from config import (
    ANALYSIS_VERSION,
    AUDIENCE_NAMES,
    DEFAULT_WINDOW_DAYS,
    SOURCE_NAMES,
    Settings,
)
from models import REVIEW_LABELS, timestamp
from pipeline import collect_posts, run_analysis, run_pipeline, source_status
from processors.evaluation import evaluate_reviews
from storage import Store
from storage.research import RESEARCH_SOURCES, import_research, list_research


def configure_logging():
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    # HTTPX logs complete request URLs at INFO, including query-string API keys.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def bounded_int(minimum, maximum):
    def parse(value):
        result = int(value)
        if not minimum <= result <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return result

    return parse


def add_collection_arguments(parser, include_limit=True):
    parser.add_argument(
        "--audiences", help="Comma-separated audiences: " + ",".join(AUDIENCE_NAMES)
    )
    parser.add_argument(
        "--sources", help="Comma-separated sources: " + ",".join(SOURCE_NAMES)
    )
    if include_limit:
        parser.add_argument(
            "--comment-threads",
            type=bounded_int(0, 5),
            help="Top qualifying threads per source to sample (default: 3; 0 disables)",
        )
        parser.add_argument(
            "--comments-per-thread",
            type=bounded_int(1, 10),
            help="Comment sample per selected thread (default: 3)",
        )
        parser.add_argument(
            "--limit",
            type=bounded_int(1, 500),
            default=50,
            help="Maximum search matches per source, before comment enrichment (default: 50; X minimum: 10)",
        )
    parser.add_argument(
        "--days",
        type=bounded_int(1, 365),
        default=DEFAULT_WINDOW_DAYS,
        help="Lookback window (default: 180; X recent search capped at 7)",
    )


def settings_for(
    sources=None, comment_threads=None, comments_per_thread=None, audiences=None
):
    overrides = {}
    if sources is not None:
        overrides["sources"] = [
            source.strip() for source in sources.split(",") if source.strip()
        ]
    if audiences is not None:
        overrides["audiences"] = [
            part.strip() for part in audiences.split(",") if part.strip()
        ]
    for key, value in (
        ("comment_threads", comment_threads),
        ("comments_per_thread", comments_per_thread),
    ):
        if value is not None:
            overrides[key] = value
    return Settings(**overrides)


def latest(kind, limit=20, source=None, store=None, quality=None, audience=None):
    if limit < 1:
        raise ValueError("limit must be positive")
    store = store or Store()
    data = store.load_result("latest_analysis.json")
    if not data:
        return {
            "status": "error",
            "message": "No analysis found. Run 'metis run' first.",
        }
    if (
        data.get("schema_version") != 2
        or data.get("analysis_version") != ANALYSIS_VERSION
    ):
        return {
            "status": "error",
            "message": "Run 'metis analyze' to upgrade the saved analysis.",
        }
    items = data.get(kind, [])
    if source:
        items = [
            item
            for item in items
            if item.get("source") == source or source in item.get("sources", [])
        ]
    if quality:
        items = [item for item in items if item.get("lead_quality") == quality]
    if audience:
        items = [item for item in items if audience in item.get("audiences", [])]
    collection = store.load_result("latest_collection.json")
    return {
        "status": "success",
        "processed_at": data.get("processed_at"),
        "selected_sources": data.get("selected_sources"),
        "selected_audiences": data.get("selected_audiences"),
        "lead_audience_counts": data.get("lead_audience_counts", {}),
        "window_days": data.get("window_days"),
        "analysis_status": data.get("status", "unknown"),
        "analysis_version": data.get("analysis_version"),
        "lead_source_counts": data.get("lead_source_counts", {}),
        "lead_age_counts": data.get("lead_age_counts", {}),
        "supporting_evidence_count": data.get("supporting_evidence_count", 0),
        "community_coverage": data.get("community_coverage", []),
        "latest_collection": collection,
        "collection_newer_than_analysis": bool(
            collection
            and (timestamp(collection.get("timestamp")) or 0)
            > (timestamp(data.get("processed_at")) or 0)
        ),
        kind: items[:limit],
    }


def run_safely(action):
    """Keep expected configuration/storage failures consistent across entry points."""
    try:
        return action()
    except (ValueError, OSError, sqlite3.Error) as exc:
        message = (
            str(exc)
            if isinstance(exc, ValueError)
            else "Unable to read or write the Metis data directory"
        )
        return {"status": "error", "message": message}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="metis", description="Find unmet needs across businesses and everyday life"
    )
    subparsers = parser.add_subparsers(dest="command")
    for name in ("collect", "analyze", "run"):
        add_collection_arguments(
            subparsers.add_parser(name), include_limit=name != "analyze"
        )
    status_parser = subparsers.add_parser(
        "sources", help="Show configuration readiness without network calls"
    )
    status_parser.add_argument("--sources")
    status_parser.add_argument("--audiences")
    for name in ("leads", "ideas", "clusters", "candidates", "supporting_evidence"):
        command = subparsers.add_parser(name)
        command.add_argument("--limit", type=bounded_int(1, 1000), default=20)
        command.add_argument("--source", choices=SOURCE_NAMES)
        command.add_argument("--audience", choices=AUDIENCE_NAMES)
        if name == "candidates":
            command.add_argument("--quality", choices=REVIEW_LABELS)
    review = subparsers.add_parser(
        "review", help="Label a stored post locally for ranking evaluation"
    )
    review.add_argument("post_id")
    review.add_argument("--label", required=True, choices=REVIEW_LABELS)
    review.add_argument("--note", default="")
    subparsers.add_parser(
        "evaluate", help="Compare ranking rules with your local review labels"
    )
    research_import = subparsers.add_parser(
        "research-import",
        help="Import linked analyst notes without scoring them as posts",
    )
    research_import.add_argument("path")
    research = subparsers.add_parser(
        "research", help="Read the manual source pilot notes"
    )
    research.add_argument("--source", choices=tuple(RESEARCH_SOURCES))
    research.add_argument("--limit", type=bounded_int(1, 1000), default=20)
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    configure_logging()

    def execute():
        if args.command == "research-import":
            return import_research(args.path, Store())
        if args.command == "research":
            return list_research(Store(), args.source, args.limit)
        if args.command in {
            "leads",
            "ideas",
            "clusters",
            "candidates",
            "supporting_evidence",
        }:
            return latest(
                args.command,
                args.limit,
                args.source,
                quality=getattr(args, "quality", None),
                audience=args.audience,
            )
        if args.command == "review":
            return Store().save_review(args.post_id, args.label, args.note)
        if args.command == "evaluate":
            return evaluate_reviews(Store())
        settings = settings_for(
            args.sources,
            getattr(args, "comment_threads", None),
            getattr(args, "comments_per_thread", None),
            args.audiences,
        )
        if args.command == "sources":
            return source_status(settings)
        if args.command == "collect":
            return collect_posts(settings, limit=args.limit, days=args.days)
        if args.command == "analyze":
            return run_analysis(settings, days=args.days)
        return run_pipeline(settings, limit=args.limit, days=args.days)

    result = run_safely(execute)
    print(json.dumps(result, indent=2))
    return {"success": 0, "partial": 2, "error": 1}.get(result["status"], 1)


if __name__ == "__main__":
    sys.exit(main())
