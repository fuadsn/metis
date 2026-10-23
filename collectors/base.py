"""Bounded read-only collection with explicit partial/failure reporting."""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import httpx

from config import DEFAULT_WINDOW_DAYS, Settings
from models import normalize_post, unique_posts
from processors.cleaner import clean_posts, rank_candidates
from processors.signals import promising_discussion


class CollectionError(Exception):
    pass


class StopCollection(CollectionError):
    """Access, network, or budget failure that must stop all queries."""

    pass


class RateLimited(StopCollection):
    pass


@dataclass
class CollectionResult:
    source: str
    status: str = "success"
    posts: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    requests: int = 0
    comments: List[Dict] = field(default_factory=list)
    comment_threads: int = 0
    comment_requests: int = 0

    def summary(self):
        return {
            "source": self.source,
            "status": self.status,
            "collected": len(self.posts),
            "requests": self.requests,
            "comments_collected": len(self.comments),
            "comment_threads": self.comment_threads,
            "comment_requests": self.comment_requests,
            "errors": self.errors,
        }


class Collector:
    source = ""
    supports_comments = False
    search_request_limit = 10

    def __init__(self, settings: Optional[Settings] = None, client=None):
        self.settings = settings or Settings()
        self.client = client
        self.result = CollectionResult(self.source)
        self.request_limit = 0

    def missing_configuration(self) -> List[str]:
        return []

    def collect(self, limit=50, days=DEFAULT_WINDOW_DAYS) -> CollectionResult:
        if not 1 <= limit <= 500 or not 1 <= days <= 365:
            raise ValueError("limit must be 1–500 and days must be 1–365")
        self.result = CollectionResult(self.source)
        missing = self.missing_configuration()
        if missing:
            self.result.status = "unconfigured"
            self.result.errors = ["Set " + ", ".join(missing)]
            return self.result
        self.request_limit = self.search_request_limit
        owned = self.client is None
        if owned:
            self.client = httpx.Client(timeout=10, follow_redirects=False)
        self.deadline = time.monotonic() + 60
        try:
            self._collect(limit, days)
            self.result.posts = unique_posts(self.result.posts)[:limit]
            self._enrich_comments()
        except (
            CollectionError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
        ) as exc:
            self.result.errors.append(
                str(exc)
                if isinstance(exc, CollectionError)
                else "Unexpected response format from source"
            )
        finally:
            if owned:
                self.client.close()
                self.client = None
        self.result.posts = unique_posts(self.result.posts)[:limit]
        self.result.comments = unique_posts(self.result.comments)
        if self.result.errors:
            self.result.status = (
                "partial" if self.result.posts or self.result.comments else "error"
            )
        return self.result

    def collect_all(self):
        result = self.collect()
        if result.status in {"error", "unconfigured"}:
            raise CollectionError("; ".join(result.errors))
        return result.posts

    def add(self, raw):
        self.result.posts.append(normalize_post(raw, self.source))

    def comment_budget(self):
        return self.settings.comment_threads

    def _enrich_comments(self):
        if not self.supports_comments or not self.settings.comment_threads:
            return
        candidates = [
            p
            for p in rank_candidates(clean_posts(self.result.posts))
            if (p["lead_quality"] == "opportunity" or promising_discussion(p))
            and (
                p["num_comments"] > 0
                or p["metadata"].get("comment_ids")
                or p["metadata"].get("comment_count_unknown")
            )
        ]
        candidates.sort(
            key=lambda p: (
                p["lead_quality"] != "opportunity",
                -p["priority_score"],
                -p["num_comments"],
                p["post_id"],
            )
        )
        before = self.result.requests
        budget = self.comment_budget()
        self.request_limit = before + budget
        try:
            for point in candidates[: self.settings.comment_threads]:
                parent = {**point, "id": point["post_id"]}
                self.result.comment_threads += 1
                try:
                    for raw in self._fetch_comments(
                        parent, self.settings.comments_per_thread
                    ):
                        self.result.comments.append(
                            normalize_post(
                                {
                                    **raw,
                                    "kind": "comment",
                                    "title": "",
                                    "parent_id": parent["id"],
                                    "parent_url": parent["url"],
                                    "community": parent["community"],
                                    "matched_queries": parent["matched_queries"],
                                    "metadata": {
                                        **raw.get("metadata", {}),
                                        "parent_title": parent["title"],
                                    },
                                },
                                self.source,
                            )
                        )
                except StopCollection:
                    raise
                except CollectionError as exc:
                    self.result.errors.append(f"Comments: {exc}")
        finally:
            self.result.comment_requests = self.result.requests - before

    def request(self, method, url, *, as_text=False, **kwargs):
        for attempt in range(3):
            if self.result.requests >= self.request_limit:
                raise StopCollection(
                    "Per-run request cap reached; narrow the configured searches"
                )
            if time.monotonic() >= self.deadline:
                raise StopCollection("Source exceeded its 60-second collection budget")
            self.result.requests += 1
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.RequestError:
                if attempt < 2:
                    time.sleep(0.25 * 2**attempt)
                    continue
                raise StopCollection("Network request failed after 3 attempts")
            if response.status_code == 429 or (
                response.status_code == 403
                and (
                    response.headers.get("x-ratelimit-remaining") == "0"
                    or response.headers.get("retry-after")
                )
            ):
                raise RateLimited(
                    "Source rate limit reached; collection stopped for this run"
                )
            if response.status_code >= 500 and attempt < 2:
                time.sleep(0.25 * 2**attempt)
                continue
            if 300 <= response.status_code < 400:
                raise StopCollection(
                    "Source redirected the request; collection stopped"
                )
            if response.status_code >= 400:
                hints = {
                    401: "check credentials",
                    402: "API credits or billing access required",
                    403: "API access denied; check app permissions",
                }
                error = (
                    StopCollection
                    if response.status_code in {401, 402, 403}
                    else CollectionError
                )
                raise error(
                    f"HTTP {response.status_code}: {hints.get(response.status_code, 'source request failed')}"
                )
            if as_text:
                return response.text
            try:
                return response.json()
            except ValueError:
                raise CollectionError("Source returned invalid JSON")
