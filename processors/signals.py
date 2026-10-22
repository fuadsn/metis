"""Explainable lead signals. Scores prioritize review, not buyer probabilities."""

import re
from datetime import datetime, timezone

from config import PAIN_KEYWORDS

BUYING = ("would pay", "will pay", "willing to pay", "budget for")
SEARCH = (
    "looking for",
    "alternative to",
    "alternatives to",
    "can someone recommend",
    "any recommendations",
)
UNMET = (
    "wish there was",
    "can't find",
    "cannot find",
    "no good",
    "missing feature",
    "doesn't support",
    "does not support",
)
BURDEN = (
    "manual work",
    "manually",
    "repetitive",
    "copy and paste",
    "copy-paste",
    "time consuming",
    "time-consuming",
)
QUESTIONS = (
    "how do i",
    "how can i",
    "does anyone know",
    "help me",
    "error",
    "exception",
    "traceback",
    "not working",
)
DOMAIN = (
    "developer",
    "startup",
    "saas",
    "workflow",
    "deployment",
    "deploy",
    "api",
    "database",
    "invoice",
    "billing",
    "business",
    "customer",
    "team",
    "docker",
    "kubernetes",
    "ci/cd",
    "authentication",
    "sso",
    "integration",
    "automation",
    "software",
    "tool",
    "tools",
    "reporting",
    "dashboard",
    "onboarding",
    "customers",
    "invoices",
    "deployments",
    "authentication",
    "payments",
    "subscription",
    "hosting",
    "documentation",
    "monitoring",
)


def matching_text(text):
    return text.lower().replace("’", "'").replace("‘", "'")


def matches(phrase, text):
    return (
        re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", matching_text(text))
        is not None
    )


def affirmed(phrase, text):
    text = matching_text(text)
    for match in re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text):
        prefix = re.split(r"[.!?;\n]", text[: match.start()])[-1][-60:]
        if not re.search(
            r"(?:\bnot|\bnever|\bno|n't|\bwho|\bwhy)\s+(?:\w+\s+){0,3}$", prefix
        ):
            return True
    return False


def signal_text(text):
    # Preserve original bodies; quoted examples and code are not the author's intent.
    text = re.sub(r"```.*?(?:```|$)|~~~.*?(?:~~~|$)|<!--.*?-->", "", text, flags=re.S)
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.lstrip().startswith(">")
        and not re.search(
            r"is your feature request related to|describe the solution you|describe alternatives you",
            line,
            re.I,
        )
    )


