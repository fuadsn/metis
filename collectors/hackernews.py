import httpx
import time
from typing import List, Dict, Optional
from config import HN_API_BASE, HN_SOURCES


class HNCollector:
    def __init__(self):
        self.base_url = HN_API_BASE

    def collect_all(self) -> List[Dict]:
        all_items = []

        for source in HN_SOURCES:
            print(f"Collecting from {source}...")
            items = self._collect_source(source)
            all_items.extend(items)
            print(f"  Collected {len(items)} items")

        return all_items

    def _collect_source(self, source: str) -> List[Dict]:
        endpoint_map = {
            "top": "topstories",
            "new": "newstories",
            "best": "beststories",
            "ask": "askstories",
            "show": "showstories",
        }

        endpoint = endpoint_map.get(source, "topstories")

        try:
            response = httpx.get(f"{self.base_url}/{endpoint}.json", timeout=30)
            response.raise_for_status()
            story_ids = response.json()

            story_ids = story_ids[:20]

            stories = []
            for story_id in story_ids:
                story = self._fetch_story(story_id)
                if story:
                    stories.append(story)
                time.sleep(0.1)

            return stories

        except Exception as e:
            print(f"Error collecting {source}: {e}")
            return []

    def _fetch_story(self, story_id: int) -> Optional[Dict]:
        try:
            response = httpx.get(f"{self.base_url}/item/{story_id}.json", timeout=10)
            response.raise_for_status()
            story = response.json()

            if not story:
                return None

            return {
                "id": str(story.get("id")),
                "title": story.get("title", ""),
                "text": story.get("text", ""),
                "url": story.get("url", ""),
                "score": story.get("score", 0),
                "descendants": story.get("descendants", 0),
                "by": story.get("by", ""),
                "time": story.get("time"),
                "type": story.get("type", "story"),
                "source": "hackernews",
            }
        except Exception:
            return None
