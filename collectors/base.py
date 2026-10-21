"""Bounded read-only collection with explicit partial/failure reporting."""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import httpx
from config import Settings
from models import normalize_post, unique_posts


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

    def summary(self):
        return {
            "source": self.source,
            "status": self.status,
            "collected": len(self.posts),
            "requests": self.requests,
            "errors": self.errors,
        }


class Collector:
    source = ""

    def __init__(self, settings: Optional[Settings] = None, client=None):
        self.settings = settings or Settings()
        self.client = client
        self.result = CollectionResult(self.source)
        self.request_limit = 0

    def missing_configuration(self) -> List[str]:
        return []

    def collect(self, limit=50, days=30) -> CollectionResult:
        if not 1 <= limit <= 500 or not 1 <= days <= 365:
            raise ValueError("limit must be 1–500 and days must be 1–365")
        self.result = CollectionResult(self.source)
        missing = self.missing_configuration()
        if missing:
            self.result.status = "unconfigured"
            self.result.errors = ["Set " + ", ".join(missing)]
            return self.result
        self.request_limit = 10 if self.source != "hackernews" else limit + 5
        owned = self.client is None
        if owned:
            self.client = httpx.Client(timeout=10, follow_redirects=False)
        self.deadline = time.monotonic() + 60
        try:
            self._collect(limit, days)
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
        if self.result.errors:
            self.result.status = "partial" if self.result.posts else "error"
        return self.result

    def collect_all(self):
        result = self.collect()
        if result.status in {"error", "unconfigured"}:
            raise CollectionError("; ".join(result.errors))
        return result.posts

    def add(self, raw):
        self.result.posts.append(normalize_post(raw, self.source))

    def request(self, method, url, **kwargs):
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
            try:
                return response.json()
            except ValueError:
                raise CollectionError("Source returned invalid JSON")
