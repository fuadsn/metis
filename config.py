import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

SUBREDDITS = [
    "startups",
    "saas",
    "indiehackers",
    "entrepreneur",
    "smallbusiness",
    "coding",
    "programming",
    "devops",
    "sysadmin",
    "webdev",
]

POSTS_PER_SUBREDDIT = 200

REDDIT_PRAW_CONFIG = {
    "client_id": os.getenv("REDDIT_CLIENT_ID", ""),
    "client_secret": os.getenv("REDDIT_CLIENT_SECRET", ""),
    "user_agent": os.getenv("REDDIT_USER_AGENT", "metis/1.0"),
}

PUSHSHIFT_URL = "https://api.pushshift.io/reddit/search/submission"

COLLECTION_INTERVAL_HOURS = 6

PUSHshift_CONFIG = {
    "base_url": "https://api.pushshift.io/reddit/search/submission",
    "posts_per_request": 200,
}

PAIN_KEYWORDS = [
    "tired of",
    "sick of",
    "wish there was",
    "has anyone found",
    "looking for",
    "can't find",
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
    "what's the best",
    " Alternatives ",
    "vs ",
]

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HN_SOURCES = ["top", "new"]
