"""Illustrative behavioral cases; these do not establish real-market precision."""

from datetime import datetime, timezone

import pytest

from cli import latest, main
from config import Settings
from generators.idea_generator import format_ideas_for_agent
from models import normalize_post
from pipeline import run_analysis
from processors.cleaner import clean_posts, rank_candidates
from processors.clusterer import cluster_pain_points
from storage import Store


def record(body, id="1", source="hackernews", **overrides):
    return normalize_post(
        {
            "id": id,
            "source": source,
            "author": "author-" + id,
            "body": body,
            "created_utc": datetime.now(timezone.utc).timestamp(),
            "url": f"https://example.org/{source}/{id}",
            **overrides,
        }
    )


def ranked(*posts):
    return rank_candidates(clean_posts(list(posts)))


def analyze(tmp_path, *posts):
    store = Store(tmp_path)
    store.upsert(posts)
    return run_analysis(
        Settings(
            sources=sorted({p["source"] for p in posts}),
            audiences=["small_business", "everyday_life", "developer_tools"],
        ),
        store,
    )


def test_recurring_business_work_across_platforms_produces_one_grounded_idea(tmp_path):
    first = record("Our shop manually reconciles inventory counts every Friday.")
    second = record(
        "I manually count stock in my store each week and enter the totals.",
        "2",
        "discourse",
        community="community.shopify.com",
    )
    result = analyze(tmp_path, first, second)
    assert len(result["leads"]) == 2
    assert len(result["ideas"]) == 1
    idea = result["ideas"][0]
    assert idea["independent_platform_count"] == 2
    assert idea["commercial"]["basis"] == "inferred_business_labor"
    assert idea["commercial"]["payment_verified"] is False
    assert (
        idea["desired_outcome"]
        == "Keep recorded inventory consistent with a physical count"
    )
    assert idea["novelty_score"] is idea["market_difficulty"] is None
    assert set(idea["evidence_urls"]) == {first["url"], second["url"]}
    assert "payment unverified" in format_ideas_for_agent(result["ideas"])


def test_single_buyer_is_a_lead_but_not_a_recurring_idea(tmp_path):
    result = analyze(
        tmp_path,
        record(
            "Our shop manually counts inventory every week. I would pay for a tool to do this."
        ),
    )
    assert len(result["leads"]) == 1
    assert result["ideas"] == []
    assert (
        "needs_two_independent_matching_reports"
        in result["clusters"][0]["commercial"]["reasons"]
    )


def test_recurrence_without_economic_evidence_stays_available_for_research(
    tmp_path, monkeypatch, capsys
):
    result = analyze(
        tmp_path,
        record(
            "I am looking for a method to maintain my monthly household budget without constantly adjusting categories."
        ),
        record(
            "Our family expenses vary each month. I need a budgeting tool to update the monthly spending plan.",
            "2",
            "stackexchange",
            community="money",
        ),
    )
    assert len(result["problems"]) == 2
    assert result["clusters"][0]["repeated_need"]
    assert result["leads"] == result["ideas"] == []
    assert all(
        p["commercial"]["reasons"] == ["no_economic_evidence"]
        for p in result["problems"]
    )
    store = Store(tmp_path)
    monkeypatch.setattr("cli.Store", lambda: store)
    assert main(["problems", "--audience", "everyday_life"]) == 0
    assert '"no_economic_evidence"' in capsys.readouterr().out
    assert latest("ideas", store=store)["commercial_filter"]["enabled"]


def test_one_stated_payment_signal_and_an_independent_matching_problem_pass(tmp_path):
    result = analyze(
        tmp_path,
        record(
            "Our family manually updates the monthly budget each week. I would pay for an app to maintain the plan."
        ),
        record(
            "I need a budgeting tool for my family. I adjust the monthly categories manually every week.",
            "2",
            "stackexchange",
            community="money",
        ),
    )
    assert len(result["leads"]) == 1
    assert len(result["ideas"]) == 1
    assert result["ideas"][0]["commercial"]["basis"] == "stated_economic_evidence"


@pytest.mark.parametrize(
    "body",
    [
        "My budget for a car is thirty thousand dollars. How do I choose between cash and retirement savings?",
        "We are looking for a salary solution for our co-founder salary dispute. I have a family and household expenses.",
        "My family spends hours using an assistant for meal planning every day and everything works well.",
        "I manually import bank transactions every month with scripts. This is exactly what I wanted. Everything I need is here.",
        "I need a tool for my monthly household budget, but I am not willing to pay for any software.",
        "I would pay $0 for a budgeting app for my family.",
        "I would pay for nothing. We are not willing to pay for any household service.",
        "I keep client invoices in spreadsheets. How can I ask my client for more work without sounding pushy?",
        "I need a formula to calculate compound interest for my savings without Excel.",
        "> Our shop would pay for inventory software.\nThanks for the quote about counting stock.",
    ],
)
def test_advice_satisfied_workflows_and_nonbuyer_signals_do_not_pass(body):
    point = ranked(record(body))[0]
    assert point["commercial"]["eligible"] is False
    assert point["commercial"]["evidence"] == []
    assert point["commercial"]["reasons"]


