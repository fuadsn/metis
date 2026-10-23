import json
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from collectors import COLLECTORS
from collectors.base import CollectionResult
from config import ANALYSIS_VERSION, Settings
from models import normalize_post
from pipeline import collect_posts, run_analysis
from processors import clean_posts, cluster_pain_points, extract_pain_points
from storage import Store

NOW = datetime.now(timezone.utc).timestamp()
ISO_NOW = datetime.now(timezone.utc).isoformat()


def test_default_run_never_calls_deferred_sources_even_with_credentials(
    monkeypatch, tmp_path, capsys
):
    import cli
    import pipeline

    monkeypatch.delenv("METIS_SOURCES", raising=False)
    monkeypatch.setenv("REDDIT_CLIENT_ID", "configured-app")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "configured-secret")
    monkeypatch.setenv("X_BEARER_TOKEN", "configured-token")
    monkeypatch.setattr(pipeline, "Store", lambda: Store(tmp_path))
    called = []

    def free_collector(source):
        class FakeCollector:
            def __init__(self, config):
                pass

            def collect(self, **kwargs):
                called.append(source)
                return CollectionResult(source)

        return FakeCollector

    class DeferredCollector:
        def __init__(self, config):
            pytest.fail("Default v1 collection must not call Reddit or X")

    for source in ("hackernews", "github", "stackexchange"):
        monkeypatch.setitem(COLLECTORS, source, free_collector(source))
    for source in ("reddit", "x", "discourse"):
        monkeypatch.setitem(COLLECTORS, source, DeferredCollector)
    assert cli.main(["run", "--limit", "1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "success"
    assert called == ["hackernews", "github", "stackexchange"]


def settings(**kwargs):
    defaults = dict(
        comment_threads=0,
        reddit_client_id="test-app",
        reddit_client_secret="test-secret",
        x_bearer_token="test-token",
        subreddits=["SaaS"],
        github_queries=["workflow"],
        x_queries=["developer"],
        stackexchange_sites=["stackoverflow"],
        stackexchange_queries=["workflow"],
    )
    return Settings(**{**defaults, **kwargs})


def test_legacy_hn_body_author_date_and_link_survive_processing():
    posts = clean_posts(
        [
            {
                "id": "12",
                "source": "hackernews",
                "title": "Ask HN: Invoice tools?",
                "text": "<p>I am frustrated with manual work.</p>",
                "by": "founder",
                "time": NOW,
                "descendants": 4,
                "score": 1,
            }
        ]
    )
    point = extract_pain_points(posts)[0]
    assert point["body"] == "I am frustrated with manual work."
    assert point["created_utc"] == NOW
    assert point["author"] == "founder"
    assert point["num_comments"] == 4
    assert point["url"] == "https://news.ycombinator.com/item?id=12"
    assert point["source"] == "hackernews"
    assert "frustrated" in point["evidence_excerpt"]


def test_popularity_alone_is_not_a_pain_point():
    posts = clean_posts(
        [
            {
                "id": 1,
                "title": "Beautiful telescope image of a distant galaxy",
                "score": 900,
            }
        ]
    )
    assert extract_pain_points(posts) == []


def test_short_untitled_posts_and_cross_source_ids_are_preserved():
    posts = clean_posts(
        [
            {
                "id": "1",
                "source": "x",
                "body": "Looking for a deployment workaround for my SaaS",
            },
            {
                "id": "1",
                "source": "reddit",
                "title": "Help",
                "body": "I am tired of this manual work",
            },
        ]
    )
    assert {p["id"] for p in posts} == {"x:1", "reddit:1"}
    assert len(extract_pain_points(posts)) == 2


def test_clustering_does_not_match_api_in_capital():
    point = extract_pain_points(
        clean_posts([{"id": "1", "title": "Capital planning is hard to automate"}])
    )[0]
    assert cluster_pain_points([point])[0]["topic"] == "other"


def test_legacy_import_dedup_upsert_and_query_window(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    legacy = {
        "source": "hackernews",
        "posts": [
            {"id": "1", "time": NOW, "title": "Test", "score": 1},
            {"id": "1", "time": NOW, "title": "Test", "score": 2},
        ],
    }
    snapshot = raw / "hackernews_2026-01-01.json"
    snapshot.write_text(json.dumps(legacy))
    store = Store(tmp_path)
    assert store.counts() == {"hackernews": 1}
    result = store.upsert(
        [
            {"id": "1", "source": "hackernews", "time": NOW, "score": 8},
            {"id": "1", "source": "reddit", "created_utc": NOW, "score": 3},
        ]
    )
    assert result == {"new": 1, "updated": 1, "unchanged": 0}
    assert Store(tmp_path).load_posts(sources=["hackernews"])[0]["score"] == 8
    assert len(store.load_posts(since=NOW - 1)) == 2
    assert store.load_posts(since=NOW + 1) == []
    assert json.loads(snapshot.read_text()) == legacy


def test_legacy_import_orders_by_collection_time_across_sources(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name, date, score in [
        ("a", "2026-01-02T00:00:00", 4),
        ("z", "2026-01-01T00:00:00", 1),
    ]:
        (raw / f"{name}.json").write_text(
            json.dumps(
                {
                    "source": "hackernews",
                    "collection_time": date,
                    "posts": [{"id": "1", "score": score}],
                }
            )
        )
    assert Store(tmp_path).load_posts()[0]["score"] == 4


def test_hn_deduplicates_search_results_and_filters_deleted():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "objectID": "1",
                        "created_at_i": int(NOW),
                        "title": "Ask HN: Workflow tools?",
                        "story_text": "<p>Looking for a tool</p>",
                    },
                    {"objectID": "2", "created_at_i": int(NOW), "deleted": True},
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["hackernews"](settings(), client).collect(limit=20, days=30)
    assert result.status == "success"
    assert len(result.posts) == 1
    assert len(result.posts[0]["matched_queries"]) == len(settings().hackernews_queries)
    assert result.posts[0]["body"] == "Looking for a tool"


def test_reddit_uses_oauth_and_preserves_discussion_evidence():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("access_token"):
            assert parse_qs(request.content.decode())["grant_type"] == [
                "client_credentials"
            ]
            return httpx.Response(200, json={"access_token": "granted"})
        assert request.headers["Authorization"] == "Bearer granted"
        assert request.url.host == "oauth.reddit.com"
        return httpx.Response(
            200,
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "id": "abc",
                                "title": "Looking for a deployment tool",
                                "selftext": "Manual work is annoying",
                                "created_utc": NOW,
                                "author": "founder",
                                "subreddit": "SaaS",
                                "permalink": "/r/SaaS/comments/abc/test/",
                                "num_comments": 5,
                            }
                        }
                    ]
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["reddit"](settings(), client).collect(limit=10)
    assert result.status == "success"
    assert result.posts[0]["url"] == "https://www.reddit.com/r/SaaS/comments/abc/test/"
    assert result.posts[0]["body"] == "Manual work is annoying"
    assert len(requests) == 2


def test_reddit_refresh_token_grant():
    def handler(request):
        if request.url.path.endswith("access_token"):
            assert parse_qs(request.content.decode()) == {
                "grant_type": ["refresh_token"],
                "refresh_token": ["refresh"],
            }
            return httpx.Response(200, json={"access_token": "granted"})
        return httpx.Response(200, json={"data": {"children": []}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["reddit"](
            settings(reddit_refresh_token="refresh"), client
        ).collect()
    assert result.status == "success"


def test_github_search_is_public_and_excludes_prs():
    def handler(request):
        assert "is:public" in request.url.params["q"]
        assert "is:issue" in request.url.params["q"]
        return httpx.Response(
            200,
            json={
                "items": [
                    {"pull_request": {}, "id": 7},
                    {
                        "id": 8,
                        "title": "Feature request: Better workflow",
                        "body": "I need a workaround",
                        "html_url": "https://github.com/test/repo/issues/8",
                        "repository_url": "https://api.github.com/repos/test/repo",
                        "created_at": ISO_NOW,
                        "labels": [{"name": "enhancement"}],
                        "user": {"login": "dev"},
                        "comments": 3,
                    },
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["github"](settings(), client).collect()
    assert result.status == "success"
    assert result.posts[0]["community"] == "test/repo"
    assert result.posts[0]["matched_queries"] == ["workflow"]
    assert len(result.posts) == 1


def test_x_seven_day_window_and_read_budget():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-token"
        start = datetime.fromisoformat(
            request.url.params["start_time"].replace("Z", "+00:00")
        )
        assert (datetime.now(timezone.utc) - start).total_seconds() < 7 * 86400
        size = int(request.url.params["max_results"])
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": str(i),
                        "text": "Looking for a better developer tool",
                        "created_at": ISO_NOW,
                        "public_metrics": {"like_count": 3, "reply_count": 2},
                    }
                    for i in range(size)
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["x"](
            settings(x_queries=["one", "two", "three"]), client
        ).collect(limit=15)
    assert result.status == "success"
    assert sum(int(r.url.params["max_results"]) for r in requests) <= 15
    assert len(requests) == 1
    assert result.posts[0]["num_comments"] == 2


def test_stackexchange_namespace_body_and_backoff():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.params["filter"] == "withbody"
        return httpx.Response(
            200,
            json={
                "backoff": 10,
                "quota_remaining": 10,
                "items": [
                    {
                        "question_id": 5,
                        "title": "Workflow &amp; deployment",
                        "body": "<p>Looking for a workaround</p>",
                        "link": "https://stackoverflow.com/questions/5",
                        "creation_date": NOW,
                        "owner": {"user_id": 3},
                        "answer_count": 2,
                    },
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["stackexchange"](
            settings(stackexchange_sites=["stackoverflow", "serverfault"]), client
        ).collect()
    assert result.status == "partial"
    assert len(requests) == 1
    assert result.posts[0]["id"] == "stackexchange:stackoverflow:5"
    assert result.posts[0]["body"] == "Looking for a workaround"


@pytest.mark.parametrize(
    "source,config",
    [
        ("reddit", {"reddit_client_id": "", "reddit_client_secret": ""}),
        ("x", {"x_bearer_token": ""}),
    ],
)
def test_missing_credentials_never_make_a_request(source, config):
    def handler(request):
        pytest.fail("Unconfigured source must not make a request")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS[source](settings(**config), client).collect()
    assert result.status == "unconfigured"
    assert result.requests == 0


@pytest.mark.parametrize("code", [401, 402, 403, 429])
def test_api_denials_and_rate_limits_are_not_empty_success(code):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            code, json={"detail": "sensitive diagnostic that should not be copied"}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["x"](settings(), client).collect()
    assert result.status == "error"
    assert len(requests) == 1
    assert "sensitive diagnostic" not in str(result.errors)
    assert "test-token" not in str(result.errors)


def test_transient_failure_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("collectors.base.time.sleep", lambda _: None)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503 if len(requests) == 1 else 200, json={"data": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["x"](settings(), client).collect()
    assert result.status == "success"
    assert len(requests) == 2


def test_collection_and_analysis_share_store_and_partial_status(tmp_path, monkeypatch):
    class FakeCollector:
        def __init__(self, config):
            pass

        def collect(self, **kwargs):
            post = normalize_post(
                {
                    "id": 1,
                    "source": "github",
                    "title": "Looking for a workflow tool",
                    "body": "I would pay for a deployment workaround",
                    "created_utc": NOW,
                    "url": "https://github.com/example/tool/issues/1",
                }
            )
            return CollectionResult("github", posts=[post, post])

    monkeypatch.setitem(COLLECTORS, "github", FakeCollector)
    config = settings(
        sources=["github", "reddit"], reddit_client_id="", reddit_client_secret=""
    )
    store = Store(tmp_path)
    first = collect_posts(config, store)
    second = collect_posts(config, store)
    assert first["status"] == "partial"
    assert first["new"] == 1
    assert second["new"] == 0
    analysis = run_analysis(config, store)
    assert analysis["posts_processed"] == 1
    assert analysis["supporting_evidence"][0]["lead_type"] == "buying_signal"
    assert analysis["supporting_evidence"][0]["url"].endswith("/issues/1")
    assert analysis["source_counts"] == {"github": 1}
    assert store.load_result("latest_collection.json")["status"] == "partial"


def test_cli_json_stdout_exit_code_and_no_secrets(capsys, monkeypatch, tmp_path):
    import cli

    monkeypatch.setattr(cli, "Store", lambda: Store(tmp_path))
    assert cli.main(["sources", "--sources", "reddit,x"]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["sources"][0]["status"] == "disabled"
    assert cli.main(["collect", "--sources", "typo"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"


@pytest.mark.parametrize(
    "scope,window,reused",
    [
        (["reddit"], 30, True),
        (["github"], 30, False),
        (["reddit"], 7, False),
        (None, 30, False),
    ],
)
def test_failed_collection_preserves_last_analysis_without_mixing_scope(
    tmp_path, scope, window, reused
):
    from pipeline import run_pipeline

    store = Store(tmp_path)
    previous = {
        "schema_version": 2,
        "analysis_version": ANALYSIS_VERSION,
        "status": "success",
        "leads": [{"post_id": f"{(scope or ['github'])[0]}:1"}],
        "window_days": window,
        "selected_audiences": ["small_business", "everyday_life"],
    }
    if scope is not None:
        previous["selected_sources"] = scope
    store.save_result(previous, "latest_analysis.json")
    result = run_pipeline(
        settings(sources=["reddit"], reddit_client_id="", reddit_client_secret=""),
        store,
        days=30,
    )
    assert result["status"] == "error"
    assert result["analysis_reused"] is reused
    if reused:
        assert result["leads"] == previous["leads"]
    else:
        assert "leads" not in result
    assert store.load_result("latest_analysis.json") == previous


def test_request_cap_stops_remaining_queries():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = COLLECTORS["x"](
            settings(x_queries=["developer"] * 20), client
        ).collect()
    assert result.status == "error"
    assert len(requests) == 10
    assert "cap" in result.errors[0]


def test_malformed_response_is_an_error():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="not JSON")
        )
    ) as client:
        result = COLLECTORS["x"](settings(), client).collect()
    assert result.status == "error"
    assert "invalid JSON" in result.errors[0]


def test_cli_logging_does_not_expose_query_string_credentials(
    caplog, capsys, monkeypatch, tmp_path
):
    import logging

    import cli
    import pipeline

    key = "test-sensitive-api-key"
    monkeypatch.setenv("STACKEXCHANGE_KEY", key)
    monkeypatch.setattr(pipeline, "Store", lambda: Store(tmp_path))
    real_client = httpx.Client

    def handler(request):
        assert request.url.params["key"] == key
        return httpx.Response(200, json={"items": [], "quota_remaining": 100})

    monkeypatch.setattr(
        "collectors.base.httpx.Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    with caplog.at_level(logging.INFO):
        assert cli.main(["collect", "--sources", "stackexchange", "--limit", "1"]) == 0
    output = capsys.readouterr()
    assert key not in output.out + output.err + caplog.text
    assert json.loads(output.out)["status"] == "success"
