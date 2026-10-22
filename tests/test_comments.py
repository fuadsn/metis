from datetime import datetime, timezone

import httpx
import pytest

from collectors import COLLECTORS
from config import Settings
from models import normalize_post
from pipeline import collect_posts, run_analysis
from storage import Store

NOW = datetime.now(timezone.utc).timestamp()
ISO = datetime.now(timezone.utc).isoformat()


def settings(**overrides):
    return Settings(
        **{
            "sources": ["github"],
            "hackernews_queries": ["workflow"],
            "github_queries": ["workflow"],
            "stackexchange_sites": ["stackoverflow"],
            "stackexchange_queries": ["workflow"],
            "comment_threads": 1,
            "comments_per_thread": 2,
            **overrides,
        }
    )


def issue(number, body="We manually repeat deployment steps every week."):
    return {
        "id": number,
        "number": number,
        "title": "Deployment workflow",
        "body": body,
        "html_url": f"https://github.com/test/repo/issues/{number}",
        "repository_url": "https://api.github.com/repos/test/repo",
        "created_at": ISO,
        "comments": 5,
        "user": {"login": "author"},
    }


def test_hn_fetches_bounded_top_level_comments_only_on_promising_threads():
    requests = []

    def handler(request):
        requests.append(request.url.path)
        if request.url.host == "hn.algolia.com":
            return httpx.Response(
                200,
                json={
                    "hits": []
                    if request.url.params["tags"] == "comment"
                    else [
                        {
                            "objectID": "1",
                            "created_at_i": int(NOW),
                            "title": "Ask HN: Deployment workflow",
                            "story_text": "We would pay for a deployment tool.",
                            "num_comments": 20,
                        }
                    ]
                },
            )
        item = int(request.url.path.split("/")[-1].split(".")[0])
        if item < 100:
            return httpx.Response(
                200,
                json={
                    "id": item,
                    "type": "story",
                    "time": NOW,
                    "title": "Deployment workflow"
                    if item == 1
                    else "Picture of a galaxy",
                    "text": "We would pay for a deployment tool."
                    if item == 1
                    else "An interesting picture.",
                    "kids": [101, 102, 103],
                    "descendants": 20,
                },
            )
        return httpx.Response(
            200,
            json={
                "id": item,
                "type": "comment",
                "parent": 1,
                "time": NOW,
                "by": "reader",
                "text": "<p>We manually repeat this work too.</p>",
                "deleted": item == 101,
                "kids": [999],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["hackernews"](settings(), client).collect(limit=2, days=30)
    assert result.status == "success"
    assert result.comment_requests == 3
    assert result.comment_threads == 1
    assert len(requests) == 5
    assert len(result.comments) == 1
    comment = result.comments[0]
    assert comment["id"] == "hackernews:comment:102"
    assert comment["parent_id"] == "hackernews:1"
    assert comment["title"] == ""
    assert comment["url"] == "https://news.ycombinator.com/item?id=102"
    assert comment["body"] == "We manually repeat this work too."


@pytest.mark.parametrize("enabled", [True, False])
def test_github_comment_selection_bounds_bot_filtering_and_id_namespace(enabled):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/search/issues":
            return httpx.Response(
                200,
                json={"items": [issue(1), issue(2, "How do I fix a Docker error?")]},
            )
        assert request.url.path == "/repos/test/repo/issues/1/comments"
        assert request.url.params["per_page"] == "2"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "body": "We would pay for this deployment tool.",
                    "html_url": "https://github.com/test/repo/issues/1#issuecomment-1",
                    "user": {"login": "other"},
                    "created_at": ISO,
                },
                {"id": 2, "user": {"type": "Bot"}, "body": "Automatic comment"},
            ],
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["github"](
            settings(comment_threads=1 if enabled else 0), client
        ).collect(limit=2)
    assert result.status == "success"
    assert len(requests) == (2 if enabled else 1)
    if enabled:
        assert result.comments[0]["id"] == "github:comment:1"
        assert result.comments[0]["parent_id"] == "github:1"
        assert result.comments[0]["url"].endswith("#issuecomment-1")
    else:
        assert result.comments == []


def test_comment_rate_limit_preserves_posts_and_stops_remaining_threads():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/search/issues":
            return httpx.Response(200, json={"items": [issue(1), issue(2)]})
        return httpx.Response(429)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["github"](settings(comment_threads=2), client).collect(
            limit=2
        )
    assert result.status == "partial"
    assert len(result.posts) == 2
    assert len(requests) == 2
    assert result.comment_requests == 1
    assert "rate limit" in result.errors[0]


