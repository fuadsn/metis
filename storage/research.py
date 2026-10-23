"""Local research notes, kept separate from original posts and lead scoring."""

import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import List, Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

RESEARCH_SOURCES = {
    "ukbusinessforums": {
        "host": "www.ukbusinessforums.co.uk",
        "path_prefix": "/threads/",
        "audience": "small_business",
        "access_note": "Manual pilot; direct robots access returned HTTP 403 on 2026-10-23.",
    },
    "moneysavingexpert": {
        "host": "forums.moneysavingexpert.com",
        "path_prefix": "/discussion/",
        "audience": "everyday_life",
        "access_note": "Manual pilot; direct HTTPS failed in the tested runtime on 2026-10-23. Automated access is not established.",
    },
    "capterra": {
        "host": "www.capterra.com",
        "path_prefix": "/p/",
        "audience": "small_business",
        "access_note": "Manual review research; direct page access returned HTTP 403 on 2026-10-23. No automated feed configured.",
    },
}


def research_sources():
    return [
        {
            "source": source,
            "status": "manual_research",
            "automatic_collection": False,
            **details,
        }
        for source, details in RESEARCH_SOURCES.items()
    ]


class ResearchNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["ukbusinessforums", "moneysavingexpert", "capterra"]
    url: str = Field(min_length=1, max_length=2000)
    locator: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=250)
    author_label: str = Field(default="", max_length=100)
    published_on: Optional[date] = None
    date_note: str = Field(default="", max_length=300)
    observed_on: date
    audience: Literal["small_business", "everyday_life", "developer_tools"]
    observation: Literal[
        "problem_report",
        "research_question",
        "existing_solution",
        "positive_experience",
    ]
    summary: str = Field(min_length=1, max_length=1200)
    excerpt: str = Field(default="", max_length=400)
    incentive: Literal[
        "incentivized", "non_incentivized", "unknown", "not_applicable"
    ] = "unknown"
    caveat: str = Field(min_length=1, max_length=600)
    follow_up: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def check_provenance(self):
        parsed = urlsplit(self.url)
        source = RESEARCH_SOURCES[self.source]
        if (
            parsed.scheme != "https"
            or parsed.netloc != source["host"]
            or not parsed.path.startswith(source["path_prefix"])
        ):
            raise ValueError(
                "Use an HTTPS discussion/review URL on the selected source"
            )
        if self.observed_on > date.today() or (
            self.published_on and self.published_on > self.observed_on
        ):
            raise ValueError(
                "Observation cannot be in the future or precede publication"
            )
        if self.published_on is None and not self.date_note.strip():
            raise ValueError(
                "Unknown publication dates need a date_note; do not substitute discovery time"
            )
        if len(self.excerpt.split()) > 25:
            raise ValueError(
                "Keep excerpts to at most 25 words; write your own summary"
            )
        if any(
            not getattr(self, key).strip()
            for key in ("title", "locator", "summary", "caveat", "follow_up")
        ):
            raise ValueError("Research fields must not be blank")
        return self


class ResearchBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    notes: List[ResearchNote] = Field(min_length=1, max_length=100)


def import_research(path, store):
    path = Path(path)
    if path.stat().st_size > 1_000_000:
        raise ValueError("Research import must be at most 1 MB")
    try:
        batch = ResearchBatch.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, UnicodeError):
        raise ValueError(
            "Invalid research batch; check the schema in docs/source-pilot.md"
        ) from None
    rows = []
    for note in batch.notes:
        identity = json.dumps([note.source, note.url, note.locator], ensure_ascii=False)
        key = "research:" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        rows.append(
            (
                key,
                note.source,
                note.published_on.isoformat() if note.published_on else None,
                json.dumps(note.model_dump(mode="json")),
            )
        )
    if len({row[0] for row in rows}) != len(rows):
        raise ValueError(
            "Duplicate research note in batch; use one note per URL and locator"
        )
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    with store.connection() as db:
        for key, source, published, payload in rows:
            previous = db.execute(
                "SELECT payload FROM research_notes WHERE id=?", (key,)
            ).fetchone()
            counts[
                "new"
                if not previous
                else "unchanged"
                if previous[0] == payload
                else "updated"
            ] += 1
            db.execute(
                "INSERT INTO research_notes VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET published_on=excluded.published_on, payload=excluded.payload",
                (key, source, published, payload),
            )
    return {
        "status": "success",
        "imported": len(rows),
        **counts,
        "scored_as_leads": False,
    }


def list_research(store, source=None, limit=20):
    if source is not None and source not in RESEARCH_SOURCES:
        raise ValueError("Unknown research source")
    if not 1 <= limit <= 1000:
        raise ValueError("Research limit must be 1–1000")
    sql, args = "SELECT id, payload FROM research_notes", []
    if source:
        sql += " WHERE source=?"
        args.append(source)
    sql += " ORDER BY published_on DESC, id"
    with store.connection() as db:
        rows = list(db.execute(sql, args))
    notes = []
    for key, payload in rows:
        note = json.loads(payload)
        published = (
            date.fromisoformat(note["published_on"]) if note["published_on"] else None
        )
        notes.append(
            {
                **note,
                "id": key,
                "age_days": (date.today() - published).days if published else None,
                "collection_method": "manual_research",
                "evidence_kind": "analyst_note",
                "scored_as_lead": False,
                "current_need_verified": False,
                "willingness_to_pay": "not_established",
            }
        )
    return {
        "status": "success",
        "total": len(notes),
        "source_counts": dict(Counter(note["source"] for note in notes)),
        "observation_counts": dict(Counter(note["observation"] for note in notes)),
        "research_notes": notes[:limit],
        "interpretation": "Research notes are analyst observations, not original posts, verified buyers, or independent repeat evidence. Unknown dates remain unknown.",
    }
