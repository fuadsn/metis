"""Read public merchant/household forum posts; search snippets are never scored."""

import time
from datetime import datetime, timezone
from math import ceil
from urllib.robotparser import RobotFileParser

from collectors.base import CollectionError, Collector, StopCollection
from collectors.search import age_windows
from models import timestamp

# One focused query per forum, sampled in both age bands. No paid/authenticated APIs.
SITES = {
    "small_business": ("community.shopify.com", "manually"),
    "everyday_life": ("community.monzo.com", '"every week"'),
}
USER_AGENT = "Metis/0.6 (+https://github.com/fuadsn/metis)"


class DiscourseCollector(Collector):
    source = "discourse"
    search_request_limit = 30

    def _collect(self, limit, days):
        sites = [SITES[a] for a in self.settings.audiences if a in SITES]
        windows = age_windows(days)
        per_search = min(5, ceil(limit / max(1, len(sites) * len(windows))))
        self.seen = set()
        self.last_search = {}
        for host, query in sites:
            if len(self.result.posts) >= limit:
                break
            try:
                self._forum(host, query, windows, per_search, limit)
            except StopCollection as exc:
                if (
                    self.result.requests >= self.request_limit
                    or time.monotonic() >= self.deadline
                ):
                    raise
                # Stop requests to this host after access/rate/network failures.
                # Another public forum has its own limits and can still succeed.
                self.result.errors.append(f"{host}: {exc}")

    def _forum(self, host, query, windows, per_search, limit):
        robots = RobotFileParser()
        headers = {"User-Agent": USER_AGENT}
        policy = self.request(
            "GET", f"https://{host}/robots.txt", as_text=True, headers=headers
        )
        if "user-agent:" not in policy.lower():
            raise StopCollection("Public search policy unavailable; forum skipped")
        robots.parse(policy.splitlines())
        if not robots.can_fetch(USER_AGENT, f"https://{host}/search.json"):
            raise StopCollection("robots.txt disallows public search; forum skipped")
        for band, start, end in windows:
            if len(self.result.posts) >= limit:
                return
            after = (
                datetime.fromtimestamp(start - 86400, timezone.utc).date().isoformat()
            )
            before = (
                datetime.fromtimestamp(end + 86400, timezone.utc).date().isoformat()
            )
            pause = 1 - (time.monotonic() - self.last_search.get(host, 0))
            if pause > 0:
                time.sleep(pause)
            self.last_search[host] = time.monotonic()
            try:
                data = self.request(
                    "GET",
                    f"https://{host}/search.json",
                    headers=headers,
                    params={
                        "q": f"{query} in:first after:{after} before:{before} order:relevance",
                    },
                )
            except StopCollection:
                raise
            except CollectionError as exc:
                self.result.errors.append(f"{host}: {exc}")
                continue
            if data.get("errors") or (data.get("grouped_search_result") or {}).get(
                "error"
            ):
                raise StopCollection("search was rejected")
            topics = {item["id"]: item for item in data.get("topics", [])}
            hits = [
                h
                for h in data.get("posts", [])
                if h.get("post_number") == 1
                and h.get("topic_id") in topics
                and start <= (timestamp(h.get("created_at")) or 0) <= end
            ]
            # Fetch before the next search so a later rate limit cannot discard
            # already retrieved full evidence.
            for hit in hits[:per_search]:
                identity = (host, hit["id"])
                if identity in self.seen:
                    continue
                if len(self.result.posts) >= limit:
                    return
                self.seen.add(identity)
                topic = topics[hit["topic_id"]]
                try:
                    if not robots.can_fetch(
                        USER_AGENT, f"https://{host}/posts/{int(hit['id'])}.json"
                    ):
                        raise StopCollection(
                            "robots.txt disallows full-post reads; forum skipped"
                        )
                    post = self.request(
                        "GET",
                        f"https://{host}/posts/{int(hit['id'])}.json",
                        headers=headers,
                    )
                    if (
                        post.get("id") != int(hit["id"])
                        or post.get("deleted_at")
                        or post.get("hidden")
                        or post.get("post_number") != 1
                        or post.get("topic_id") != hit["topic_id"]
                        or not start <= (timestamp(post.get("created_at")) or 0) <= end
                    ):
                        continue
                    if not isinstance(post.get("raw"), str) or not post["raw"].strip():
                        self.result.errors.append(
                            f"{host}: full post text unavailable; snippet skipped"
                        )
                        continue
                    self.add(
                        {
                            "id": f"{host}:topic:{topic['id']}",
                            "community": host,
                            "title": topic["title"],
                            "body": post["raw"],
                            "author": post.get("username", ""),
                            "url": f"https://{host}/t/{topic['id']}/1",
                            "created_utc": post["created_at"],
                            "updated_utc": post.get("updated_at"),
                            "num_comments": max(0, (topic.get("posts_count") or 1) - 1),
                            "matched_queries": [query],
                            "metadata": {
                                "discovery": "full_post_search",
                                "age_band": band,
                                "forum_post_id": post["id"],
                                "tags": topic.get("tags", []),
                            },
                        }
                    )
                except StopCollection:
                    raise
                except CollectionError as exc:
                    self.result.errors.append(f"{host}: {exc}")
