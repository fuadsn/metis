"""Explainable lead signals. Scores prioritize review, not buyer probabilities."""

import re
from datetime import datetime, timezone

from config import PAIN_KEYWORDS
from processors.audiences import AUDIENCE_TERMS, classify_audiences, primary_audience
from processors.source_context import source_context

BUYING = ("would pay", "will pay", "could pay", "willing to pay", "budget for")
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
    "keeping track",
    "keep track",
    "chasing",
    "switching between",
    "re-enter",
    "struggling",
    "struggle",
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
    "linux",
    "cli",
    "repository",
    "repositories",
    "config",
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
) + tuple(term for words in AUDIENCE_TERMS.values() for term in words)


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
    text = re.sub(r"\[quote(?:=[^\]]*)?\].*?\[/quote\]", "", text, flags=re.S | re.I)
    text = re.sub(r"`[^`\n]+`|\b\w+\.\w+\([^\n)]*\)", "[code]", text)
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


PRODUCT = r"\b(?:tools?|software|services?|solutions?|platforms?|apps?|libraries|library|frameworks?|providers?|systems?|products?|automation|integrations?|hosting)\b"
PERSON = r"\b(?:i|i'm|i've|we|we're|we've|my|our|as a parent|as a caregiver|as a shop owner)\b"
PEOPLE_SEARCH = r"\blooking for\s+(?:(?:a|an|some|any|few|early|beta|full-stack|backend|frontend|dyslexic|senior|junior|software|java|data|ml)\s+){0,6}(?:engineers?|developers?|roles?|jobs?|employment|testers?|participants?)\b"


def own_statement(phrase, sentence):
    """Keep intent in the author's own clause, not elsewhere in a long post."""
    normalized = matching_text(sentence)
    position = normalized.find(phrase)
    return position >= 0 and bool(
        re.search(PERSON, normalized[max(0, position - 80) : position])
    )


def purchase_sentences(text):
    """Payment interest must concern a solution, not an unrelated life budget."""
    target = (
        PRODUCT
        + r"|\b(?:workaround|subscription|bookkeeping|childcare|caregiving|cleaning|gardening|newsletter|news bundle)\b"
    )
    result = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", signal_text(text)):
        normalized = matching_text(sentence)
        for phrase in BUYING:
            if not affirmed(phrase, sentence) or not own_statement(phrase, sentence):
                continue
            tail = normalized[normalized.find(phrase) + len(phrase) :]
            if re.search(
                r"^\s+(?:for\s+)?(?:(?:nothing|zero|less)\b|[$£€]?\s*0(?:\.0+)?(?:\s|/|$))",
                tail,
            ):
                continue
            if re.search(target, tail[:160]):
                result.append(sentence.strip())
                break
    return result


def workflow_state(text):
    """Keep solved workflows as useful research, not unresolved demand."""
    text = matching_text(signal_text(text))
    resolved = re.search(
        r"\b(?:solved (?:my|our|the|a lot of)|fixed (?:it|this|the (?:issue|problem))|"
        r"(?:it|this|that) (?:has |have )?(?:solved|fixed)|"
        r"(?:exactly|everything) (?:what )?i (?:wanted|need)|"
        r"works (?:perfectly|well) for (?:me|us)|"
        r"(?:my|our) problem (?:is|was|has been) (?:solved|fixed))\b",
        text,
    )
    residual = re.search(
        r"\b(?:still|but|however)\b[^.!?\n]{0,80}\b(?:have to|has to|cannot|can't|"
        r"waste|wastes|spend|spends|manually|fails|broken|unresolved|struggling)\b",
        text,
    )
    return "resolved" if resolved and not residual else "ongoing_or_unknown"