def score_post(post, now=None):
    text = signal_text(
        post.get("text") or "\n".join((post.get("title", ""), post.get("body", "")))
    )
    keywords = [phrase for phrase in PAIN_KEYWORDS if affirmed(phrase, text)]
    buying = [phrase for phrase in BUYING if affirmed(phrase, text)]
    search = [phrase for phrase in SEARCH if affirmed(phrase, text)]
    normalized = matching_text(text)
    if "looking for" in search and not re.search(
        r"\blooking for\s+(?!(?:(?:a|an|some|any|beta)\s+){0,2}(?:owners|testers|contributors|feedback|people|someone|developers|engineers|users|volunteers)\b)[^.!?\n]{0,80}\b(?:tools?|software|services?|solutions?|platforms?|alternatives?|apps?|libraries|library|frameworks?|providers?|systems?|products?|automation|integrations?|hosting)\b",
        normalized,
    ):
        search.remove("looking for")
    tool_question = re.search(
        r"\b(?:which|what)\b[^.!?\n]{0,60}\b(?:tool|software|service|platform|library|framework)\b[^.!?\n]{0,60}\b(?:use|recommend)\b",
        normalized,
    )
    if tool_question:
        search.append(tool_question.group())
    unmet = [phrase for phrase in UNMET if affirmed(phrase, text)]
    burden = [phrase for phrase in BURDEN if affirmed(phrase, text)]
    time_cost = re.search(
        r"\b(?:spend|waste|lose|takes|costs)\b[^.!?\n]{0,60}\b(?:hours?|days?)\b",
        normalized,
    )
    if time_cost:
        burden.append(time_cost.group())
    questions = [phrase for phrase in QUESTIONS if matches(phrase, text)]
    labels = {
        str(label).lower() for label in post.get("metadata", {}).get("labels", [])
    }
    feature = bool(
        labels & {"enhancement", "feature request", "feature-request"}
    ) or matches("feature request", text)
    workaround = affirmed("workaround", text)
    candidate = bool(
        keywords or buying or search or unmet or burden or questions or feature
    )
    promotion = bool(
        re.search(
            r"^show hn:|\b(?:i|we) (?:built|launched|created)\b|\b(?:try|check out) my\b",
            matching_text(text),
        )
    )
    hiring = bool(
        re.search(
            r"\b(?:looking for (?:a )?(?:job|work|employment|internship)|we(?:'re| are) hiring)\b",
            matching_text(text),
        )
    )
    bot = (
        post.get("author", "").lower().endswith("[bot]")
        or post.get("metadata", {}).get("author_type") == "Bot"
    )
    solicitation = bool(
        re.search(
            r"community wishlist|feature request template|feature ideas\s*(?:&|and)\s*requests",
            post.get("title", ""),
            re.I,
        )
    )
    components = {"explicit_signal": 10 if candidate else 0}
    for key, value, points in (
        ("willingness_to_pay", buying, 35),
        ("tool_or_alternative_search", search, 20),
        ("unmet_capability", unmet, 20),
        ("recurring_or_manual_work", burden, 20),
        ("feature_request", feature, 12),
        ("workaround", workaround, 8),
        ("explicit_pain", keywords, 5),
    ):
        if value:
            components[key] = points
    context = text + "\n" + post.get("metadata", {}).get("parent_title", "")
    relevant = any(matches(word, context) for word in DOMAIN)
    if candidate and relevant:
        components["startup_or_developer_context"] = 10
    created = post.get("created_utc")
    if candidate and created:
        age = ((now or datetime.now(timezone.utc).timestamp()) - created) / 86400
        if 0 <= age <= 30:
            components["recency"] = 5 if age <= 7 else 2
    strong = bool(buying or search or unmet or burden or feature)
    score = min(100, sum(components.values()))
    quality = (
        "opportunity"
        if strong and relevant and score >= 40
        else "support"
        if candidate
        else "noise"
    )
    if candidate and not relevant:
        components["unclear_market_context_penalty"] = -max(0, score - 25)
        score = min(score, 25)
    if questions and not strong:
        components["support_only_penalty"] = -max(0, score - 25)
        score = min(score, 25)
    if bot or hiring or solicitation or (promotion and not buying):
        components["promotion_hiring_bot_or_template_penalty"] = -sum(
            components.values()
        )
        score, quality = 0, "noise"
    if not candidate:
        score = 0
    phrases = list(
        dict.fromkeys(buying + search + unmet + burden + keywords + questions)
    )
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    excerpt = next(
        (
            sentence
            for phrase in phrases
            for sentence in sentences
            if affirmed(phrase, sentence)
        ),
        text,
    )
    return {
        "lead_quality": quality,
        "lead_type": "noise"
        if quality == "noise"
        else "buying_signal"
        if buying
        else "alternative_search"
        if search
        else "workflow_pain"
        if quality == "opportunity"
        else "support_question"
        if quality == "support"
        else "noise",
        "priority_score": score,
        "score_breakdown": components,
        "matched_keywords": list(
            dict.fromkeys(keywords + buying + search + unmet + burden)
        ),
        "evidence_excerpt": excerpt[:600],
        "scoring_method": "intent_heuristic_v2",
    }


def promising_discussion(post):
    """Ask HN can contain useful replies even without intent in the root question."""
    return (
        post.get("source") == "hackernews"
        and post.get("title", "").lower().startswith("ask hn:")
        and any(matches(word, signal_text(post.get("text", ""))) for word in DOMAIN)
    )
