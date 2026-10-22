import re
from datetime import datetime, timedelta, timezone
from math import ceil

from collectors.base import CollectionError, Collector, StopCollection


class GitHubCollector(Collector):
    source = "github"
    supports_comments = True

    def _headers(self):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "metis/0.2"}
        if self.settings.github_token:
            headers["Authorization"] = "Bearer " + self.settings.github_token
        return headers

    def _collect(self, limit, days):
        headers = self._headers()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        queries = self.settings.github_queries
        per_query = min(100, ceil(limit / len(queries)))
        for query in queries:
            try:
                data = self.request(
                    "GET",
                    "https://api.github.com/search/issues",
                    headers=headers,
                    params={
                        "q": f"{query} is:issue is:open is:public created:>={cutoff}",
                        "order": "desc",
                        "per_page": per_query,
                    },
                )
                if data.get("incomplete_results"):
                    self.result.errors.append(
                        "GitHub returned incomplete search results"
                    )
                for item in data["items"]:
                    if "pull_request" in item:
                        continue
                    self.add(
                        {
                            "id": item["id"],
                            "title": item["title"],
                            "body": item.get("body") or "",
                            "url": item["html_url"],
                            "community": item["repository_url"].split("/repos/")[-1],
                            "author": (item.get("user") or {}).get("login", ""),
                            "created_utc": item["created_at"],
                            "updated_utc": item.get("updated_at"),
                            "num_comments": item.get("comments", 0),
                            "score": (item.get("reactions") or {}).get("+1", 0),
                            "matched_queries": [query],
                            "metadata": {
                                "issue_number": item.get("number"),
                                "author_type": (item.get("user") or {}).get("type", ""),
                                "labels": [
                                    label["name"] for label in item.get("labels", [])
                                ],
                            },
                        }
                    )
            except StopCollection:
                raise
            except CollectionError as exc:
                self.result.errors.append(str(exc))

    def _fetch_comments(self, post, limit):
        repo = post["community"]
        number = str(
            post["metadata"].get("issue_number")
            or post["url"].rstrip("/").split("/")[-1]
        )
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not number.isdigit():
            raise CollectionError("Missing GitHub issue coordinates for comments")
        data = self.request(
            "GET",
            f"https://api.github.com/repos/{repo}/issues/{number}/comments",
            headers=self._headers(),
            params={"per_page": limit, "page": 1},
        )
        for item in data[:limit]:
            user = item.get("user") or {}
            if user.get("type") == "Bot" or user.get("login", "").endswith("[bot]"):
                continue
            yield {
                "id": f"comment:{item['id']}",
                "body": item.get("body") or "",
                "url": item["html_url"],
                "author": user.get("login", ""),
                "created_utc": item["created_at"],
                "updated_utc": item.get("updated_at"),
            }
