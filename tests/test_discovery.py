"""Behavioral checks for community discovery and historical evidence."""

from datetime import datetime, timezone

import httpx
import pytest

from collectors.hackernews import HNCollector
from collectors.search import age_windows
from config import Settings
from models import normalize_post
from pipeline import run_analysis
from processors.signals import score_post
from storage import Store

NOW = int(datetime.now(timezone.utc).timestamp())


@pytest.fixture(autouse=True)
def developer_research_scope(monkeypatch):
    monkeypatch.setenv("METIS_AUDIENCES", "developer_tools")


def evidence(source="hackernews", age=0, **overrides):
    return normalize_post(
        {
            "id": "1",
            "source": source,
            "author": "founder",
            "title": "Deployment workflow",
            "body": "Our team manually repeats deployment steps every week.",
            "created_utc": NOW - age * 86400,
            **overrides,
        }
    )


def test_recent_and_historical_windows_do_not_overlap_or_exceed_request():
    assert age_windows(7, NOW) == [("recent", NOW - 7 * 86400, NOW)]
    recent, historical = age_windows(180, NOW)
    assert recent[1] == historical[2] + 1
    assert historical[1] == NOW - 180 * 86400
    assert recent[2] == NOW


def test_history_gets_same_intent_score_and_explicit_age_without_claiming_current_demand():
    recent = score_post(evidence(age=1), now=NOW)
    old = score_post(evidence(age=120), now=NOW)
    assert recent["priority_score"] == old["priority_score"]
    assert recent["freshness"] == "recent"
    assert old["freshness"] == "historical"
    assert old["age_days"] == 120
    assert old["current_need_verified"] is False
    assert old["lead_quality"] == "opportunity"


def test_github_support_cannot_create_or_boost_opportunities_or_repeat_counts(tmp_path):
    store = Store(tmp_path)
    store.upsert([evidence(), evidence("github", age=100, author="someone_else")])
    settings = Settings(sources=["hackernews", "github"])
    result = run_analysis(settings, store)
    assert result["window_days"] == 180
    assert result["lead_source_counts"] == {"hackernews": 1}
    assert result["supporting_evidence_count"] == 1
    cluster = result["clusters"][0]
    assert cluster["repeat_evidence_count"] == 1
    assert cluster["repeated_need"] is False
    assert len(cluster["supporting_evidence"]) == 1
    assert cluster["priority_score"] == result["leads"][0]["priority_score"]
    github_only = run_analysis(Settings(sources=["github"]), store)
    assert github_only["leads"] == github_only["clusters"] == github_only["ideas"] == []
    assert github_only["supporting_evidence"][0]["source"] == "github"


def test_primary_evidence_across_periods_keeps_dates_and_independent_counts(tmp_path):
    store = Store(tmp_path)
    store.upsert(
        [
            evidence(age=120),
            evidence(
                "stackexchange",
                age=5,
                author="second",
                body="Our team repeats repetitive deployment steps weekly.",
            ),
        ]
    )
    result = run_analysis(Settings(sources=["hackernews", "stackexchange"]), store)
    assert result["lead_age_counts"] == {"historical": 1, "recent": 1}
    assert result["clusters"][0]["repeated_need"] is True
    assert result["clusters"][0]["evidence_span_days"] == 115
    assert (
        "same_task_obstacle_and_audience_rules"
        in result["clusters"][0]["repeat_validation"]
    )


def test_hn_searches_both_periods_and_nested_comment_text_with_original_attribution():
    calls = []

    def handler(request):
        calls.append(request)
        start, end = [
            int(part.split("=")[1])
            for part in request.url.params["numericFilters"].split(",")
        ]
        historical = end < NOW - 86400
        assert (
            request.url.params["restrictSearchableAttributes"]
            == "title,story_text,comment_text"
        )
        assert "author" not in request.url.params["restrictSearchableAttributes"]
        if request.url.params["tags"] == "comment":
            hit = {
                "objectID": "11" if historical else "12",
                "created_at_i": start + 1,
                "comment_text": "<p>Our team would pay for a deployment tool.</p>",
                "story_title": "A discussion about software",
                "story_id": 1,
                "parent_id": 7,
                "author": "reply_author",
            }
        else:
            hit = {
                "objectID": "1" if historical else "2",
                "created_at_i": start + 1,
                "title": "Ask HN: Deployment workflow",
                "story_text": "I need a deployment tool.",
                "author": "original_author",
            }
        return httpx.Response(200, json={"hits": [hit]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = HNCollector(Settings(hackernews_queries=["workflow"]), client).collect(
            limit=4
        )
    assert result.status == "success"
    assert len(calls) == 4
    assert len(result.posts) == len(result.comments) == 2
    comment = result.comments[0]
    assert comment["title"] == ""
    assert comment["author"] == "reply_author"
    assert comment["parent_id"] == "hackernews:1"
    assert comment["metadata"]["immediate_parent_id"] == 7
    assert comment["url"] == "https://news.ycombinator.com/item?id=12"
    assert comment["parent_url"] == "https://news.ycombinator.com/item?id=1"
    assert "reply_author" not in comment["body"]


def test_comment_only_partial_search_keeps_evidence_after_rate_limit():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 3:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "objectID": "12",
                        "story_id": 1,
                        "created_at_i": NOW - 60,
                        "comment_text": "I would pay for a deployment tool.",
                        "author": "reader",
                    }
                ]
                if request.url.params["tags"] == "comment"
                else []
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = HNCollector(
            Settings(hackernews_queries=["workflow", "manual"]), client
        ).collect(days=30)
    assert result.status == "partial"
    assert len(result.comments) == 1
    assert result.posts == []
    assert len(calls) == 3


