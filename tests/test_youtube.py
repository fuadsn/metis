from datetime import datetime, timedelta, timezone

import httpx
import pytest

from collectors.youtube import YouTubeCollector
from config import Settings
from pipeline import run_analysis, source_status
from storage import Store

VIDEO = "abcdefghijk"
SECOND = "zyxwvutsrqp"
NOW = datetime.now(timezone.utc)


def settings(**overrides):
    return Settings(
        **{
            "sources": ["youtube"],
            "youtube_api_key": "test-secret",
            "youtube_video_ids": [VIDEO],
            **overrides,
        }
    )


def comment(identifier="comment-1", age=3, body=None, author="UC-account"):
    return {
        "snippet": {
            "topLevelComment": {
                "id": identifier,
                "snippet": {
                    "textOriginal": body
                    or "Our shop manually reconciles inventory every week.",
                    "publishedAt": (NOW - timedelta(days=age)).isoformat(),
                    "updatedAt": NOW.isoformat(),
                    "likeCount": 4,
                    "authorChannelId": {"value": author},
                },
            }
        }
    }


def collect(handler, config=None, **kwargs):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return YouTubeCollector(config or settings(), client).collect(**kwargs)


def test_missing_key_never_makes_a_network_request():
    def unexpected(request):
        pytest.fail("Unconfigured YouTube must not access the network")

    result = collect(unexpected, settings(youtube_api_key=""))
    assert result.status == "unconfigured"
    assert result.requests == 0
    assert "test-secret" not in repr(settings())


def test_comment_date_author_identity_and_link_not_creator_intent(tmp_path):
    def handler(request):
        assert request.headers["x-goog-api-key"] == "test-secret"
        assert "test-secret" not in str(request.url)
        assert request.url.params["textFormat"] == "plainText"
        assert request.url.params["order"] == "time"
        return httpx.Response(200, json={"items": [comment()]})

    result = collect(handler)
    assert result.status == "success"
    assert result.posts == []
    post = result.comments[0]
    assert post["id"] == "youtube:comment-1"
    assert post["kind"] == "comment" and post["title"] == ""
    assert post["author"] == "UC-account"
    assert post["parent_id"] == f"youtube:video:{VIDEO}"
    assert post["url"].endswith("&lc=comment-1")
    assert post["created_utc"] < post["updated_utc"]
    store = Store(tmp_path)
    store.upsert(result.comments)
    analysis = run_analysis(settings(), store)
    assert len(analysis["leads"]) == 1
    assert analysis["clusters"][0]["repeated_need"] is False
    assert analysis["leads"][0]["willingness_to_pay"] == "not_established"


def test_old_comments_are_not_refreshed_by_edits_and_duplicates_are_removed():
    missing_date = comment("missing")
    del missing_date["snippet"]["topLevelComment"]["snippet"]["publishedAt"]
    result = collect(
        lambda r: httpx.Response(
            200,
            json={
                "items": [
                    comment(),
                    comment(),
                    comment("old", age=190),
                    comment("future", age=-2),
                    missing_date,
                ]
            },
        )
    )
    assert len(result.comments) == 1


def test_discovery_is_bounded_deduplicated_and_does_not_exclude_old_videos():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/search"):
            assert "publishedAfter" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": {"videoId": VIDEO},
                            "snippet": {
                                "title": "I would pay for family software",
                                "channelId": "creator",
                                "publishedAt": "2020-01-01T00:00:00Z",
                            },
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={"items": [comment(body="Thank you for explaining this clearly!")]},
        )

    result = collect(
        handler,
        settings(
            youtube_video_ids=[], youtube_queries=[f"query {i}" for i in range(8)]
        ),
    )
    assert result.requests == 5 and result.comment_threads == 1
    assert len(result.comments[0]["matched_queries"]) == 4
    from processors.cleaner import clean_posts, rank_candidates

    assert rank_candidates(clean_posts(result.comments))[0]["lead_quality"] == "noise"


def test_limit_applies_to_comments_across_videos():
    calls = []

    def handler(request):
        calls.append(request)
        count = int(request.url.params["maxResults"])
        return httpx.Response(
            200, json={"items": [comment(str(i)) for i in range(count)]}
        )

    result = collect(handler, settings(youtube_video_ids=[VIDEO, SECOND]), limit=2)
    assert len(result.comments) == 2
    assert len(calls) == 1


@pytest.mark.parametrize(
    "reason,status", [("commentsDisabled", 403), ("videoNotFound", 404)]
)
def test_unavailable_video_skips_to_next_video(reason, status):
    def handler(request):
        if request.url.params["videoId"] == VIDEO:
            return httpx.Response(
                status, json={"error": {"errors": [{"reason": reason}]}}
            )
        return httpx.Response(200, json={"items": [comment()]})

    result = collect(handler, settings(youtube_video_ids=[VIDEO, SECOND]))
    assert result.status == "partial"
    assert len(result.comments) == 1
    assert result.comment_requests == 2


@pytest.mark.parametrize(
    "status,reason",
    [(403, "quotaExceeded"), (403, "forbidden"), (400, "keyInvalid"), (302, "")],
)
def test_access_failure_stops_without_echoing_response_or_key(status, reason):
    result = collect(
        lambda r: httpx.Response(
            status,
            json={
                "error": {
                    "message": "test-secret",
                    "errors": [{"reason": reason}],
                }
            },
        ),
        settings(youtube_video_ids=[VIDEO, SECOND]),
    )
    assert result.status == "error" and result.requests == 1
    assert "test-secret" not in str(result.summary())


def test_youtube_is_optional_and_reports_missing_key(monkeypatch):
    monkeypatch.delenv("METIS_SOURCES", raising=False)
    status = source_status(Settings(youtube_api_key=""))
    row = next(row for row in status["sources"] if row["source"] == "youtube")
    assert row["status"] == "disabled" and row["missing"] == ["YOUTUBE_API_KEY"]
    assert len(status["research_sources"]) == 3
    assert all(not item["automatic_collection"] for item in status["research_sources"])


@pytest.mark.parametrize(
    "overrides",
    [
        {"youtube_video_ids": ["https://youtube.com/watch?v=x"]},
        {"youtube_video_ids": [VIDEO] * 9},
        {"youtube_comments_per_video": 0},
        {"youtube_comments_per_video": 101},
        {"youtube_queries": []},
    ],
)
def test_invalid_configuration(overrides):
    with pytest.raises(ValueError):
        settings(**overrides)
