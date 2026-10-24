"""Illustrative regression cases, not a measured production-quality benchmark."""

import json
from datetime import datetime, timezone

import pytest

from config import Settings
from models import normalize_post
from pipeline import run_analysis
from processors.cleaner import clean_posts, rank_candidates
from processors.clusterer import cluster_pain_points
from processors.evaluation import evaluate_reviews
from processors.signals import score_post
from storage import Store

NOW = datetime.now(timezone.utc).timestamp()


def post(body, **overrides):
    return normalize_post(
        {
            "id": "1",
            "source": "github",
            "body": body,
            "author": "dev",
            "created_utc": NOW,
            **overrides,
        }
    )


@pytest.mark.parametrize(
    "body,quality",
    [
        ("We would pay for a deployment tool to eliminate manual work.", "opportunity"),
        (
            "Our team is looking for an alternative to our billing software.",
            "opportunity",
        ),
        (
            "I manually copy invoices every week into our billing software.",
            "opportunity",
        ),
        ("Our team has a budget for a developer onboarding tool.", "opportunity"),
        ("How do I fix this Docker error? It happens on startup.", "support"),
        ("We are not willing to pay for deployment software.", "noise"),
        ("Who would pay for this developer tool?", "noise"),
        ("I am not looking for an alternative to our billing software.", "noise"),
        ("We have no budget for a developer tool.", "noise"),
        ("I built a deployment tool. Looking for feedback from developers.", "noise"),
        ("I am looking for a job as a developer.", "noise"),
        ("A beautiful photo of a distant galaxy has been published.", "noise"),
        (
            "Example code:\n```\nI would pay for a developer tool\n```\nThis is a string literal.",
            "noise",
        ),
        (
            "> I would pay for a deployment tool\nThanks for sharing this interesting quote.",
            "noise",
        ),
        (
            "Is your feature request related to a problem? Please describe.\nNo response.",
            "noise",
        ),
        ("Looking for a gardener to trim my hedges every week.", "support"),
    ],
)
def test_illustrative_quality_cases(body, quality):
    result = score_post(post(body))
    assert result["lead_quality"] == quality
    assert result["priority_score"] == max(
        0, min(100, sum(result["score_breakdown"].values()))
    )


def test_ranking_prefers_explicit_demand_over_popular_support_and_preserves_excerpt():
    buyer = post(
        "Context about our team. We would pay for a deployment workaround.",
        id="buyer",
        score=0,
    )
    support = post("How do I fix this Docker error?", id="support", score=10000)
    ranked = rank_candidates(clean_posts([support, buyer]))
    assert ranked[0]["post_id"] == "github:buyer"
    assert ranked[0]["evidence_excerpt"] in buyer["body"]
    assert ranked[0]["evidence_excerpt"] == "We would pay for a deployment workaround."


def test_comment_never_inherits_parent_buying_intent():
    comment = post(
        "Thank you for reporting this; we will investigate.",
        kind="comment",
        metadata={"parent_title": "I would pay for a deployment tool"},
    )
    assert score_post(comment)["lead_quality"] == "noise"


def test_synonyms_group_related_needs_across_sources_but_keep_different_needs_separate():
    records = [
        post(
            "We manually repeat deployment steps every week.",
            title="Deployment workflow",
            source="hackernews",
            id="1",
            author="founder",
        ),
        post(
            "Our CI/CD requires repetitive manual work for releases.",
            source="stackexchange",
            title="CI/CD workflow",
            id="2",
            author="dev",
        ),
        post(
            "Our deployment software is too expensive. Looking for an alternative to this tool.",
            source="hackernews",
            title="Deployment pricing",
            id="3",
            author="another",
        ),
    ]
    groups = cluster_pain_points(rank_candidates(clean_posts(records)))
    automation = next(g for g in groups if g["need"] == "automation")
    assert automation["topic"] == "deploy"
    assert automation["sources"] == ["hackernews", "stackexchange"]
    assert automation["repeated_need"] is True
    assert automation["repeat_evidence_count"] == 2
    assert len(groups) == 2


