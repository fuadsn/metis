"""Nontechnical discovery, source attribution, scope and request-budget checks."""

import json
from datetime import datetime, timezone

import httpx
import pytest

from collectors.discourse import DiscourseCollector
from config import Settings
from models import normalize_post
from pipeline import run_analysis, run_pipeline
from processors.cleaner import clean_posts, rank_candidates
from processors.signals import score_post
from storage import Store

NOW = int(datetime.now(timezone.utc).timestamp())
ISO = datetime.fromtimestamp(NOW - 60, timezone.utc).isoformat()


def post(body, **overrides):
    return normalize_post(
        {
            "id": "1",
            "source": "hackernews",
            "author": "reader",
            "created_utc": NOW - 60,
            "body": body,
            **overrides,
        }
    )


@pytest.mark.parametrize(
    "body,audience",
    [
        (
            "I run a salon. I spend two hours every week chasing missed appointments.",
            "small_business",
        ),
        ("Our shop manually counts inventory every Friday.", "small_business"),
        (
            "I cannot find reliable childcare that covers alternating shifts.",
            "everyday_life",
        ),
        (
            "My family spends hours each week coordinating school pickups.",
            "everyday_life",
        ),
        ("I need a way to manage my family meal plan.", "everyday_life"),
        (
            "I manually enter client invoices into a notebook every month.",
            "small_business",
        ),
    ],
)
def test_nontechnical_problems_qualify_without_software_words(body, audience):
    result = score_post(post(body))
    assert result["lead_quality"] == "opportunity"
    assert audience in result["audiences"]
    assert "developer_tools" not in result["audiences"]
    assert result["score_breakdown"]["audience_context"] == 10


@pytest.mark.parametrize(
    "body",
    [
        "How long should I boil potatoes for dinner?",
        "Our store uses automation daily and everything works well.",
        "I do not spend hours on family chores anymore.",
        '[quote="customer, post:1, topic:42"]I would pay for a family planning service.[/quote]\nThanks for sharing.',
        "I would pay for nothing. We are not willing to pay for any household service.",
    ],
)
def test_routine_advice_quotes_and_negated_burden_do_not_qualify(body):
    result = score_post(post(body))
    assert result["lead_quality"] != "opportunity"


def test_audience_selection_changes_leads_and_keeps_all_candidates(tmp_path):
    store = Store(tmp_path)
    store.upsert(
        [
            post("I manually count inventory in our shop every week."),
            post("Our team manually repeats deployment steps every week.", id="2"),
        ]
    )
    business = run_analysis(
        Settings(audiences=["small_business"], sources=["hackernews"]), store
    )
    assert len(business["leads"]) == 1
    assert business["leads"][0]["post_id"] == "hackernews:1"
    assert len(business["candidates"]) == 2
    assert business["lead_audience_counts"] == {"small_business": 1}
    assert business["ideas"][0]["scoring_method"] == "evidence_brief"
    assert business["ideas"][0]["novelty_score"] is None
    assert business["ideas"][0]["problem_excerpt"] in business["leads"][0]["body"]
    technical = run_analysis(
        Settings(audiences=["developer_tools"], sources=["hackernews"]), store
    )
    assert [p["post_id"] for p in technical["leads"]] == ["hackernews:2"]
    from cli import latest

    assert latest("ideas", store=store, audience="developer_tools")["ideas"]
    assert latest("ideas", store=store, audience="small_business")["ideas"] == []


def test_failed_collection_never_reuses_a_different_audience_scope(tmp_path):
    store = Store(tmp_path)
    run_analysis(Settings(audiences=["developer_tools"], sources=["reddit"]), store)
    result = run_pipeline(
        Settings(
            audiences=["small_business"],
            sources=["reddit"],
            reddit_client_id="",
            reddit_client_secret="",
        ),
        store,
    )
    assert result["status"] == "error"
    assert result["analysis_reused"] is False


