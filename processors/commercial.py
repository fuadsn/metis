"""Evidence-based commercial screening, not revenue or purchase predictions."""

import re

from processors.problems import TASKS
from processors.signals import (
    PERSON,
    PRODUCT,
    affirmed,
    matching_text,
    purchase_sentences,
    signal_text,
)

NUMBER = r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|half an?)"
ACTION = r"\b(?:manual\w*|repetitiv\w*|repeat\w*|reconcil\w*|count\w*|enter\w*|review\w*|chas\w*|copy\w*|clean\w*|import\w*|schedul\w*|coordinat\w*|deploy\w*|wast\w*)\b"


def linked_to_task(sentence, signature):
    """Do not borrow a payment or cost statement about an unrelated service."""
    if not signature["task"]:
        return True  # Unmatched tasks can be single leads, never repeated ideas.
    s = matching_text(sentence)
    return bool(
        re.search(TASKS[signature["task"]][2][0], s)
        or re.search(r"\b(?:this|that|it|these)\b", s)
        or re.search(
            r"\bfor (?:a |an |the )?(?:tool|app|service|software|solution)\b", s
        )
    )


def positive_spend(text):
    amount = re.search(
        r"[$£€]\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:dollars?|pounds?|euros?)", text
    )
    return bool(amount and float(amount.group(1) or amount.group(2)) > 0)


def commercial_assessment(point):
    text = signal_text("\n".join((point.get("title", ""), point.get("body", ""))))
    normalized = matching_text(text)
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    signature = point["problem_signature"]
    reasons, evidence = [], []
    if point.get("workflow_state") == "resolved":
        reasons.append("workflow_already_resolved")
    if point.get("lead_quality") != "opportunity":
        reasons.append("insufficient_unresolved_problem_signal")
    if point.get("evidence_role") != "primary":
        reasons.append("supporting_source_only")
    if re.search(
        r"\b(?:how (?:do|can|should) i (?:ask|tell|convince)|salary dispute|co-founder salary)\b",
        normalized,
    ):
        reasons.append("interpersonal_advice_request")
    if re.search(
        r"\b(?:not willing to pay|won't pay|will not pay|only (?:want|need|use) (?:a )?free|free (?:tools?|software|apps?|solutions?) only)\b",
        normalized,
    ):
        reasons.append("explicit_unwillingness_to_pay")

    def add(kind, strength, excerpt):
        evidence.append(
            {"kind": kind, "strength": strength, "excerpt": excerpt.strip()[:600]}
        )

    if not reasons:
        for sentence in purchase_sentences(text):
            if linked_to_task(sentence, signature):
                add("stated_payment_interest", "stated", sentence)
        for sentence in sentences:
            s = matching_text(sentence)
            # Spending must concern a solution in the same sentence; an ordinary
            # household budget, salary or stock value is not a software budget.
            spend = re.search(
                r"\b(?:i|we) (?:already |currently )?(?:pay|spend)\b[^.!?\n]{0,50}(?:[$£€]\s*\d+(?:\.\d+)?|\d+\s*(?:dollars?|pounds?|euros?))\b",
                s,
            )
            if (
                spend
                and re.search(PRODUCT, s)
                and affirmed(spend.group(), sentence)
                and signature["matchable"]
                and linked_to_task(sentence, signature)
                and positive_spend(spend.group())
            ):
                add("existing_solution_spend", "stated", sentence)
            time = re.search(
                r"\b(?:spend\w*|wast\w*|takes?|costs?|los[et]\w*)\b[^.!?\n]{0,35}\b"
                + NUMBER
                + r"\s*(?:hours?|minutes?)\b",
                s,
            )
            if (
                time
                and not re.search(r"\b0(?:\.0+)?\s*(?:hours?|minutes?)\b", time.group())
                and re.search(PERSON, s)
                and re.search(ACTION, s)
                and affirmed(time.group(), sentence)
                and point.get("recurring_work_mentioned")
                and signature["matchable"]
                and linked_to_task(sentence, signature)
            ):
                add("quantified_recurring_time_cost", "stated", sentence)
        # Labor cost is an inference. Two independent accounts with this basis
        # are required at idea level unless a stronger economic signal exists.
        if (
            signature["matchable"]
            and point.get("primary_audience") in {"small_business", "developer_tools"}
            and point.get("firsthand_context")
            and point.get("recurring_work_mentioned")
            and re.search(
                r"\b(?:our (?:shop|store|team|business|staff)|my (?:shop|store|business|clients?)|i run|staff|employees?|client invoices?|our billing|our deployment)\b",
                normalized,
            )
            and any(affirmed(m.group(), text) for m in re.finditer(ACTION, normalized))
        ):
            add("recurring_business_labor", "inferred", signature["obstacle_excerpt"])
    if not reasons and not evidence:
        reasons.append("no_economic_evidence")
    return {
        "eligible": bool(evidence) and not reasons,
        "status": "economic_signal"
        if any(e["strength"] == "stated" for e in evidence)
        else "inferred_labor_cost"
        if evidence
        else "research_only",
        "evidence": evidence,
        "reasons": reasons,
        "payment_verified": False,
        "method": "commercial_evidence_rules_v1",
    }


def cluster_commercial_assessment(independent_points, repeated):
    evidence = [
        {**e, "post_id": p["post_id"], "url": p.get("url", "")}
        for p in independent_points
        for e in p.get("commercial", {}).get("evidence", [])
        if p["commercial"]["eligible"]
    ]
    strong = any(e["strength"] == "stated" for e in evidence)
    inferred_accounts = len(
        {e["post_id"] for e in evidence if e["strength"] == "inferred"}
    )
    reasons = []
    if not repeated:
        reasons.append("needs_two_independent_matching_reports")
    if not strong and inferred_accounts < 2:
        reasons.append("needs_stated_economic_evidence_or_two_business_labor_reports")
    return {
        "eligible": not reasons,
        "status": "commercial_hypothesis" if not reasons else "research_only",
        "basis": "stated_economic_evidence"
        if strong
        else "inferred_business_labor"
        if inferred_accounts >= 2
        else "insufficient",
        "evidence": evidence,
        "reasons": reasons,
        "payment_verified": False,
        "method": "recurrence_and_commercial_evidence_v1",
    }