@pytest.mark.parametrize(
    "case", ["same_thread", "same_author", "copied_text", "unknown_authors"]
)
def test_replies_reposts_and_unknown_authors_do_not_inflate_repeat_evidence(case):
    first = post(
        "I manually repeat deployment steps every week.", id="1", source="hackernews"
    )
    second = post(
        "We need a tool to automate CI/CD manual work.",
        id="2",
        author="someone-else",
        source="hackernews",
    )
    if case == "same_thread":
        second.update(kind="comment", parent_id=first["id"])
    elif case == "same_author":
        second["author"] = first["author"]
    elif case == "copied_text":
        second["body"] = first["body"]
    else:
        first["author"] = second["author"] = ""
    group = cluster_pain_points(rank_candidates(clean_posts([first, second])))[0]
    assert group["repeated_need"] is False
    assert group["repeat_evidence_count"] <= 1


def test_analysis_exposes_review_candidates_but_only_opportunities_become_leads(
    tmp_path,
):
    store = Store(tmp_path)
    store.upsert(
        [
            post("We would pay for a deployment tool.", id="1"),
            post("How do I fix a Docker error?", id="2"),
            post("A photo of a distant galaxy has been published.", id="3"),
        ]
    )
    result = run_analysis(Settings(sources=["github"]), store)
    assert result["quality_counts"] == {"opportunity": 1, "support": 1, "noise": 1}
    assert result["leads_count"] == 0
    assert result["supporting_evidence_count"] == 2
    assert len(result["candidates"]) == 3
    assert all(
        p["lead_quality"] == "opportunity"
        for c in result["clusters"]
        for p in c["pain_points"]
    )


def test_reviews_evaluate_real_labels_and_exclude_changed_evidence(tmp_path):
    store = Store(tmp_path)
    assert evaluate_reviews(store)["opportunity_precision"] is None
    records = [
        post("I would pay for a deployment tool.", id="1"),
        post("How do I fix a Docker error?", id="2"),
    ]
    store.upsert(records)
    # Deliberately label the rule's positive as noise to verify false-positive metrics.
    store.save_review("github:1", "noise", "Example negative review")
    store.save_review("github:2", "support")
    result = evaluate_reviews(store)
    assert result["opportunity_precision"] == 0
    assert result["confusion_matrix"]["noise"]["opportunity"] == 1
    records[0]["body"] = "The original question has now been edited."
    store.upsert(records)
    result = evaluate_reviews(store)
    assert result["evaluated"] == 1
    assert result["stale_review_ids"] == ["github:1"]
    assert result["opportunity_precision"] is None
    with pytest.raises(ValueError, match="not found"):
        store.save_review("github:missing", "noise")


def test_review_and_evaluate_cli_are_local(monkeypatch, tmp_path, capsys):
    import cli

    store = Store(tmp_path)
    store.upsert([post("I would pay for a deployment tool.")])
    monkeypatch.setattr(cli, "Store", lambda: store)
    assert cli.main(["review", "github:1", "--label", "opportunity"]) == 0
    assert json.loads(capsys.readouterr().out)["label"] == "opportunity"
    assert cli.main(["evaluate"]) == 0
    assert json.loads(capsys.readouterr().out)["opportunity_recall"] == 1


@pytest.mark.parametrize(
    "body",
    [
        "The code hides the entity that a caller is looking for.",
        "I am looking for owners to test this developer integration.",
        "This developer software is usable every day.",
    ],
)
def test_live_run_false_positive_patterns_do_not_qualify(body):
    assert score_post(post(body))["lead_quality"] != "opportunity"


def test_tool_recommendation_question_and_quantified_time_cost_qualify():
    assert (
        score_post(post("Which security tool do you use for your software?"))[
            "lead_quality"
        ]
        == "opportunity"
    )
    assert (
        score_post(
            post("Our team spends time on this. Deployment takes three hours per week.")
        )["lead_quality"]
        == "opportunity"
    )


def test_old_analysis_requires_refresh_before_serving_new_ranked_leads(tmp_path):
    from cli import latest

    store = Store(tmp_path)
    store.save_result(
        {"schema_version": 2, "status": "success", "leads": []}, "latest_analysis.json"
    )
    result = latest("leads", store=store)
    assert result["status"] == "error"
    assert "analyze" in result["message"]


def test_feature_solicitation_is_not_itself_evidence_of_demand():
    invitation = post(
        "Have an idea, a missing feature, or a workflow that could be easier?",
        title="Feature ideas & requests — community wishlist",
        metadata={"labels": ["enhancement"]},
    )
    assert score_post(invitation)["lead_quality"] == "noise"
