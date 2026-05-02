import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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


def collect_posts():
    collector = HNCollector()
    posts = collector.collect_all()

    existing_ids = get_all_post_ids()
    new_posts = [p for p in posts if p["id"] not in existing_ids]

    if new_posts:
        save_raw_posts(new_posts, "hackernews")

    return {
        "collected": len(posts),
        "new": len(new_posts),
        "total_stored": len(existing_ids) + len(new_posts),
    }


def run_analysis():
    all_posts = load_raw_posts(limit=10)

    cleaned = clean_posts(all_posts)
    pain_points = extract_pain_points(cleaned)
    clusters = cluster_pain_points(pain_points)
    ideas = generate_ideas(clusters)

    processed_data = {
        "posts_processed": len(all_posts),
        "pain_points_count": len(pain_points),
        "clusters": clusters,
        "ideas": ideas,
    }

    save_processed_data(processed_data, "latest_analysis.json")

    return processed_data


def get_ideas(limit=10):
    data = load_processed_data("latest_analysis.json")
    if not data:
        return {"error": "No analysis run yet. Run metis_analyze first."}

    ideas = data.get("ideas", [])[:limit]
    return {"ideas": ideas}


def get_clusters():
    data = load_processed_data("latest_analysis.json")
    if not data:
        return {"error": "No analysis run yet. Run metis_analyze first."}

    return {"clusters": data.get("clusters", [])}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["collect", "analyze", "ideas", "clusters"])
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    result = {}
    if args.command == "collect":
        result = collect_posts()
    elif args.command == "analyze":
        result = run_analysis()
    elif args.command == "ideas":
        result = get_ideas(args.limit)
    elif args.command == "clusters":
        result = get_clusters()

    print(json.dumps(result, indent=2))