def test_zero_comment_setting_disables_comment_search_as_well_as_enrichment():
    def handler(request):
        assert request.url.params["tags"] == "ask_hn"
        return httpx.Response(200, json={"hits": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = HNCollector(Settings(comment_threads=0), client).collect()
    assert result.status == "success"
    assert result.requests == 10
    assert result.comments == []


@pytest.mark.parametrize(
    "body",
    [
        "To deploy the software, manually run the following command.",
        "Users could manually configure this developer tool.",
        "Our developer team ran this manually once to fix a typo.",
        "A feature request for software with no description of a need.",
    ],
)
def test_tutorials_one_off_tasks_and_feature_labels_are_not_primary_opportunities(body):
    result = score_post(evidence(body=body))
    assert result["lead_quality"] != "opportunity"


def test_direct_solution_request_and_firsthand_recurring_cost_qualify():
    assert (
        score_post(evidence(body="I need a Linux CLI tool to configure new repos."))[
            "lead_quality"
        ]
        == "opportunity"
    )
    assert (
        score_post(
            evidence(body="Our team wastes three hours every week on deployment.")
        )["lead_quality"]
        == "opportunity"
    )


@pytest.mark.parametrize(
    "body",
    [
        "A business building EVs in the US would pay less for electricity.",
        "This is a faster alternative to our database software.",
        "We use this integration as a convenient alternative to PayPal.",
        "Say you're looking for a tool; our software will find one for you.",
        "We have a working MVP for repetitive manual work and are looking for early testers.",
        "I'm curious how engineers handle workflows. Do you rely mostly on manual work?",
        "I do wish there was another way to solve the political dispute.",
    ],
)
def test_observed_generic_statements_and_promotions_do_not_qualify(body):
    assert score_post(evidence(body=body))["lead_quality"] != "opportunity"


def test_hn_search_budget_stops_extra_queries_and_preserves_completed_matches():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "objectID": "1",
                        "created_at_i": NOW - 60,
                        "title": "Ask HN: I need a deployment tool",
                        "story_text": "",
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = HNCollector(
            Settings(comment_threads=0, hackernews_queries=["workflow"] * 21), client
        ).collect(days=30)
    assert len(calls) == 20
    assert result.status == "partial"
    assert len(result.posts) == 1
    assert "request cap" in result.errors[0]


@pytest.mark.parametrize(
    "body",
    [
        "I'm looking for material recommendations about open source software.",
        "I am looking for a software developer engineer role.",
        "We are looking for software engineers for our product team.",
        "I am a PhD student looking for dyslexic software engineers for a study.",
        "What is the alternative to Library.configure() for this API?",
        "Any other alternative to notify events in Flutter?",
        "I'm trying to understand how engineers handle repetitive drawing creation in their workflow.",
        "I was looking for software that would solve this workflow, but found it.",
    ],
)
def test_recruiting_surveys_and_code_alternatives_are_not_opportunities(body):
    assert score_post(evidence(body=body))["lead_quality"] != "opportunity"


@pytest.mark.parametrize(
    "body",
    [
        "I need a program to do a thing, I'll use AI instead of looking for software.",
        "I'm looking for a SaaS tool. Disclosure: I'm affiliated with a competing product.",
    ],
)
def test_generic_hypotheticals_and_disclosed_competitor_research_are_not_buyer_signals(
    body,
):
    assert score_post(evidence(body=body))["lead_quality"] != "opportunity"


@pytest.mark.parametrize(
    "body",
    [
        "I am looking for a software tool for our developers.",
        "We are looking for onboarding software for engineers.",
    ],
)
def test_searching_for_tools_for_developers_is_not_recruiting(body):
    assert score_post(evidence(body=body))["lead_quality"] == "opportunity"
