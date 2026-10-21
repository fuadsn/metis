from datetime import datetime, timedelta, timezone
from math import ceil

from collectors.base import CollectionError, Collector, StopCollection


class XCollector(Collector):
    source = "x"

    def missing_configuration(self):
        token = self.settings.x_bearer_token
        return [] if token and not token.startswith("your_") else ["X_BEARER_TOKEN"]

    def _collect(self, limit, days):
        # Limit caps retrieved (billable) posts, including overlapping queries.
        start = (
            datetime.now(timezone.utc)
            - timedelta(days=min(days, 7))
            + timedelta(minutes=1)
        )
        remaining = limit
        for query in self.settings.x_queries:
            if remaining < 10:
                if not self.result.posts:
                    raise CollectionError("X requires --limit of at least 10")
                break
            page_size = min(
                100, remaining, max(10, ceil(limit / len(self.settings.x_queries)))
            )
            try:
                data = self.request(
                    "GET",
                    "https://api.x.com/2/tweets/search/recent",
                    headers={"Authorization": "Bearer " + self.settings.x_bearer_token},
                    params={
                        "query": query,
                        "max_results": page_size,
                        "start_time": start.isoformat().replace("+00:00", "Z"),
                        "tweet.fields": "created_at,author_id,public_metrics,lang",
                    },
                )
                if data.get("errors"):
                    self.result.errors.append(
                        "X returned partial results; check query and access"
                    )
                if (
                    "data" not in data
                    and not data.get("errors")
                    and data.get("meta", {}).get("result_count") != 0
                ):
                    raise CollectionError("X returned an unexpected search response")
                items = data.get("data", [])
                remaining -= len(items)
                for item in items:
                    metrics = item.get("public_metrics") or {}
                    self.add(
                        {
                            "id": item["id"],
                            "body": item["text"],
                            "url": f"https://x.com/i/web/status/{item['id']}",
                            "author": item.get("author_id", ""),
                            "created_utc": item.get("created_at"),
                            "score": metrics.get("like_count", 0),
                            "num_comments": metrics.get("reply_count", 0),
                            "matched_queries": [query],
                            "metadata": {"public_metrics": metrics},
                        }
                    )
            except StopCollection:
                raise
            except CollectionError as exc:
                self.result.errors.append(str(exc))
