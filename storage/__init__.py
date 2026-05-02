import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from config import RAW_DIR, PROCESSED_DIR


def ensure_dirs():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def save_raw_posts(posts: List[Dict], source: str) -> int:
    ensure_dirs()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = RAW_DIR / f"{source}_{timestamp}.json"

    data = {
        "collection_time": datetime.now().isoformat(),
        "source": source,
        "post_count": len(posts),
        "posts": posts,
    }

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return len(posts)


def load_raw_posts(source: Optional[str] = None, limit: int = 10) -> List[Dict]:
    ensure_dirs()

    files = sorted(RAW_DIR.glob(f"{source or '*'}_*.json"), reverse=True)[:limit]
    all_posts = []

    for file in files:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            all_posts.extend(data.get("posts", []))

    return all_posts


def get_all_post_ids() -> set:
    ensure_dirs()
    ids = set()

    for file in RAW_DIR.glob("*.json"):
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            for post in data.get("posts", []):
                ids.add(post.get("id"))

    return ids


def save_processed_data(data: Dict, filename: str):
    ensure_dirs()
    filepath = PROCESSED_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_processed_data(filename: str) -> Optional[Dict]:
    filepath = PROCESSED_DIR / filename
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None
