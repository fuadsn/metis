import re
from datetime import datetime, timedelta, timezone
from math import ceil

from collectors.base import CollectionError, Collector, StopCollection


class RedditCollector(Collector):
    source = "reddit"

    def missing_configuration(self):
        return [
            name
            for name, value in (
                ("REDDIT_CLIENT_ID", self.settings.reddit_client_id),
                ("REDDIT_CLIENT_SECRET", self.settings.reddit_client_secret),
            )
            if not value or value.startswith("your_")
        ]

    def _collect(self, limit, days):
        communities = self.settings.subreddits
        if not communities:
            raise CollectionError("Set METIS_SUBREDDITS to at least one subreddit")
        if any(not re.fullmatch(r"[A-Za-z0-9_]+", name) for name in communities):
            raise CollectionError("METIS_SUBREDDITS must contain subreddit names only")
        headers = {"User-Agent": self.settings.reddit_user_agent}
        grant = {"grant_type": "client_credentials"}
        if self.settings.reddit_refresh_token:
            grant = {
                "grant_type": "refresh_token",
                "refresh_token": self.settings.reddit_refresh_token,
            }
        token = self.request(
            "POST",
            "https://www.reddit.com/api/v1/access_token",
            auth=(self.settings.reddit_client_id, self.settings.reddit_client_secret),
            headers=headers,
            data=grant,
        )
        if not token.get("access_token"):
            raise CollectionError(
                "Reddit did not grant an access token; check approved app access"
            )
        headers["Authorization"] = "Bearer " + token["access_token"]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        per_subreddit = min(100, ceil(limit / len(communities)))
        for community in communities:
            try:
                data = self.request(
                    "GET",
                    f"https://oauth.reddit.com/r/{community}/new",
                    headers=headers,
                    params={"limit": per_subreddit, "raw_json": 1},
                )
                for child in data["data"]["children"]:
                    post = child["data"]
                    if post.get("stickied") or post.get("created_utc", 0) < cutoff:
                        continue
                    if post.get("selftext") in {"[removed]", "[deleted]"}:
                        continue
                    self.add(post)
            except StopCollection:
                raise
            except CollectionError as exc:
                self.result.errors.append(f"r/{community}: {exc}")