def test_stackexchange_unknown_comment_count_and_backoff_keep_attributed_comments():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("search/advanced"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "question_id": 42,
                            "title": "Deployment workflow",
                            "body": "<p>We manually repeat deployment steps every week.</p>",
                            "creation_date": NOW,
                            "link": "https://stackoverflow.com/questions/42",
                        }
                    ],
                    "quota_remaining": 50,
                },
            )
        assert request.url.path == "/2.3/questions/42/comments"
        assert request.url.params["sort"] == "votes"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "comment_id": 1,
                        "body": "<p>We would pay for a deployment tool.</p>",
                        "owner": {"user_id": 7},
                        "creation_date": NOW,
                    }
                ],
                "backoff": 10,
                "quota_remaining": 49,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["stackexchange"](settings(), client).collect(
            limit=1, days=30
        )
    assert result.status == "partial"
    assert len(requests) == 2
    comment = result.comments[0]
    assert comment["id"] == "stackexchange:stackoverflow:comment:1"
    assert comment["parent_id"] == "stackexchange:stackoverflow:42"
    assert comment["author"] == "7"
    assert comment["url"].endswith("#comment1_42")


def test_pipeline_persists_comments_separately_and_repeat_runs_do_not_duplicate(
    tmp_path, monkeypatch
):
    from collectors.base import CollectionResult

    parent = normalize_post(
        {
            "id": 1,
            "source": "github",
            "body": "We manually repeat deployment steps every week.",
            "created_utc": NOW,
        }
    )
    comment = normalize_post(
        {
            "id": "comment:1",
            "source": "github",
            "kind": "comment",
            "parent_id": "github:1",
            "body": "I would pay for a deployment tool.",
            "created_utc": NOW,
        }
    )

    class FakeCollector:
        def __init__(self, config):
            pass

        def collect(self, **kwargs):
            return CollectionResult("github", posts=[parent], comments=[comment])

    monkeypatch.setitem(COLLECTORS, "github", FakeCollector)
    store = Store(tmp_path)
    first = collect_posts(settings(), store)
    second = collect_posts(settings(), store)
    assert first["collected"] == 1
    assert first["comments_collected"] == 1
    assert first["new"] == 2
    assert second["new"] == 0
    assert store.counts() == {"github": 2}
    result = run_analysis(settings(), store)
    assert result["comments_processed"] == 1
    assert result["leads"] == []
    assert len(result["supporting_evidence"]) == 2


def test_relevant_ask_hn_gets_bounded_exploratory_comments_without_root_intent():
    def handler(request):
        if request.url.host == "hn.algolia.com":
            return httpx.Response(
                200,
                json={
                    "hits": []
                    if request.url.params["tags"] == "comment"
                    else [
                        {
                            "objectID": "1",
                            "created_at_i": int(NOW),
                            "title": "Ask HN: How has your software team adapted its process?",
                            "story_text": "I am interested in your experiences.",
                            "num_comments": 3,
                        }
                    ]
                },
            )
        if request.url.path.endswith("/1.json"):
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "type": "story",
                    "title": "Ask HN: How has your software team adapted its process?",
                    "text": "I am interested in your experiences.",
                    "time": NOW,
                    "kids": [2],
                    "descendants": 1,
                },
            )
        return httpx.Response(
            200,
            json={
                "id": 2,
                "type": "comment",
                "parent": 1,
                "by": "reader",
                "time": NOW,
                "text": "We would pay for a tool to automate this workflow.",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["hackernews"](settings(), client).collect(limit=1, days=30)
    assert result.status == "success"
    assert result.comment_threads == 1
    assert len(result.comments) == 1


def test_hn_comment_retries_stay_inside_extra_request_budget(monkeypatch):
    monkeypatch.setattr("collectors.base.time.sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.host == "hn.algolia.com":
            return httpx.Response(
                200,
                json={
                    "hits": []
                    if request.url.params["tags"] == "comment"
                    else [
                        {
                            "objectID": "1",
                            "created_at_i": int(NOW),
                            "title": "Ask HN: How has your software team adapted its process?",
                            "story_text": "I am interested in your experiences.",
                            "num_comments": 3,
                        }
                    ]
                },
            )
        if request.url.path.endswith("/1.json"):
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "type": "story",
                    "title": "Looking for a deployment tool",
                    "time": NOW,
                    "kids": [2, 3, 4],
                    "descendants": 3,
                },
            )
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["hackernews"](
            settings(comments_per_thread=2), client
        ).collect(limit=1, days=30)
    assert result.status == "partial"
    assert result.comment_requests == 3
    assert len(calls) == 5
    assert len(result.posts) == 1
