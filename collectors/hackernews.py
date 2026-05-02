import httpx
import asyncio
from typing import List, Dict, Optional
from config import HN_API_BASE, HN_SOURCES, HN_POSTS_PER_SOURCE


class HNCollector:
    def __init__(self):
        self.base_url = HN_API_BASE

    def collect_all(self) -> List[Dict]:
        return asyncio.run(self._collect_all_async())

    async def _collect_all_async(self) -> List[Dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            all_items = []

            for source in HN_SOURCES:
                print(f"Collecting from {source}...")
                items = await self._collect_source(client, source)
                all_items.extend(items)
                print(f"  Collected {len(items)} items")

            return all_items

    async def _collect_source(
        self, client: httpx.AsyncClient, source: str
    ) -> List[Dict]:
        endpoint_map = {
            "top": "topstories",
            "new": "newstories",
            "best": "beststories",
            "ask": "askstories",
            "show": "showstories",
        }

        endpoint = endpoint_map.get(source, "topstories")

        try:
            response = await client.get(f"{self.base_url}/{endpoint}.json")
            response.raise_for_status()
            story_ids = response.json()

            story_ids = story_ids[:HN_POSTS_PER_SOURCE]

            tasks = [self._fetch_story(client, story_id) for story_id in story_ids]
            stories = await asyncio.gather(*tasks)

            return [s for s in stories if s is not None]

        except Exception as e:
            print(f"Error collecting {source}: {e}")
            return []

    async def _fetch_story(
        self, client: httpx.AsyncClient, story_id: int
    ) -> Optional[Dict]:
        try:
            response = await client.get(f"{self.base_url}/item/{story_id}.json")
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
