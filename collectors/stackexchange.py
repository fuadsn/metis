from math import ceil

from collectors.base import CollectionError, Collector, RateLimited, StopCollection
from collectors.search import age_windows
from models import plain_text


class StackExchangeCollector(Collector):
    source = "stackexchange"
    supports_comments = True
    search_request_limit = 20

    def _collect(self, limit, days):
        searches = [
            (site, query, band, start, end)
            for site, query in self.settings.stackexchange_searches()
            for band, start, end in age_windows(days)
        ]
        if not searches:
            raise CollectionError(
                "Configure at least one Stack Exchange site and query"
            )
        for site, query, band, start, end in searches:
            try:
                params = {
                    "site": site,
                    "q": query,
                    "fromdate": start,
                    "todate": end,
                    "order": "desc",
                    "sort": "relevance",
                    "closed": "false",
                    "filter": "withbody",
                    "pagesize": min(100, ceil(limit / len(searches))),
                }
                if self.settings.stackexchange_key:
                    params["key"] = self.settings.stackexchange_key
                data = self.request(
                    "GET",
                    "https://api.stackexchange.com/2.3/search/advanced",
                    params=params,
                )
                if data.get("error_id"):
                    raise CollectionError("Stack Exchange rejected the search request")
                for item in data["items"]:
                    self.add(
                        {
                            "id": f"{site}:{item['question_id']}",
                            "community": site,
                            "title": plain_text(item["title"]),
                            "body": plain_text(item.get("body", "")),
                            "url": item["link"],
                            "author": str((item.get("owner") or {}).get("user_id", "")),
                            "created_utc": item["creation_date"],
                            "updated_utc": item.get("last_activity_date"),
                            "score": item.get("score", 0),
                            "num_comments": item.get("comment_count", 0),
                            "matched_queries": [query],
                            "metadata": {
                                "discovery": "text_search",
                                "age_band": band,
                                "comment_count_unknown": "comment_count" not in item,
                                "tags": item.get("tags", []),
                                "answer_count": item.get("answer_count", 0),
                                "is_answered": item.get("is_answered", False),
                            },
                        }
                    )
                if data.get("backoff") or data.get("quota_remaining") == 0:
                    raise RateLimited(
                        "Stack Exchange requested backoff or exhausted quota; stopped this run"
                    )
            except StopCollection:
                raise
            except CollectionError as exc:
                self.result.errors.append(str(exc))

    def _fetch_comments(self, post, limit):
        question_id = post["external_id"].split(":")[-1]
        if not question_id.isdigit():
            raise CollectionError("Missing Stack Exchange question ID for comments")
        params = {
            "site": post["community"],
            "filter": "withbody",
            "pagesize": limit,
            "sort": "votes",
            "order": "desc",
        }
        if self.settings.stackexchange_key:
            params["key"] = self.settings.stackexchange_key
        data = self.request(
            "GET",
            f"https://api.stackexchange.com/2.3/questions/{question_id}/comments",
            params=params,
        )
        if data.get("error_id"):
            raise CollectionError("Stack Exchange rejected the comments request")
        for item in data["items"][:limit]:
            yield {
                "id": f"{post['community']}:comment:{item['comment_id']}",
                "body": plain_text(item.get("body", "")),
                "url": item.get("link")
                or f"{post['url'].split('#')[0]}#comment{item['comment_id']}_{question_id}",
                "author": str((item.get("owner") or {}).get("user_id", "")),
                "created_utc": item["creation_date"],
                "score": item.get("score", 0),
            }
        if data.get("backoff") or data.get("quota_remaining") == 0:
            raise RateLimited(
                "Stack Exchange requested backoff or exhausted quota; stopped this run"
            )
