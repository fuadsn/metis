from datetime import datetime, timedelta, timezone

from collectors.base import CollectionError, Collector, StopCollection
from models import plain_text


class HNCollector(Collector):
    source = "hackernews"
    base_url = "https://hacker-news.firebaseio.com/v0"

    def _collect(self, limit, days):
        feeds = []
        for name in ("ask", "show", "new", "top", "best"):
            try:
                feeds.append(
                    self.request("GET", f"{self.base_url}/{name}stories.json")[:limit]
                )
            except StopCollection:
                raise
            except CollectionError as exc:
                self.result.errors.append(f"{name}: {exc}")
        ids = list(
            dict.fromkeys(
                feed[i] for i in range(limit) for feed in feeds if i < len(feed)
            )
        )[:limit]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        for story_id in ids:
            try:
                story = self.request("GET", f"{self.base_url}/item/{story_id}.json")
                if not story or story.get("deleted") or story.get("dead"):
                    continue
                if story.get("type") != "story" or story.get("time", 0) < cutoff:
                    continue
                self.add(
                    {
                        **story,
                        "title": plain_text(story.get("title", "")),
                        "body": plain_text(story.get("text", "")),
                        "metadata": {"external_url": story.get("url", "")},
                    }
                )
            except StopCollection:
                raise
            except CollectionError as exc:
                self.result.errors.append(f"Item {story_id}: {exc}")