def score_post(post, now=None):
    text = signal_text(
        post.get("text") or "\n".join((post.get("title", ""), post.get("body", "")))
    )
    keywords = [phrase for phrase in PAIN_KEYWORDS if affirmed(phrase, text)]
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    paragraphs = re.split(r"\n\s*\n", text)
    payment_sentences = purchase_sentences(text)
    buying = [
        phrase
        for phrase in BUYING
        if any(matches(phrase, s) for s in payment_sentences)
    ]
    search = [phrase for phrase in SEARCH if affirmed(phrase, text)]
    normalized = matching_text(text)
    if "looking for" in search and not re.search(
        r"\blooking for\s+(?!(?:(?:a|an|some|any|beta)\s+){0,2}(?:owners|testers|contributors|feedback|people|someone|developers|engineers|users|volunteers)\b)[^.!?\n]{0,80}\b(?:tools?|software|services?|solutions?|platforms?|alternatives?|apps?|libraries|library|frameworks?|providers?|systems?|products?|automation|integrations?|hosting)\b",
        normalized,
    ):
        search.remove("looking for")
    if "looking for" in search and (
        re.search(PEOPLE_SEARCH, normalized)
        or re.search(
            r"\blooking for (?:some |any |a |an )?(?:materials?|books?|courses?|mental model|conceptual framework)\b|\b(?:was|were|instead of) looking for\b",
            normalized,
        )
    ):
        search.remove("looking for")
    search = [
        phrase
        for phrase in search
        if any(
            affirmed(phrase, sentence)
            and (
                (
                    phrase == "looking for"
                    and (
                        own_statement(phrase, sentence)
                        or matching_text(sentence).startswith("looking for")
                    )
                )
                or (
                    phrase in {"alternative to", "alternatives to"}
                    and re.search(PRODUCT, matching_text(sentence))
                    and re.search(
                        r"\b(?:looking for|seeking|need|want|recommend|suggest|any|are there|is there|what|which)\b",
                        matching_text(sentence)[: matching_text(sentence).find(phrase)],
                    )
                )
                or phrase in {"can someone recommend", "any recommendations"}
            )
            for sentence in sentences
        )
    ]
    tool_question = re.search(
        r"\b(?:which|what)\b[^.!?\n]{0,60}\b(?:tool|software|service|platform|library|framework)\b[^.!?\n]{0,60}\b(?:use|recommend)\b",
        normalized,
    )
    if tool_question:
        search.append(tool_question.group())
    direct_request = re.search(
        r"\b(?:i|we) (?:need|want|require|am seeking|are seeking)\s+(?!to\b)[^,.!?\n]{0,80}\b(?:tool|software|service|platform|library|framework|solution)\b",
        normalized,
    )
    if direct_request:
        search.append(direct_request.group())
    practical_request = re.search(
        r"\b(?:i|we) (?:need|want) (?:a|an|some|better) (?:better |easier |reliable )?(?:way|method|system|service) to (?:manage|organize|organise|track|schedule|coordinate|plan)\b[^.!?\n]{0,100}",
        normalized,
    )
    if practical_request:
        search.append(practical_request.group())
    unmet = [
        phrase
        for phrase in UNMET
        if any(
            affirmed(phrase, sentence)
            and own_statement(phrase, sentence)
            and (
                re.search(PRODUCT, matching_text(sentence))
                or any(matches(word, sentence) for word in DOMAIN)
            )
            for sentence in sentences
        )
    ]
    burden = [
        phrase
        for phrase in BURDEN
        if any(
            affirmed(phrase, sentence) and own_statement(phrase, sentence)
            for sentence in sentences
        )
        or any(
            affirmed(phrase, paragraph)
            and re.search(PERSON, matching_text(paragraph))
            and re.search(
                r"\b(?:challenge|problem|pattern|struggling|struggle|have to|has to|only way|workaround)\b",
                matching_text(paragraph),
            )
            for paragraph in paragraphs
        )
    ]
    time_cost = re.search(
        r"\b(?:spends?|wastes?|loses?|takes|costs)\b[^.!?\n]{0,60}\b(?:hours?|days?)\b",
        normalized,
    )
    if time_cost and not affirmed(time_cost.group(), text):
        time_cost = None
    if time_cost and not re.search(
        r"\b(?:coordinat\w*|reconcil\w*|count\w*|enter\w*|review\w*|chasing|"
        r"deploy\w*|copy\w*|clean\w*|import\w*|schedul\w*|wast\w*|struggl\w*)\b",
        normalized,
    ):
        time_cost = None
    if time_cost:
        burden.append(time_cost.group())
    firsthand = bool(re.search(PERSON, normalized))
    recurring = bool(
        re.search(
            r"\b(?:every|each|per|a) (?:day|week|weekday|month|quarter|release|deployment|monday|tuesday|wednesday|thursday|friday|saturday|sunday|sku|order|item|customer|time)\b|\b(?:daily|weekly|monthly|quarterly|repeatedly|repetitive)\b",
            normalized,
        )
    )
    process_request = re.search(
        r"\b(?:i(?:'m| am)|we(?:'re| are)) (?:particularly )?(?:looking for|interested in) (?:a|an|some) (?:simpler |better |reliable )?(?:way|method|system|approach|service)\b[^.!?\n]{0,150}\b(?:manage|organize|organise|track|schedule|coordinate|plan|maintain|budget)\b",
        normalized,
    )
    if process_request and recurring and affirmed(process_request.group(), text):
        search.append(process_request.group())
    # A manual action in a tutorial is not evidence of a recurring unmet need.
    if not firsthand or not (recurring or time_cost or search or unmet):
        burden = []
    if not firsthand:
        unmet = []
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
            r"^(?:show|launch) hn:|\b(?:i|we) (?:built|launched|created)\b|\b(?:try|check out) my\b|\blooking for (?:a few |some |early |beta )*(?:testers|users|feedback)\b|\bworking mvp\b",
            matching_text(text),
        )
        or re.search(
            r"\b(?:i(?:'m| am)|we(?:'re| are)) (?:building|launching)\b[^.!?\n]{0,80}\b(?:projects?|apps?|tools?|products?|services?|prototypes?)\b",
            normalized,
        )
    )
    hiring = (
        bool(
            re.search(
                r"\b(?:looking for (?:a )?(?:job|work|employment|internship)|we(?:'re| are) hiring)\b",
                matching_text(text),
            )
        )
        or bool(re.search(PEOPLE_SEARCH, normalized))
        or bool(
            re.search(
                r"^ask hn: (?:who is hiring|who wants to be hired)\?",
                post.get("metadata", {}).get("parent_title", ""),
                re.I,
            )
        )
    )
    bot = (
        post.get("author", "").lower().endswith("[bot]")
        or post.get("metadata", {}).get("author_type") == "Bot"
    )
    solicitation = (
        bool(
            re.search(
                r"community wishlist|feature request template|feature ideas\s*(?:&|and)\s*requests",
                post.get("title", ""),
                re.I,
            )
        )
        or bool(
            re.search(
                r"\b(?:i'm|i am|we are|we're) (?:trying to understand|curious (?:what|how)|researching how|affiliated with)\b",
                normalized,
            )
        )
        or bool(
            re.search(
                r"\b(?:please )?(?:support|upvote|like|star) (?:this|my|our|the) (?:proposal|project|issue)\b",
                normalized,
            )
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
    audience_signals = classify_audiences(post, context)
    relevant = bool(audience_signals) or any(matches(word, context) for word in DOMAIN)
    if candidate and relevant:
        components["audience_context"] = 10
    created = post.get("created_utc")
    age = (
        ((now if now is not None else datetime.now(timezone.utc).timestamp()) - created)
        / 86400
        if created
        else None
    )
    strong = bool(buying or search or unmet or burden)
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
    state = workflow_state(text)
    if state == "resolved" and quality == "opportunity":
        components["resolved_workflow_penalty"] = -max(0, score - 25)
        score, quality = min(score, 25), "support"
    phrases = list(
        dict.fromkeys(buying + search + unmet + burden + keywords + questions)
    )
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
        "audiences": list(audience_signals),
        "primary_audience": primary_audience(post, audience_signals),
        "audience_signals": audience_signals,
        "audience_method": "explicit_text_and_community_context; labels describe the topic, not a verified personal profile",
        **source_context(post.get("source")),
        "age_days": round(age, 1) if age is not None and age >= 0 else None,
        "freshness": "unknown"
        if age is None or age < 0
        else "recent"
        if age <= 30
        else "historical",
        "current_need_verified": False,
        "workflow_state": state,
        "validation_stage": "unvalidated_problem_signal"
        if quality == "opportunity"
        else "insufficient_signal",
        "willingness_to_pay": "stated_in_text_unverified"
        if buying
        else "not_established",
        "firsthand_context": firsthand,
        "recurring_work_mentioned": recurring,
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
        "scoring_method": "intent_heuristic_v6",
    }


def promising_discussion(post):
    """Ask HN can contain useful replies even without intent in the root question."""
    return (
        post.get("source") == "hackernews"
        and post.get("title", "").lower().startswith("ask hn:")
        and any(matches(word, signal_text(post.get("text", ""))) for word in DOMAIN)
    )
