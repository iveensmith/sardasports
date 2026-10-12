"""How much memory this process holds, for the health check and the logs.

Read from `/proc/self/status` (Linux, which is where it matters: the production
container). Anywhere else it reports None rather than guessing, because a made-up
number in a health response is worse than no number.
"""

from __future__ import annotations


def rss_mb() -> float | None:
    """Resident memory of this process in megabytes, or None where it cannot be read."""
    try:
        with open("/proc/self/status", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        return None
    return None
