"""Optional, bounded public comment sampling through the YouTube Data API."""

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from models import normalize_post, timestamp

from .base import CollectionError, Collector, StopCollection

API = "https://www.googleapis.com/youtube/v3/"


class YouTubeCollector(Collector):
    source = "youtube"
    search_request_limit = 20  # Includes discovery, comments, and retry attempts.

    def missing_configuration(self):
        return [] if self.settings.youtube_api_key else ["YOUTUBE_API_KEY"]

    def check_source_error(self, response):
        try:
            reasons = {
                item.get("reason")
                for item in response.json().get("error", {}).get("errors", [])
            }
        except (ValueError, TypeError, AttributeError):
            reasons = set()
        if reasons & {"quotaExceeded", "dailyLimitExceeded"}:
            raise StopCollection("YouTube quota exhausted; collection stopped")
        if reasons & {"commentsDisabled", "videoNotFound"}:
            raise CollectionError("YouTube video unavailable or comments disabled")
        if response.status_code == 400:
            raise StopCollection(
                "YouTube rejected the request; check API key and configuration"
            )

    def api(self, resource, **params):
        # Header avoids API keys in request URLs and HTTP access logs.
        return self.request(
            "GET",
            API + resource,
            headers={"X-Goog-Api-Key": self.settings.youtube_api_key},
            params=params,
        )

    def _collect(self, limit, days):
        now = datetime.now(timezone.utc).timestamp()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        videos = {video: {"queries": []} for video in self.settings.youtube_video_ids}
        if not videos:
            for query in self.settings.youtube_queries[:4]:
                data = self.api(
                    "search", part="snippet", type="video", q=query, maxResults=2
                )
                for item in data.get("items", []):
                    video = item.get("id", {}).get("videoId", "")
                    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
                        continue
                    details = videos.setdefault(
                        video, {**item.get("snippet", {}), "queries": []}
                    )
                    details["queries"].append(query)
        seen = set()
        for video, details in list(videos.items())[:8]:
            remaining = limit - len(self.result.comments)
            if remaining <= 0:
                break
            self.result.comment_threads += 1
            before = self.result.requests
            try:
                data = self.api(
                    "commentThreads",
                    part="snippet",
                    videoId=video,
                    order="time",
                    textFormat="plainText",
                    maxResults=min(remaining, self.settings.youtube_comments_per_video),
                )
            except StopCollection:
                raise
            except CollectionError as exc:
                self.result.errors.append(f"Video {video}: {exc}")
                continue
            finally:
                self.result.comment_requests += self.result.requests - before
            for item in data.get("items", []):
                if len(self.result.comments) >= limit:
                    break
                top = item.get("snippet", {}).get("topLevelComment", {})
                snippet = top.get("snippet", {})
                comment_id = top.get("id")
                published = timestamp(snippet.get("publishedAt"))
                body = snippet.get("textOriginal") or snippet.get("textDisplay") or ""
                if not comment_id or comment_id in seen or not body.strip():
                    continue
                if published is None or not cutoff <= published <= now:
                    continue
                seen.add(comment_id)
                self.result.comments.append(
                    normalize_post(
                        {
                            "id": comment_id,
                            "kind": "comment",
                            "body": body,
                            "parent_id": f"youtube:video:{video}",
                            "parent_url": f"https://www.youtube.com/watch?v={video}",
                            "url": f"https://www.youtube.com/watch?v={video}&lc={quote(comment_id, safe='')}",
                            "community": details.get("channelId") or "youtube",
                            "author": snippet.get("authorChannelId", {}).get(
                                "value", ""
                            ),
                            "created_utc": published,
                            "updated_utc": snippet.get("updatedAt"),
                            "score": snippet.get("likeCount", 0),
                            "matched_queries": details["queries"],
                            "metadata": {
                                "parent_title": details.get("title", ""),
                                "video_id": video,
                                "collection_method": "youtube_data_api",
                                "sample_scope": "latest_top_level_comments; one page per video; replies not collected",
                            },
                        },
                        self.source,
                    )
                )
