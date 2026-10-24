"""Evaluate current rules against explicitly labelled local evidence."""

from models import REVIEW_LABELS, evidence_fingerprint
from processors.cleaner import clean_posts
from processors.signals import score_post


def evaluate_reviews(store):
    matrix = {actual: dict.fromkeys(REVIEW_LABELS, 0) for actual in REVIEW_LABELS}
    stale = []
    rows = store.reviewed_posts()
    for row in rows:
        if evidence_fingerprint(row["post"]) != row["fingerprint"]:
            stale.append(row["post"]["id"])
            continue
        cleaned = clean_posts([row["post"]])
        predicted = score_post(cleaned[0])["lead_quality"] if cleaned else "noise"
        matrix[row["label"]][predicted] += 1
    true_positive = matrix["opportunity"]["opportunity"]
    predicted_positive = sum(row["opportunity"] for row in matrix.values())
    actual_positive = sum(matrix["opportunity"].values())
    return {
        "status": "success",
        "scoring_method": "intent_heuristic_v6",
        "reviewed": len(rows),
        "evaluated": len(rows) - len(stale),
        "stale_review_ids": stale,
        "opportunity_precision": round(true_positive / predicted_positive, 4)
        if predicted_positive
        else None,
        "opportunity_recall": round(true_positive / actual_positive, 4)
        if actual_positive
        else None,
        "confusion_matrix": matrix,
        "scope": "Explicit local review labels only; this is not an estimate of market-wide accuracy.",
    }
