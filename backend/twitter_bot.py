"""
Twitter Bot — BS Detector
Polls Sorsa API for mentions, checks likes filter, submits to backend, replies via X API.
"""

import os
import json
import time
import logging
import requests
import tweepy
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bs-bot")

# ── Config ────────────────────────────────────────────────────────────────────
SORSA_API_KEY        = os.getenv("SORSA_API_KEY", "")
SORSA_BASE           = "https://api.sorsa.io"

TWITTER_API_KEY      = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET   = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET= os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")

BOT_HANDLE    = os.getenv("TWITTER_BOT_HANDLE", "BullshitDetector")
BACKEND_URL   = os.getenv("BACKEND_URL", "http://localhost:10000")
MIN_LIKES     = int(os.getenv("MIN_LIKES", "500"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))   # seconds between mention checks
PROCESSED_FILE = Path("processed_mentions.json")

SITE_URL = "bullshit-detector-wv8w.onrender.com"


# ── Persistence ───────────────────────────────────────────────────────────────
def load_processed() -> set:
    try:
        return set(json.loads(PROCESSED_FILE.read_text()))
    except Exception:
        return set()


def save_processed(ids: set):
    PROCESSED_FILE.write_text(json.dumps(list(ids)))


# ── Sorsa (read) ──────────────────────────────────────────────────────────────
def _sorsa(path: str, params: dict = None) -> dict:
    """GET request to Sorsa API. Adjust auth header if needed per your plan."""
    r = requests.get(
        f"{SORSA_BASE}{path}",
        params=params,
        headers={"X-API-Key": SORSA_API_KEY},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def get_mentions() -> list:
    """Search for recent tweets mentioning @BOT_HANDLE."""
    # Sorsa uses standard Twitter search operators
    data = _sorsa("/search/tweets", {"query": f"@{BOT_HANDLE}", "count": 20})
    return data.get("tweets", [])


def get_tweet_likes(tweet_id: str) -> int:
    """Return like count for a tweet via Sorsa."""
    data = _sorsa(f"/tweets/{tweet_id}")
    # Sorsa may return favorite_count (v1-style) or public_metrics (v2-style)
    return (
        data.get("favorite_count")
        or data.get("public_metrics", {}).get("like_count", 0)
        or 0
    )


def get_tweet_author(tweet: dict) -> str:
    """Extract screen_name from various Sorsa response shapes."""
    for key in ("author", "user"):
        obj = tweet.get(key)
        if isinstance(obj, dict):
            return obj.get("screen_name") or obj.get("username") or ""
    return ""


def get_referenced_tweet(mention: dict) -> dict | None:
    """Return the tweet being fact-checked (quoted or replied-to tweet)."""
    # v2-style
    refs = mention.get("referenced_tweets")
    if isinstance(refs, list) and refs:
        return refs[0]
    # v1-style quoted tweet
    qt = mention.get("quoted_tweet") or mention.get("retweeted_status")
    if isinstance(qt, dict):
        return qt
    return None


# ── Backend (verify) ──────────────────────────────────────────────────────────
def submit_to_backend(url: str) -> str:
    """Submit tweet URL to BS Detector. Returns job_id."""
    r = requests.post(
        f"{BACKEND_URL}/api/verify/url",
        json={"url": url},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    # If already cached the backend returns status=done directly
    if data.get("status") == "done":
        return f"cached:{json.dumps(data)}"
    return data["job_id"]


def poll_result(job_id: str, max_wait: int = 1800) -> dict | None:
    """Poll /api/poll/{job_id} every 10s until done or timeout."""
    if job_id.startswith("cached:"):
        return json.loads(job_id[7:])

    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = requests.get(f"{BACKEND_URL}/api/poll/{job_id}", timeout=10)
            data = r.json()
            if data.get("status") == "done":
                return data
        except Exception as e:
            logger.warning("Poll error: %s", e)
        time.sleep(10)
    return None


# ── Twitter reply (write) ─────────────────────────────────────────────────────
def _tweepy_client():
    return tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_SECRET,
    )


def format_reply(verdict_data: dict) -> str:
    """Format verdict as a tweet (≤ 280 chars)."""
    v    = verdict_data.get("verdict", "INCONCLUSIVE").upper()
    conf = verdict_data.get("confidence", 0)
    summary = verdict_data.get("evidence_summary", "") or ""

    icons = {"BULLSHIT": "🚨", "LEGIT": "✅", "INCONCLUSIVE": "🤔"}
    icon  = icons.get(v, "🔍")

    header = f"{icon} {v} — {conf}% confidence\n\n"
    footer = f"\n\nVerified on-chain · {SITE_URL}"
    budget = 280 - len(header) - len(footer)

    if len(summary) > budget:
        summary = summary[:budget - 1] + "…"

    return header + summary + footer


def post_reply(text: str, reply_to_id: str):
    client = _tweepy_client()
    client.create_tweet(text=text, in_reply_to_tweet_id=reply_to_id)


# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    processed = load_processed()
    logger.info("Bot started — watching @%s (min %d likes, poll every %ds)",
                BOT_HANDLE, MIN_LIKES, POLL_INTERVAL)

    while True:
        try:
            mentions = get_mentions()
            logger.info("Fetched %d mention(s)", len(mentions))

            for mention in mentions:
                mention_id = str(mention.get("id") or mention.get("id_str") or "")
                if not mention_id or mention_id in processed:
                    continue

                # Mark as processed immediately (avoid double-processing on error)
                processed.add(mention_id)
                save_processed(processed)

                ref = get_referenced_tweet(mention)
                if not ref:
                    logger.info("Mention %s has no referenced tweet — skip", mention_id)
                    continue

                ref_id = str(ref.get("id") or ref.get("id_str") or "")
                if not ref_id:
                    continue

                # ── Likes filter ─────────────────────────────────────────────
                try:
                    likes = get_tweet_likes(ref_id)
                except Exception as e:
                    logger.warning("Could not fetch likes for %s: %s", ref_id, e)
                    continue

                if likes < MIN_LIKES:
                    logger.info("Tweet %s has %d likes (need %d) — skip", ref_id, likes, MIN_LIKES)
                    continue

                logger.info("Tweet %s has %d likes — proceeding", ref_id, likes)

                # ── Build URL ────────────────────────────────────────────────
                ref_author = get_tweet_author(ref) or "i"
                ref_url = f"https://x.com/{ref_author}/status/{ref_id}"

                # ── Submit & wait ────────────────────────────────────────────
                try:
                    job_id = submit_to_backend(ref_url)
                    logger.info("Job %s submitted for %s", job_id[:20], ref_url)
                except Exception as e:
                    logger.error("Backend submit failed: %s", e)
                    continue

                result = poll_result(job_id)
                if not result:
                    logger.error("Timed out on job %s", job_id[:20])
                    continue

                # ── Reply ────────────────────────────────────────────────────
                try:
                    reply_text = format_reply(result)
                    post_reply(reply_text, mention_id)
                    logger.info("Replied to %s: %s (%s%%)",
                                mention_id, result.get("verdict"), result.get("confidence"))
                except Exception as e:
                    logger.error("Failed to post reply: %s", e)

                time.sleep(2)   # gentle on rate limits between replies

        except Exception as e:
            logger.error("Bot loop error: %s", e)

        logger.info("Sleeping %ds…", POLL_INTERVAL)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