@pytest.mark.parametrize(
    "body,kind",
    [
        (
            "Our shop manually counts stock every week. We currently pay $80 per month for inventory software but still have to do the count manually.",
            "existing_solution_spend",
        ),
        (
            "I spend three hours every week manually importing bank transactions for my family budget. The file has incorrect columns.",
            "quantified_recurring_time_cost",
        ),
        (
            "I would pay for a service to cover childcare during my changing shifts.",
            "stated_payment_interest",
        ),
    ],
)
def test_economic_signals_include_exact_supporting_text(body, kind):
    point = ranked(record(body))[0]
    assert point["commercial"]["eligible"]
    evidence = next(e for e in point["commercial"]["evidence"] if e["kind"] == kind)
    assert evidence["excerpt"] in body
    assert evidence["strength"] == "stated"


def test_same_broad_budget_topic_cannot_merge_salary_and_household_planning():
    groups = cluster_pain_points(
        ranked(
            record(
                "We are looking for a salary solution for our co-founder salary dispute. I have family expenses and a budget."
            ),
            record(
                "I need a budgeting tool to maintain my family's monthly spending plan without constantly adjusting categories.",
                "2",
            ),
        )
    )
    assert len(groups) == 2
    assert all(not g["repeated_need"] for g in groups)


def test_same_subject_different_task_or_obstacle_stays_separate():
    groups = cluster_pain_points(
        ranked(
            record("Our shop manually enters invoices every week."),
            record("Our shop is chasing overdue invoices every week.", "2"),
            record("Our shop manually counts inventory every week.", "3"),
            record(
                "Our shop manually counts inventory every Friday but committed stock makes the totals wrong.",
                "4",
            ),
        )
    )
    assert len(groups) == 4
    assert all(not g["repeated_need"] for g in groups)


def test_ambiguous_multitask_post_does_not_bridge_two_groups():
    points = ranked(
        record("Our shop manually counts inventory each week."),
        record("Our shop enters invoices manually every month.", "2"),
        record(
            "Our shop manually counts inventory and enters invoices every week.", "3"
        ),
    )
    assert (
        next(p for p in points if p["post_id"].endswith(":3"))["problem_signature"][
            "status"
        ]
        == "ambiguous_tasks"
    )
    assert len(cluster_pain_points(points)) == 3


def test_bank_import_paraphrases_match_but_budget_plan_adjustments_do_not():
    groups = cluster_pain_points(
        ranked(
            record(
                "I manually import bank transactions each month for my family. The CSV has incorrect columns."
            ),
            record(
                "My family needs a bank import tool. I have to fix different formats manually every month.",
                "2",
                "stackexchange",
                community="money",
            ),
            record(
                "I need a budgeting app to maintain my family's monthly spending plan without constantly adjusting categories.",
                "3",
            ),
        )
    )
    assert len(groups) == 2
    matched = next(g for g in groups if g["repeated_need"])
    assert matched["problem_signature"]["task"] == "bank_transaction_import"
    assert matched["problem_signature"]["obstacle"] == "data_format"


def test_duplicate_platform_and_github_cannot_boost_corroboration(tmp_path):
    text = "Our shop manually reconciles inventory counts every Friday before opening the doors to customers for the weekend."
    first = record(text)
    second = record(
        "I manually count stock in my store each week and enter the totals.", "2"
    )
    duplicate = record(text + " This is frustrating.", "3", "discourse")
    github = record("Our shop manually counts inventory every Monday.", "4", "github")
    baseline = analyze(tmp_path / "baseline", first, second)
    result = analyze(tmp_path / "copies", first, second, duplicate, github)
    a, b = baseline["clusters"][0], result["clusters"][0]
    assert b["repeat_evidence_count"] == 2
    assert b["independent_platform_count"] == 1
    assert not b["cross_source"]
    assert b["priority_score"] == a["priority_score"]
    assert b["excluded_from_repeat"][0]["reason"] == "copied_or_near_duplicate_text"
    assert b["commercial"]["evidence"] == a["commercial"]["evidence"]


def test_unknown_tasks_do_not_group_only_because_they_share_pain_words():
    groups = cluster_pain_points(
        ranked(
            record("Our shop does repetitive paperwork every week. I need a tool."),
            record("Our store needs a tool for manual paperwork each month.", "2"),
        )
    )
    assert len(groups) == 2
    assert all(not g["commercial"]["eligible"] for g in groups)


def test_solved_workflow_with_explicit_residual_pain_is_not_discarded():
    point = ranked(
        record(
            "Our shop uses an app that solved the invoice problem, but we still have to manually count inventory every week."
        )
    )[0]
    assert point["workflow_state"] != "resolved"
    assert point["commercial"]["eligible"]


def test_conditional_subscription_payment_is_kept_without_claiming_a_buyer():
    point = ranked(
        record(
            "My family cannot afford separate newspaper subscriptions. I could pay a subscription divided among the news portals I visit."
        )
    )[0]
    assert point["commercial"]["eligible"]
    assert point["willingness_to_pay"] == "stated_in_text_unverified"
    assert not point["commercial"]["payment_verified"]


def test_unrelated_purchase_and_zero_price_are_not_economic_support_for_a_task():
    for ending in [
        "I would pay for a garden cleaning service.",
        "We currently pay $0 for inventory software.",
    ]:
        point = ranked(
            record("Our shop manually counts inventory every week. " + ending)
        )[0]
        assert point["commercial"]["status"] == "inferred_labor_cost"
        assert all(e["strength"] == "inferred" for e in point["commercial"]["evidence"])


def test_obstacle_excerpt_prefers_the_manual_workaround_to_neutral_context():
    body = "Our shop records available and committed inventory. Staff must manually check every SKU for committed stock before entering the counts."
    point = ranked(record(body))[0]
    assert (
        point["problem_signature"]["obstacle_excerpt"]
        == "Staff must manually check every SKU for committed stock before entering the counts."
    )
