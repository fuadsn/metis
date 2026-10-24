"""Conservative task/obstacle signatures. Unrecognized or ambiguous needs stay apart.

These rules are a bounded vocabulary, not semantic understanding. Topic labels
are presentation only; they never establish a match. No parent intent is used.
"""

import re

from processors.signals import affirmed, matching_text, signal_text

# Each task needs all cue groups. More specific tasks outrank their parents.
TASKS = {
    "bank_transaction_import": (
        "Import bank transactions",
        "Use bank transactions in a budgeting or accounting workflow",
        (
            r"\b(?:bank|card|statement|transactions?)\b",
            r"\b(?:csv|ofx|qif|import\w*|export\w*)\b",
        ),
    ),
    "budget_plan_maintenance": (
        "Maintain a monthly budget",
        "Keep a spending plan current as expenses change",
        (
            r"\bbudget\w*\b",
            r"\b(?:monthly|month|categor\w*|spending)\b",
            r"\b(?:adjust\w*|updat\w*|maintain\w*|var[yi]\w*|chang\w*)\b",
        ),
    ),
    "inventory_count": (
        "Reconcile physical inventory counts",
        "Keep recorded inventory consistent with a physical count",
        (
            r"\b(?:inventory|stock|sku|skus)\b",
            r"\b(?:count\w*|reconcil\w*|stocktake|stocktaking|audit\w*|check\w*)\b",
        ),
    ),
    "inventory_sync": (
        "Synchronize inventory between systems",
        "Keep stock levels consistent across stores or systems",
        (r"\b(?:inventory|stock|sku|skus)\b", r"\b(?:sync\w*|wms|warehouse system)\b"),
    ),
    "invoice_reconciliation": (
        "Match payments to invoices",
        "Allocate received payments to the correct invoices",
        (
            r"\binvoices?\b",
            r"\b(?:payments?|bank|remittance)\b",
            r"\b(?:match\w*|reconcil\w*|allocat\w*)\b",
        ),
    ),
    "invoice_entry": (
        "Enter invoice records",
        "Move invoice details into the working records",
        (r"\binvoices?\b", r"\b(?:enter\w*|copy\w*|re-enter\w*|key\w*|input\w*)\b"),
    ),
    "invoice_collection": (
        "Collect overdue invoices",
        "Receive payment for outstanding invoices",
        (r"\binvoices?\b", r"\b(?:overdue|unpaid|chasing|chase|late payment)\b"),
    ),
    "appointment_scheduling": (
        "Manage appointments",
        "Keep appointments booked and attended",
        (
            r"\bappointments?\b",
            r"\b(?:schedul\w*|book\w*|miss\w*|no.show|chasing|remind\w*)\b",
        ),
    ),
    "childcare_shift_coverage": (
        "Arrange childcare around shifts",
        "Cover childcare during changing working hours",
        (r"\b(?:childcare|nursery|nanny)\b", r"\b(?:shifts?|rota|working hours)\b"),
    ),
    "school_payment_tracking": (
        "Track school payments",
        "Track which school payments are due or paid",
        (r"\bschools?\b", r"\bpayments?\b", r"\b(?:track\w*|due|deadline|diary)\b"),
    ),
    "meal_planning": (
        "Plan household meals",
        "Maintain a workable household meal plan",
        (r"\bmeals?\b", r"\bplan\w*\b"),
    ),
    "spreadsheet_tax_filing": (
        "Connect bookkeeping to tax filing",
        "Use existing records in a tax filing workflow",
        (
            r"\b(?:tax|mtd)\b",
            r"\b(?:spreadsheets?|excel|bookkeeping)\b",
            r"\b(?:fil\w*|submit\w*|bridg\w*)\b",
        ),
    ),
    "deployment_workflow": (
        "Run software releases",
        "Complete a deployment workflow",
        (r"\b(?:deploy\w*|ci/cd|release pipeline)\b",),
    ),
    "deployment_rollback": (
        "Roll back a software release",
        "Restore the previous working release",
        (r"\b(?:deploy\w*|ci/cd|releases?)\b", r"\brollback\b|\broll back\b"),
    ),
}

