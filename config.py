"""Configuration shared by collection, CLI, and scheduled runs."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
IS_CHECKOUT = (BASE_DIR / "pyproject.toml").exists()
ENV_FILE = (
    Path(os.environ["METIS_ENV_FILE"]).expanduser()
    if os.getenv("METIS_ENV_FILE")
    else (BASE_DIR if IS_CHECKOUT else Path.cwd()) / ".env"
)
load_dotenv(ENV_FILE, override=False)
DEFAULT_DATA_DIR = (
    BASE_DIR / "data"
    if IS_CHECKOUT
    else Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    / "metis"
)
DATA_DIR = Path(os.getenv("METIS_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser()
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
COLLECTION_INTERVAL_HOURS = 6
SOURCE_NAMES = ("hackernews", "reddit", "x", "github", "stackexchange")
DEFAULT_SOURCES = ("hackernews", "github", "stackexchange")
PAIN_KEYWORDS = [
    "tired of",
    "sick of",
    "wish there was",
    "has anyone found",
    "looking for",
    "can't find",
    "cannot find",
    "no good",
    "broken",
    "frustrated",
    "annoying",
    "problem with",
    "issues with",
    "hard to",
    "difficult to",
    "can't seem to",
    "any recommendations",
    "alternative to",
    "alternatives to",
    "workaround",
    "manual work",
    "manually",
    "feature request",
    "would pay",
    "willing to pay",
    "too expensive",
    "missing feature",
    "doesn't support",
    "does not support",
]


def csv_env(name, default):
    return [
        part.strip() for part in os.getenv(name, default).split(",") if part.strip()
    ]


def queries_env(name, default):
    value = json.loads(os.environ[name]) if os.getenv(name) else default
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(query, str) and query.strip() for query in value)
    ):
        raise ValueError(f"{name} must be a nonempty JSON array of search strings")
    return value


@dataclass
class Settings:
    comment_threads: int = field(
        default_factory=lambda: int(os.getenv("METIS_COMMENT_THREADS", "3"))
    )
    comments_per_thread: int = field(
        default_factory=lambda: int(os.getenv("METIS_COMMENTS_PER_THREAD", "3"))
    )
    sources: List[str] = field(
        default_factory=lambda: csv_env("METIS_SOURCES", ",".join(DEFAULT_SOURCES))
    )
    subreddits: List[str] = field(
        default_factory=lambda: csv_env(
            "METIS_SUBREDDITS", "SaaS,startups,smallbusiness,webdev,devops,selfhosted"
        )
    )
    reddit_client_id: str = field(
        default_factory=lambda: os.getenv("REDDIT_CLIENT_ID", ""), repr=False
    )
    reddit_client_secret: str = field(
        default_factory=lambda: os.getenv("REDDIT_CLIENT_SECRET", ""), repr=False
    )
    reddit_refresh_token: str = field(
        default_factory=lambda: os.getenv("REDDIT_REFRESH_TOKEN", ""), repr=False
    )
    reddit_user_agent: str = field(
        default_factory=lambda: os.getenv("REDDIT_USER_AGENT", "python:metis:v0.2.0")
    )
    x_bearer_token: str = field(
        default_factory=lambda: os.getenv("X_BEARER_TOKEN", ""), repr=False
    )
    github_token: str = field(
        default_factory=lambda: os.getenv("GITHUB_TOKEN", ""), repr=False
    )
    stackexchange_key: str = field(
        default_factory=lambda: os.getenv("STACKEXCHANGE_KEY", ""), repr=False
    )
    github_queries: List[str] = field(
        default_factory=lambda: queries_env(
            "METIS_GITHUB_QUERIES",
            [
                '"feature request" "workflow" in:title,body',
                '"workaround" "deployment" in:title,body',
                '"looking for" "integration" in:title,body',
            ],
        )
    )
    x_queries: List[str] = field(
        default_factory=lambda: queries_env(
            "METIS_X_QUERIES",
            [
                '("looking for" OR "wish there was" OR "alternative to") (developer OR SaaS OR startup) lang:en -is:retweet',
            ],
        )
    )
    stackexchange_sites: List[str] = field(
        default_factory=lambda: csv_env(
            "METIS_STACKEXCHANGE_SITES", "stackoverflow,serverfault"
        )
    )
    stackexchange_queries: List[str] = field(
        default_factory=lambda: queries_env(
            "METIS_STACKEXCHANGE_QUERIES", ["deployment workaround", "manual workflow"]
        )
    )

    def __post_init__(self):
        if (
            not 0 <= self.comment_threads <= 5
            or not 1 <= self.comments_per_thread <= 10
        ):
            raise ValueError(
                "comment_threads must be 0–5 and comments_per_thread must be 1–10"
            )
        unknown = set(self.sources) - set(SOURCE_NAMES)
        if unknown:
            raise ValueError(f"Unknown sources: {', '.join(sorted(unknown))}")
        self.sources = list(dict.fromkeys(self.sources))
        if not self.sources:
            raise ValueError("At least one source is required")
        for name in ("github_queries", "x_queries", "stackexchange_queries"):
            values = getattr(self, name)
            if not values or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                raise ValueError(
                    f"{name} must contain at least one nonempty search string"
                )