def test_default_query_plans_broaden_communities_and_fit_request_cap(monkeypatch):
    for key in [
        "METIS_AUDIENCES",
        "METIS_STACKEXCHANGE_SITES",
        "METIS_STACKEXCHANGE_QUERIES",
    ]:
        monkeypatch.delenv(key, raising=False)
    settings = Settings()
    assert settings.audiences == ["small_business", "everyday_life"]
    sites = {site for site, _ in settings.stackexchange_searches()}
    assert {"freelancing", "parenting", "cooking", "diy", "travel"} <= sites
    assert "stackoverflow" not in sites
    assert len(settings.stackexchange_searches()) * 2 <= 20
    assert (
        len(
            Settings(
                audiences=["small_business", "everyday_life", "developer_tools"]
            ).stackexchange_searches()
        )
        * 2
        <= 20
    )
    with pytest.raises(ValueError, match="audiences"):
        Settings(audiences=["unknown"])


def test_source_and_audience_cli_filters_return_matching_saved_results(
    tmp_path, monkeypatch, capsys
):
    import cli

    store = Store(tmp_path)
    store.upsert([post("Our shop manually checks inventory every week.")])
    run_analysis(Settings(audiences=["small_business"]), store)
    monkeypatch.setattr(cli, "Store", lambda: store)
    assert cli.main(["leads", "--audience", "small_business"]) == 0
    assert len(json.loads(capsys.readouterr().out)["leads"]) == 1
    assert cli.main(["leads", "--audience", "everyday_life"]) == 0
    assert json.loads(capsys.readouterr().out)["leads"] == []


def forum_handler(calls, missing_raw=False, fail_full=False):
    def handler(request):
        calls.append(request)
        if request.url.path == "/search.json":
            assert "in:first" in request.url.params["q"]
            assert (
                "after:" in request.url.params["q"]
                and "before:" in request.url.params["q"]
            )
            return httpx.Response(
                200,
                json={
                    "posts": [
                        {
                            "id": 12,
                            "topic_id": 7,
                            "post_number": 1,
                            "created_at": ISO,
                            "blurb": "I would pay thousands! (Search snippet must not be used.)",
                        }
                    ],
                    "topics": [
                        {"id": 7, "title": "Inventory routine", "posts_count": 3}
                    ],
                },
            )
        if fail_full:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "id": 12,
                "topic_id": 7,
                "post_number": 1,
                "created_at": ISO,
                "username": "original_author",
                "raw": None
                if missing_raw
                else "Our shop manually counts inventory every Friday.",
            },
        )

    return handler


def test_public_forum_fetches_full_posts_deduplicates_and_preserves_provenance():
    calls = []
    with httpx.Client(transport=httpx.MockTransport(forum_handler(calls))) as client:
        result = DiscourseCollector(
            Settings(audiences=["small_business"]), client
        ).collect(limit=10, days=30)
    assert result.status == "success"
    assert len(calls) == 2  # one search plus one full post
    assert len(result.posts) == 1
    p = result.posts[0]
    assert p["id"] == "discourse:community.shopify.com:topic:7"
    assert p["author"] == "original_author"
    assert p["url"] == "https://community.shopify.com/t/7/1"
    assert "thousands" not in p["body"]
    assert (
        rank_candidates(clean_posts(result.posts))[0]["lead_quality"] == "opportunity"
    )


@pytest.mark.parametrize("missing_raw,fail_full", [(True, False), (False, True)])
def test_forum_snippets_never_become_evidence_when_full_post_unavailable(
    missing_raw, fail_full
):
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(forum_handler(calls, missing_raw, fail_full))
    ) as client:
        result = DiscourseCollector(
            Settings(audiences=["small_business"]), client
        ).collect(days=30)
    assert result.posts == []
    assert result.status == "error"
    assert result.errors


def test_forum_host_is_part_of_identity_and_limits_are_bounded():
    calls = []
    with httpx.Client(transport=httpx.MockTransport(forum_handler(calls))) as client:
        result = DiscourseCollector(
            Settings(audiences=["small_business", "everyday_life"]), client
        ).collect(days=30)
    assert result.status == "success"
    assert len({p["id"] for p in result.posts}) == 2
    assert len(calls) <= 30
    assert {p["community"] for p in result.posts} == {
        "community.shopify.com",
        "community.monzo.com",
    }


@pytest.mark.parametrize(
    "body",
    [
        "As a parent with children across multiple schools, there is a payment request every week. The challenge is keeping track of what has been paid.",
        "I have a shop and I am noticing a pattern. Recent changes shift more manual work onto retailers.\n\nStaff must check every SKU for committed inventory before entering the counts.",
    ],
)
def test_firsthand_context_carries_across_sentences_in_a_problem_paragraph(body):
    assert score_post(post(body))["lead_quality"] == "opportunity"


