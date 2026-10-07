"""Is there API-Football quota left for this job?

The scheduler runs several jobs that spend API requests, and a free plan allows
a hundred a day. Switch it on without a guard and the first job to be greedy
spends the day: the injury sync alone looped over every team in the database —
3,467 of them, tennis players included — and would have exhausted the quota at
03:30, leaving every other job to fail until midnight.

This asks API-Football itself. Its `/status` endpoint reports how many requests
the account has used today and how many it is allowed, and it is free: it does
not count against the quota. Asking the source, rather than keeping a local
tally, means a script run by hand, a second process, or yesterday's drift can
never make the guard wrong, and there is no state to persist or reset.

It fails closed. If the status cannot be read, the answer is "don't spend":
skipping one run of a job is cheap, and guessing wrong is not.
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

# Left unspent so a script run by hand has some room, and so a job's worst-case
# estimate being a little low does not push the day over.
MARGIN = 5

# A daily limit at or above this means a paid plan. The free plan allows 100;
# the smallest paid tier allows several thousand.
PAID_DAILY_LIMIT = 1000


def api_status(settings, timeout: int = 15) -> dict | None:
    """`{"used": int, "limit": int, "plan": str}`, or None if it cannot be read."""
    if not getattr(settings, "api_football_key", None):
        return None
    try:
        response = requests.get(
            f"{settings.api_football_base_url}/status",
            headers={"x-apisports-key": settings.api_football_key},
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json().get("response") or {}
        requests_info = body["requests"]
        return {
            "used": int(requests_info["current"]),
            "limit": int(requests_info["limit_day"]),
            "plan": (body.get("subscription") or {}).get("plan", "unknown"),
        }
    except Exception as exc:  # network, bad JSON, missing keys: all mean "unknown"
        logger.warning("Could not read the API-Football status: %s", exc)
        return None


def remaining_requests(settings) -> int | None:
    status = api_status(settings)
    if status is None:
        return None
    return max(0, status["limit"] - status["used"])


def can_spend(settings, cost: int, margin: int = MARGIN) -> bool:
    """True if `cost` requests fit in what is left today, with `margin` to spare."""
    remaining = remaining_requests(settings)
    if remaining is None:
        return False
    return remaining >= cost + margin


def is_paid_plan(settings) -> bool:
    """True only if the account is positively known to be on a paid plan.

    An unreadable status is "no": the free-plan cadence is the safe one.
    """
    status = api_status(settings)
    return status is not None and status["limit"] >= PAID_DAILY_LIMIT
