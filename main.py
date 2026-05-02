import sys
import schedule
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from collectors import HNCollector
from storage import (
    save_raw_posts,
    load_raw_posts,
    get_all_post_ids,
    save_processed_data,
)
from processors import clean_posts, extract_pain_points, cluster_pain_points
from generators import generate_ideas, format_ideas_for_agent


def run_collection():
    print(f"\n{'=' * 50}")
    print(f"Collection run started at {datetime.now().isoformat()}")
    print(f"{'=' * 50}\n")

    collector = HNCollector()
    posts = collector.collect_all()

    existing_ids = get_all_post_ids()
    new_posts = [p for p in posts if p["id"] not in existing_ids]

    print(f"\nNew posts collected: {len(new_posts)}")

    if new_posts:
        save_raw_posts(new_posts, "hackernews")

    return len(new_posts)


def run_processing():
    print(f"\nProcessing run started at {datetime.now().isoformat()}")

    all_posts = load_raw_posts(limit=5)
    print(f"Loaded {len(all_posts)} posts for processing")

    cleaned = clean_posts(all_posts)
    print(f"Cleaned: {len(cleaned)} posts")

    pain_points = extract_pain_points(cleaned)
    print(f"Pain points extracted: {len(pain_points)}")

    clusters = cluster_pain_points(pain_points)
    print(f"Clusters formed: {len(clusters)}")

    ideas = generate_ideas(clusters)
    print(f"Ideas generated: {len(ideas)}")

    processed_data = {
        "processed_at": datetime.now().isoformat(),
        "posts_processed": len(all_posts),
        "pain_points": pain_points,
        "clusters": clusters,
        "ideas": ideas,
    }

    save_processed_data(processed_data, "latest_analysis.json")

    print("\n" + "=" * 50)
    print("IDEAS OUTPUT FOR AGENTS")
    print("=" * 50)
    print(format_ideas_for_agent(ideas))

    return processed_data


def run():
    new_posts = run_collection()

    if new_posts > 0:
        run_processing()
    else:
        print("No new posts, skipping processing")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--watch", action="store_true", help="Run continuously with scheduler"
    )
    args = parser.parse_args()

    print("Metis - Market Intelligence System")
    print("Running collection and processing...\n")

    run()

    if args.watch:
        print("\nSetting up scheduled runs...")
        schedule.every(6).hours.do(run)

        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        print("\nDone. Run with --watch for continuous operation.")