def test_forum_rate_limit_preserves_completed_other_host_and_stops_limited_host(
    monkeypatch,
):
    calls = []
    base = forum_handler(calls)

    def handler(request):
        if request.url.host == "community.monzo.com":
            calls.append(request)
            return httpx.Response(429)
        return base(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = DiscourseCollector(
            Settings(audiences=["small_business", "everyday_life"]), client
        ).collect(days=30)
    assert result.status == "partial"
    assert len(result.posts) == 1
    assert result.posts[0]["community"] == "community.shopify.com"
    assert sum(r.url.host == "community.monzo.com" for r in calls) == 1


@pytest.mark.parametrize(
    "payload",
    [{"errors": ["rejected"]}, {"grouped_search_result": {"error": "rejected"}}],
)
def test_forum_rejected_search_does_not_prevent_other_host_collection(payload):
    calls = []
    base = forum_handler(calls)

    def handler(request):
        if request.url.host == "community.shopify.com":
            calls.append(request)
            return httpx.Response(200, json=payload)
        return base(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = DiscourseCollector(
            Settings(audiences=["small_business", "everyday_life"]), client
        ).collect(days=30)
    assert result.status == "partial"
    assert len(result.posts) == 1
    assert result.posts[0]["community"] == "community.monzo.com"
    assert sum(r.url.host == "community.shopify.com" for r in calls) == 1


def test_audience_hints_from_community_alone_cannot_create_intent():
    p = post(
        "Thank you for the clear explanation and the helpful links.",
        source="discourse",
        community="community.monzo.com",
    )
    assert score_post(p)["audiences"] == ["everyday_life"]
    assert score_post(p)["lead_quality"] == "noise"


@pytest.mark.parametrize(
    "title,body",
    [
        (
            "Encryption SDK for React Native clients",
            "I am looking for a library SDK for our mobile clients and desktop clients.",
        ),
        (
            "Looking for a VS Code AI coding assistant",
            "I am working on a client project. I need a tool for code completion "
            "and managing large codebases in my development workflow.",
        ),
    ],
)
def test_technical_client_requests_are_not_mistaken_for_small_business_problems(
    tmp_path,
    title,
    body,
):
    store = Store(tmp_path)
    p = post(
        body,
        title=title,
        source="stackexchange",
        community="softwarerecs",
    )
    store.upsert([p])
    result = run_analysis(
        Settings(audiences=["small_business", "everyday_life"]), store
    )
    assert result["leads"] == []
    assert result["candidates"][0]["primary_audience"] == "developer_tools"


def test_product_pitch_with_first_person_and_general_burden_is_not_demand():
    p = post(
        "My family struggles with communication every week. "
        "That is what I am building with my side project, a messaging app. "
        "The problem is that users have to manually copy messages. "
        "I would appreciate feedback on the prototype.",
        title="Private messaging for everyone",
    )
    result = score_post(p)
    assert result["lead_quality"] == "noise"
    assert result["priority_score"] == 0


def test_large_forum_searches_remain_within_full_post_and_http_budgets():
    from datetime import timedelta

    calls = []
    posts = {}

    def handler(request):
        calls.append(request)
        if request.url.path == "/search.json":
            day = request.url.params["q"].split("after:")[1].split()[0]
            created = (
                datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
                + timedelta(days=2)
            ).isoformat()
            base_id = len(calls) * 100
            hits = [
                {
                    "id": base_id + i,
                    "topic_id": base_id + i,
                    "post_number": 1,
                    "created_at": created,
                }
                for i in range(50)
            ]
            for h in hits:
                posts[h["id"]] = {
                    **h,
                    "username": "shopkeeper",
                    "raw": "Our shop manually counts stock every week.",
                }
            return httpx.Response(
                200,
                json={
                    "posts": hits,
                    "topics": [
                        {"id": h["topic_id"], "title": "Stock counting"} for h in hits
                    ],
                },
            )
        return httpx.Response(
            200, json=posts[int(request.url.path.split("/")[-1].split(".")[0])]
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = DiscourseCollector(
            Settings(audiences=["small_business", "everyday_life"]), client
        ).collect(limit=500)
    assert result.status == "success"
    assert len(result.posts) == 20
    assert len(calls) == 24
