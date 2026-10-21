from datetime import datetime, timedelta, timezone
from math import ceil

from collectors.base import CollectionError, Collector, RateLimited, StopCollection
from models import plain_text


class StackExchangeCollector(Collector):
    source = "stackexchange"

    def _collect(self, limit, days):
        searches = [
            (site, query)
            for site in self.settings.stackexchange_sites
            for query in self.settings.stackexchange_queries
        ]
        if not searches:
            raise CollectionError(
                "Configure at least one Stack Exchange site and query"
            )
        cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        for site, query in searches:
            try:
                params = {
                    "site": site,
                    "q": query,
                    "fromdate": cutoff,
                    "order": "desc",
                    "sort": "creation",
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
