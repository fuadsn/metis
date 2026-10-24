"""Source context qualifies candidate evidence without assuming verified demand."""

from datetime import datetime, timezone

import httpx
import pytest

from collectors.discourse import DiscourseCollector
from config import Settings
from models import normalize_post
from pipeline import run_analysis, source_status
from processors.signals import score_post
from storage import Store


def post(source="hackernews", community="hackernews", **overrides):
    return normalize_post(
        {
            "id": "1",
            "source": source,
            "community": community,
            "author": "owner",
            "created_utc": datetime.now(timezone.utc).timestamp(),
            "title": "Inventory counting",
            "body": "Our shop manually reconciles inventory every week.",
            **overrides,
        }
    )


@pytest.mark.parametrize("host", ["community.shopify.com", "community.monzo.com"])
def test_vendor_workflow_can_be_a_candidate_without_claiming_verified_demand(
    host, tmp_path
):
    store = Store(tmp_path)
    store.upsert(
        [
            post(
                "discourse",
                host,
                body="I would pay for an inventory tool for our shop.",
            )
        ]
    )
    result = run_analysis(Settings(sources=["discourse"]), store)
    assert len(result["leads"]) == 1
    lead = result["leads"][0]
    assert lead["source_context"] == "vendor_community"
    assert lead["current_need_verified"] is False
    assert lead["willingness_to_pay"] == "stated_in_text_unverified"
    assert result["clusters"][0]["repeated_need"] is False


def test_vendor_and_independent_report_can_form_an_unverified_theme(tmp_path):
    store = Store(tmp_path)
    primary = post()
    store.upsert(
        [
            primary,
            post(
                "discourse",
                "community.shopify.com",
                author="merchant",
                body="My shop manually checks inventory every Friday.",
            ),
        ]
    )
    result = run_analysis(Settings(sources=["hackernews", "discourse"]), store)
    cluster = result["clusters"][0]
    assert len(result["leads"]) == 2
    assert len(cluster["supporting_evidence"]) == 0
    assert (
        cluster["repeat_evidence_count"] == cluster["independent_community_count"] == 2
    )
    assert cluster["corroboration"] == "cross_platform_problem"
    assert "same_task_obstacle_and_audience_rules" in cluster["repeat_validation"]


def test_two_topic_communities_are_visible_but_do_not_claim_verified_demand(tmp_path):
    store = Store(tmp_path)
    store.upsert(
        [
            post("stackexchange", "freelancing"),
            post(
                "stackexchange",
                "workplace",
                id="2",
                author="second",
                body="We manually count inventory in our shop each week.",
            ),
        ]
    )
    result = run_analysis(Settings(sources=["stackexchange"]), store)
    cluster = result["clusters"][0]
    assert cluster["repeated_need"] is True
    assert cluster["corroboration"] == "cross_community_problem"
    assert cluster["independent_community_count"] == 2
    assert "same_task_obstacle_and_audience_rules" in cluster["repeat_validation"]
    assert all(not lead["current_need_verified"] for lead in result["leads"])


@pytest.mark.parametrize(
    "pitch",
    [
        "We need a simple invoice service. Please support this proposal by liking the issue.",
        "I need a budgeting app. Please upvote my project.",
    ],
)
def test_campaigning_for_a_proposal_is_not_customer_demand(pitch):
    assert score_post(post(body=pitch))["lead_quality"] == "noise"


def test_ordinary_customer_need_can_mention_a_proposal_without_being_a_campaign():
    result = score_post(
        post(
            body="Our shop manually enters supplier invoices every month. A previous proposal did not solve this."
        )
    )
    assert result["lead_quality"] == "opportunity"


def test_generic_budget_or_mental_framework_does_not_create_household_demand():
    p = post(
        title="Model subscription",
        body="I have a budget of twenty dollars for coding models. I am looking for a mental model/framework to estimate token costs.",
    )
    result = score_post(p)
    assert "everyday_life" not in result["audiences"]
    assert result["lead_quality"] != "opportunity"


def test_firsthand_recurring_process_request_does_not_require_software_words():
    p = post(
        "stackexchange",
        "money",
        title="Household budget",
        body="Our household expenses change every month. I'm interested in a method that is simple enough to maintain each month without constantly adjusting categories.",
    )
    result = score_post(p)
    assert result["lead_quality"] == "opportunity"
    assert result["primary_audience"] == "everyday_life"
    routine = post(
        "stackexchange",
        "money",
        title="Household budget",
        body="How should an annual payment be recorded in a monthly budget?",
    )
    assert score_post(routine)["lead_quality"] != "opportunity"


def test_hiring_thread_comment_cannot_become_a_product_lead():
    result = score_post(
        post(
            body="I am looking for tools and software projects to work on for clients.",
            metadata={"parent_title": "Ask HN: Who wants to be hired? (October 2026)"},
        )
    )
    assert result["lead_quality"] == "noise"


def test_source_status_explains_choices_and_new_default_excludes_vendor_forums(
    monkeypatch,
):
    monkeypatch.delenv("METIS_SOURCES", raising=False)
    settings = Settings()
    result = source_status(settings)
    sources = {row["source"]: row for row in result["sources"]}
    assert sources["discourse"]["status"] == "disabled"
    assert sources["discourse"]["evidence_role"] == "primary"
    assert sources["stackexchange"]["evidence_role"] == "primary"
    assert all(
        row["selection_reason"] and row["coverage_limit"] for row in sources.values()
    )
    assert {"money", "workplace"} <= {
        site for site, _ in settings.stackexchange_searches()
    }
    assert "softwarerecs" not in {site for site, _ in settings.stackexchange_searches()}


def test_coverage_reports_empty_selected_communities_and_support_separately(tmp_path):
    store = Store(tmp_path)
    store.upsert([post(), post("discourse", "community.shopify.com")])
    settings = Settings(sources=["hackernews", "discourse", "stackexchange"])
    result = run_analysis(settings, store)
    coverage = {(r["source"], r["community"]): r for r in result["community_coverage"]}
    assert coverage[("stackexchange", "money")]["analyzed_records"] == 0
    assert coverage[("hackernews", "hackernews")]["primary_candidates"] == 1
    assert coverage[("discourse", "community.shopify.com")]["supporting_records"] == 0
    assert coverage[("discourse", "community.shopify.com")]["primary_candidates"] == 1


@pytest.mark.parametrize(
    "status,policy",
    [
        (200, "User-agent: *\nDisallow: /search\n"),
        (200, "<html>Access page</html>"),
        (302, ""),
    ],
)
def test_deferred_forum_never_searches_when_policy_denies_or_cannot_be_read(
    status, policy
):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert request.url.path == "/robots.txt"
        return httpx.Response(status, text=policy)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = DiscourseCollector(
            Settings(audiences=["small_business"]), client
        ).collect()
    assert result.status == "error"
    assert result.posts == []
    assert calls == ["/robots.txt"]
