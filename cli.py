import argparse
import json
import logging
import sqlite3
import sys

from config import SOURCE_NAMES, Settings
from models import timestamp
from pipeline import collect_posts, run_analysis, run_pipeline, source_status
from storage import Store


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
        "--sources", help="Comma-separated sources: " + ",".join(SOURCE_NAMES)
    )
    if include_limit:
        parser.add_argument(
            "--limit",
            type=bounded_int(1, 500),
            default=50,
            help="Maximum collected posts per source (default: 50; X minimum: 10)",
        )
    parser.add_argument(
        "--days",
        type=bounded_int(1, 365),
        default=30,
        help="Lookback window (default: 30; X recent search capped at 7)",
    )


def settings_for(sources=None):
    if sources is None:
        return Settings()
    return Settings(
        sources=[source.strip() for source in sources.split(",") if source.strip()]
    )


def latest(kind, limit=20, source=None, store=None):
    if limit < 1:
        raise ValueError("limit must be positive")
    store = store or Store()
    data = store.load_result("latest_analysis.json")
    if not data:
        return {
            "status": "error",
            "message": "No analysis found. Run 'metis run' first.",
        }
    if kind == "leads" and data.get("schema_version") != 2:
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
    collection = store.load_result("latest_collection.json")
    return {
        "status": "success",
        "processed_at": data.get("processed_at"),
        "selected_sources": data.get("selected_sources"),
        "window_days": data.get("window_days"),
        "analysis_status": data.get("status", "unknown"),
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
        prog="metis", description="Startup and developer-tool opportunity research"
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
    for name in ("leads", "ideas", "clusters"):
        command = subparsers.add_parser(name)
        command.add_argument("--limit", type=bounded_int(1, 1000), default=20)
        command.add_argument("--source", choices=SOURCE_NAMES)
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    configure_logging()

    def execute():
        if args.command in {"leads", "ideas", "clusters"}:
            return latest(args.command, args.limit, args.source)
        settings = settings_for(args.sources)
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