OBSTACLES = {
    "data_format": (
        "Incompatible data formats or field mappings",
        r"\b(?:wrong|incorrect|different|incompatible|unsupported|missing)\b.{0,35}\b(?:format\w*|columns?|mapping|headers?|fields?)\b|\b(?:format\w*|columns?|mapping|headers?|fields?)\b.{0,35}\b(?:wrong|incorrect|different|incompatible|mismatch\w*|manually)\b",
    ),
    "categorization": (
        "Manual or incorrect categorization",
        r"\b(?:manual\w*|wrong|incorrect)\b.{0,35}\bcategori[sz]\w*\b|\bcategori[sz]\w*\b.{0,35}\bmanual\w*\b",
    ),
    "stock_state_mismatch": (
        "Physical and reserved stock counts disagree",
        r"\b(?:committed|reserved|on.hand)\b",
    ),
    "late_payment": (
        "Payments arrive late or remain unpaid",
        r"\b(?:overdue|unpaid|chasing|chase|late)\b",
    ),
    "missed_appointments": ("Appointments are missed", r"\b(?:miss\w*|no.show)\b"),
    "schedule_conflict": (
        "Required times do not fit available coverage",
        r"\b(?:alternat\w*|rotat\w*|chang\w*|conflict\w*|cover\w*|double.book\w*|unpredictable)\b",
    ),
    "plan_adjustment": (
        "Changing plans require repeated updates",
        r"\b(?:adjust\w*|updat\w*|maintain\w*|var[yi]\w*|chang\w*|cumbersome)\b",
    ),
    "payment_status": (
        "Payment due and paid status is hard to track",
        r"\b(?:track\w*|due|deadline|diary)\b",
    ),
    "setup_fit": (
        "Existing records do not fit the filing workflow",
        r"\b(?:bridg\w*|manually|confus\w*|unsure|cannot|can't|unusable)\b",
    ),
    "manual_work": (
        "Repeated manual steps",
        r"\b(?:manual\w*|repetitiv\w*|repeat\w*|copy\w*|re-enter\w*|chasing)\b",
    ),
    "reliability": (
        "The workflow fails or produces errors",
        r"\b(?:fails?|failing|broken|crash\w*|unreliable|errors?|wrong|incorrect)\b",
    ),
    "cost": (
        "The current solution costs too much",
        r"\b(?:too expensive|costs too much|cheaper|unaffordable)\b",
    ),
    "missing_capability": (
        "A required capability is unavailable",
        r"\b(?:cannot|can't|missing|doesn't support|does not support|wish there was)\b",
    ),
}
SPECIFIC_OBSTACLES = {
    "bank_transaction_import": ["categorization", "data_format"],
    "budget_plan_maintenance": ["plan_adjustment"],
    "inventory_count": ["stock_state_mismatch"],
    "invoice_collection": ["late_payment"],
    "appointment_scheduling": ["missed_appointments", "schedule_conflict"],
    "childcare_shift_coverage": ["schedule_conflict"],
    "school_payment_tracking": ["payment_status"],
    "spreadsheet_tax_filing": ["setup_fit"],
}


def problem_signature(post):
    # Title can describe the task, but obstacle evidence must be in the author's
    # own body when one exists. Video/thread parent titles are deliberately absent.
    body = signal_text(post.get("body", ""))
    own = signal_text("\n".join((post.get("title", ""), body)))
    text = matching_text(own)
    found = [
        key
        for key, (_, _, groups) in TASKS.items()
        if all(re.search(g, text) for g in groups)
    ]
    # A bank import and budget-plan maintenance are distinct operations. A post
    # discussing both cannot connect their groups by acting as a bridge.
    if "deployment_rollback" in found and "deployment_workflow" in found:
        found.remove("deployment_workflow")
    task = found[0] if len(found) == 1 else None
    obstacle = None
    excerpt = ""
    if task:
        candidates = SPECIFIC_OBSTACLES.get(task, []) + [
            "cost",
            "reliability",
            "manual_work",
            "missing_capability",
        ]
        for key in candidates:
            excerpts = []
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", body or own):
                if any(
                    affirmed(m.group(), sentence)
                    for m in re.finditer(OBSTACLES[key][1], matching_text(sentence))
                ):
                    excerpts.append(sentence.strip())
            if excerpts:
                obstacle = key
                # Prefer the sentence describing the difficulty over a neutral
                # introduction that merely names the relevant stock/data state.
                excerpt = max(
                    excerpts,
                    key=lambda s: (
                        bool(
                            re.search(
                                r"\b(?:manual\w*|have to|only way|struggl\w*|constantly|wrong|incorrect|cannot|can't)\b",
                                matching_text(s),
                            )
                        ),
                        sum(
                            bool(re.search(g, matching_text(s))) for g in TASKS[task][2]
                        ),
                    ),
                )[:600]
            if obstacle:
                break
    matchable = bool(task and obstacle)
    return {
        "task": task,
        "task_label": TASKS[task][0] if task else None,
        "desired_outcome": TASKS[task][1] if task else None,
        "obstacle": obstacle,
        "obstacle_label": OBSTACLES[obstacle][0] if obstacle else None,
        "obstacle_excerpt": excerpt,
        "audience": post.get("primary_audience"),
        "matchable": matchable,
        "status": "matched_task_and_obstacle"
        if matchable
        else "ambiguous_tasks"
        if len(found) > 1
        else "insufficient_specificity",
        "possible_tasks": found,
        "method": "task_obstacle_rules_v1",
    }


def problem_key(point):
    signature = point.get("problem_signature") or problem_signature(point)
    if not signature["matchable"]:
        return ("unmatched", point.get("post_id") or point["id"])
    return (signature["task"], signature["obstacle"], signature["audience"])
