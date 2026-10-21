"""Canonical evidence format, including migration of original JSON data."""

from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "br", "div", "li", "pre"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value: str) -> str:
    parser = _TextParser()
    parser.feed(value or "")
    return unescape("".join(parser.parts)).strip()


def timestamp(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


class Post(BaseModel):
    id: str
    external_id: str
    source: str
    community: str = ""
    title: str = ""
    body: str = ""
    url: str = ""
    author: str = ""
    created_utc: Optional[float] = None
    updated_utc: Optional[float] = None
    score: int = 0
    num_comments: int = 0
    matched_queries: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


def normalize_post(raw: Dict, source: Optional[str] = None) -> Dict:
    source = (
        source
        or raw.get("source")
        or ("reddit" if raw.get("subreddit") else "hackernews")
    )
    external_id = str(raw.get("external_id") or raw.get("id") or "")
    if external_id.startswith(source + ":"):
        external_id = external_id[len(source) + 1 :]
    if not external_id:
        raise ValueError("Post is missing its source ID")
    url = raw.get("url") or ""
    if source == "hackernews":
        url = f"https://news.ycombinator.com/item?id={external_id}"
    elif source == "reddit" and raw.get("permalink"):
        url = "https://www.reddit.com" + raw["permalink"]
    body = raw.get("body", raw.get("selftext", raw.get("text", ""))) or ""
    if source == "hackernews" and "body" not in raw:
        body = plain_text(body)
    return Post(
        id=f"{source}:{external_id}",
        external_id=external_id,
        source=source,
        community=raw.get("community") or raw.get("subreddit") or source,
        title=raw.get("title") or "",
        body=body,
        url=url,
        author=raw.get("author") or raw.get("by") or "",
        created_utc=timestamp(raw.get("created_utc", raw.get("time"))),
        updated_utc=timestamp(raw.get("updated_utc")),
        score=raw.get("score") or 0,
        num_comments=raw.get("num_comments", raw.get("descendants", 0)) or 0,
        matched_queries=raw.get("matched_queries") or [],
        metadata=raw.get("metadata") or {},
    ).model_dump()


def unique_posts(posts: List[Dict]) -> List[Dict]:
    result = {}
    for raw in posts:
        post = normalize_post(raw)
        previous = result.get(post["id"])
        if previous:
            post["matched_queries"] = sorted(
                set(previous["matched_queries"] + post["matched_queries"])
            )
        result[post["id"]] = post
    return list(result.values())
