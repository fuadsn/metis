import argparse
import json
import sys
from datetime import datetime

from collectors import HNCollector
from storage import (
    save_raw_posts,
    load_raw_posts,
    get_all_post_ids,
    save_processed_data,
    load_processed_data,
)
from processors import clean_posts, extract_pain_points, cluster_pain_points
from generators import generate_ideas


def cmd_collect():
    collector = HNCollector()
    posts = collector.collect_all()

    existing_ids = get_all_post_ids()
    new_posts = [p for p in posts if p["id"] not in existing_ids]

    if new_posts:
        save_raw_posts(new_posts, "hackernews")

    print(
        json.dumps(
            {
                "status": "success",
                "collected": len(posts),
                "new": len(new_posts),
                "timestamp": datetime.now().isoformat(),
            }
        )
    )

    return 0


def cmd_analyze():
    all_posts = load_raw_posts(limit=10)

    cleaned = clean_posts(all_posts)
    pain_points = extract_pain_points(cleaned)
    clusters = cluster_pain_points(pain_points)
    ideas = generate_ideas(clusters)

    result = {
        "status": "success",
        "processed_at": datetime.now().isoformat(),
        "posts_processed": len(all_posts),
        "pain_points_count": len(pain_points),
        "clusters_count": len(clusters),
        "ideas_count": len(ideas),
        "clusters": clusters,
        "ideas": ideas,
    }

    save_processed_data(result, "latest_analysis.json")

    print(json.dumps(result, indent=2))

    return 0


def cmd_ideas():
    data = load_processed_data("latest_analysis.json")

    if not data:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "No analysis found. Run 'metis run' first.",
                }
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": "success",
                "ideas": data.get("ideas", []),
                "clusters": data.get("clusters", []),
            },
            indent=2,
        )
    )

    return 0


def cmd_run():
    collector = HNCollector()
    posts = collector.collect_all()

    existing_ids = get_all_post_ids()
    new_posts = [p for p in posts if p["id"] not in existing_ids]

    if new_posts:
        save_raw_posts(new_posts, "hackernews")

    all_posts = load_raw_posts(limit=10)
    cleaned = clean_posts(all_posts)
    pain_points = extract_pain_points(cleaned)
    clusters = cluster_pain_points(pain_points)
    ideas = generate_ideas(clusters)

    result = {
        "status": "success",
        "collected": len(posts),
        "new_posts": len(new_posts),
        "posts_processed": len(all_posts),
        "pain_points": len(pain_points),
        "clusters": clusters,
        "ideas": ideas,
        "timestamp": datetime.now().isoformat(),
    }

    save_processed_data(result, "latest_analysis.json")

    print(json.dumps(result, indent=2))

    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="metis", description="Metis - Market Intelligence System"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("collect", help="Collect new posts from HN")
    subparsers.add_parser("analyze", help="Analyze stored posts")
    subparsers.add_parser("ideas", help="Output latest product ideas")
    subparsers.add_parser("run", help="Full pipeline: collect + analyze")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "collect": cmd_collect,
        "analyze": cmd_analyze,
        "ideas": cmd_ideas,
        "run": cmd_run,
    }

    return commands[args.command]()


if __name__ == "__main__":
    sys.exit(main())
