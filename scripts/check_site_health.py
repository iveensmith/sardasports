"""Check that the things that have gone missing before are actually on the home page.

The home page's results strip (the scrolling carousel of graded picks) has vanished
more than once, each time for a different reason, and each time a visitor noticed
before we did. This script is the "did it come back" check, so it can be run after
any change and from a scheduler or a deploy step.

It checks, in order:

1. the engine answers its own strip endpoint with enough graded picks;
2. the website's home page actually contains the strip, with items in it;
3. the home page's boards show predictions, not an engine-unreachable banner.

    python scripts/check_site_health.py
    python scripts/check_site_health.py --web http://localhost:3000 --engine http://127.0.0.1:8000

Exit status is 0 only if every check passes, so it can gate a deploy.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

# Keep in step with MIN_STRIP_ITEMS in web/lib/api.ts.
MIN_STRIP_ITEMS = 4


def fetch(url: str, timeout: float) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except Exception as error:  # noqa: BLE001
        return 0, f"{type(error).__name__}: {error}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--web", default="http://localhost:3000")
    parser.add_argument("--engine", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    failures: list[str] = []

    status, body = fetch(f"{args.engine}/board/recent-settled?limit=24", args.timeout)
    if status != 200:
        failures.append(f"engine strip endpoint returned {status}: {body[:120]}")
    else:
        data = json.loads(body)
        stale = " (served stale)" if data.get("stale") else ""
        print(f"engine strip endpoint: {data['count']} graded picks{stale}")
        if data["count"] < MIN_STRIP_ITEMS:
            failures.append(
                f"engine has only {data['count']} graded picks, "
                f"below the {MIN_STRIP_ITEMS} the strip needs"
            )

    status, page = fetch(f"{args.web}/", args.timeout)
    if status != 200:
        failures.append(f"home page returned {status}")
    else:
        strip = re.search(
            r'<section[^>]*aria-label="Recently settled picks".*?</section>', page, re.S
        )
        if not strip:
            failures.append("the results strip is NOT on the home page")
        else:
            items = len(re.findall(r"<li", strip.group(0)))
            print(f"home page strip: present, {items // 2} picks (the track is doubled)")
            if items < MIN_STRIP_ITEMS:
                failures.append(f"the strip is present but has only {items} items")
        if "engine is unreachable" in page:
            failures.append("the home page is showing the engine-unreachable banner")
        if "no trained model" in page:
            failures.append("the home page is claiming fixtures have no trained model")
        print(f"home page boards: {page.count('<table')} tables")

    if failures:
        print("\nFAILED")
        for line in failures:
            print(f" - {line}")
        return 1
    print("\nOK: the carousel is on the home page and the boards are populated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
