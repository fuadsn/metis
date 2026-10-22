"""Search needs in Ask HN and comment text, including historical discussions."""

from math import ceil

from collectors.base import CollectionError, Collector, StopCollection
from collectors.search import age_windows, interleave
from models import normalize_post, plain_text, unique_posts


class HNCollector(Collector):
    source = "hackernews"
    supports_comments = True
    search_request_limit = 20
    base_url = "https://hacker-news.firebaseio.com/v0"

    def _collect(self, limit, days):
        # Separate queries prevent stories from crowding comments out of relevance
        # results. Age bands prevent fresh discussions from crowding out history.
        kinds = ["ask_hn", "comment"] if self.settings.comment_threads else ["ask_hn"]
        searches = [
            (query, kind, band, start, end)
            for query in self.settings.hackernews_queries
            for kind in kinds
            for band, start, end in age_windows(days)
        ]
        per_search = min(100, max(1, ceil(limit / len(searches))))
        batches = []
        try:
            for query, kind, band, start, end in searches:
                try:
                    data = self.request(
                        "GET",
                        "https://hn.algolia.com/api/v1/search",
                        params={
                            "query": query,
                            "tags": kind,
                            "numericFilters": f"created_at_i>={start},created_at_i<={end}",
                            "hitsPerPage": per_search,
                            "page": 0,
                            "advancedSyntax": "true",
                            "restrictSearchableAttributes": "title,story_text,comment_text",
                        },
                    )
                    batch = []
                    for hit in data["hits"][:per_search]:
                        if hit.get("deleted") or hit.get("dead"):
                            continue
                        created = hit.get("created_at_i")
                        if (
                            not isinstance(created, (int, float))
                            or not start <= created <= end
                        ):
                            continue
                        item_id = str(hit["objectID"])
                        if not item_id.isdigit():
                            continue
                        is_comment = kind == "comment"
                        thread_id = hit.get("story_id") if is_comment else None
                        if is_comment and not str(thread_id or "").isdigit():
                            continue
                        body = plain_text(
                            hit.get("comment_text" if is_comment else "story_text", "")
                        )
                        if is_comment and not body:
                            continue
                        batch.append(
                            normalize_post(
                                {
                                    "id": f"comment:{item_id}"
                                    if is_comment
                                    else item_id,
                                    "kind": "comment" if is_comment else "post",
                                    "title": ""
                                    if is_comment
                                    else plain_text(hit.get("title", "")),
                                    "body": body,
                                    "author": hit.get("author", ""),
                                    "created_utc": created,
                                    "score": hit.get("points") or 0,
                                    "num_comments": hit.get("num_comments") or 0,
                                    # Root conversation ID prevents nested matches inflating repeats.
                                    "parent_id": f"hackernews:{thread_id}"
                                    if is_comment
                                    else None,
                                    "parent_url": f"https://news.ycombinator.com/item?id={thread_id}"
                                    if is_comment
                                    else "",
                                    "matched_queries": [query],
                                    "metadata": {
                                        "parent_title": hit.get("story_title") or "",
                                        "immediate_parent_id": hit.get("parent_id"),
                                        "discovery": "text_search",
                                        "age_band": band,
                                    },
                                },
                                self.source,
                            )
                        )
                    batches.append(batch)
                except StopCollection:
                    raise
                except CollectionError as exc:
                    self.result.errors.append(str(exc))
        finally:
            # Preserve completed searches when a later one is rate limited.
            for post in unique_posts(list(interleave(batches)))[:limit]:
                (
                    self.result.comments
                    if post["kind"] == "comment"
                    else self.result.posts
                ).append(post)

    def comment_budget(self):
        return self.settings.comment_threads * (1 + self.settings.comments_per_thread)

    def _fetch_comments(self, post, limit):
        story = self.request("GET", f"{self.base_url}/item/{post['external_id']}.json")
        if not story or story.get("deleted") or story.get("dead"):
            return
        for item_id in story.get("kids", [])[:limit]:
            if not isinstance(item_id, int) or item_id < 1:
                continue
            comment = self.request("GET", f"{self.base_url}/item/{item_id}.json")
            if (
                not comment
                or comment.get("deleted")
                or comment.get("dead")
                or comment.get("type") != "comment"
                or str(comment.get("parent")) != post["external_id"]
            ):
                continue
            yield {
                "id": f"comment:{comment['id']}",
                "body": plain_text(comment.get("text", "")),
                "author": comment.get("by", ""),
                "created_utc": comment.get("time"),
            }
