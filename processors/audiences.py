"""Topic labels from explicit text and community context, not personal profiles."""

import re

AUDIENCE_TERMS = {
    "small_business": (
        "shop",
        "store",
        "shopify",
        "merchant",
        "inventory",
        "stock",
        "supplier",
        "appointments",
        "appointment",
        "invoice",
        "invoices",
        "invoicing",
        "bookkeeping",
        "freelancer",
        "freelancing",
        "clients",
        "client",
        "salon",
        "restaurant",
        "retail",
        "staff",
        "customer orders",
        "sales",
        "small business",
        "shipping",
        "fulfillment",
        "fulfilment",
    ),
    "everyday_life": (
        "family",
        "household",
        "home",
        "parents",
        "parent",
        "children",
        "childcare",
        "school",
        "caregiver",
        "caregiving",
        "meal",
        "meals",
        "groceries",
        "travel",
        "holiday",
        "rental",
        "landlord",
        "tenant",
        "garden",
        "gardening",
        "commute",
        "chores",
        "cleaning",
        "bills",
        "school payments",
        "budgeting",
        "rent",
        "cooking",
        "laundry",
        "shopping",
        "recipes",
        "school runs",
    ),
    "developer_tools": (
        "developer",
        "developers",
        "deployment",
        "deploy",
        "api",
        "database",
        "docker",
        "kubernetes",
        "ci/cd",
        "authentication",
        "sso",
        "linux",
        "cli",
        "repository",
        "repositories",
        "config",
        "sdk",
        "programming",
        "source code",
        "vs code",
        "codebase",
        "codebases",
        "code completion",
        "coding assistant",
        "coding assistants",
        "software development",
        "development workflow",
    ),
}
COMMUNITIES = {
    "small_business": {"freelancing", "community.shopify.com"},
    "everyday_life": {"parenting", "cooking", "diy", "travel", "community.monzo.com"},
    "developer_tools": {"stackoverflow", "serverfault"},
}


def classify_audiences(post, text):
    text = text.lower()
    signals = {}
    for audience, words in AUDIENCE_TERMS.items():
        found = [
            word
            for word in words
            if re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text)
        ]
        if audience == "small_business" and re.search(
            r"\b(?:mobile|desktop|http|web|api|python|react native|network|webrtc) clients?\b",
            text,
        ):
            found = [word for word in found if word not in {"client", "clients"}]
        if post.get("community") in COMMUNITIES[audience]:
            found.append("community:" + post["community"])
        if found:
            signals[audience] = found
    return signals


def primary_audience(post, signals):
    """Prefer the subject of the title and its community over incidental words."""
    title = post.get("title", "").lower()
    weights = {
        audience: sum(
            3
            if term.startswith("community:")
            else 1
            + 2 * bool(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", title))
            for term in terms
        )
        for audience, terms in signals.items()
    }
    return max(weights, key=weights.get) if weights else None
