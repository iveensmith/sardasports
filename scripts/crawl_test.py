"""Pretend to be a search-engine crawler against a running copy of the site.

Fetches a sample of the sitemap's URLs a few at a time, the way a crawler arriving for the
first time would, and reports how many came back healthy, how long they took, and which
failed. It exists to answer one question before the site is opened to Google: does a burst
of cold page requests make the engine fall over (500s, timeouts, or the "engine is
unreachable" banner on a page that returned 200)?

Usage (against a production build, not `next dev`, which compiles on demand):
    python scripts/crawl_test.py --base http://localhost:3001 --sample 120 --concurrency 4
"""

from __future__ import annotations

import argparse
import random
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BANNERS = ("The engine is unreachable", "could not be loaded just now", "This page couldn")


def fetch(url: str, timeout: float) -> tuple[str, int, float, str]:
    started = time.monotonic()
    try:
        with urlopen(Request(url, headers={"User-Agent": "crawl-test"}), timeout=timeout) as r:
            body = r.read().decode("utf-8", "ignore")
            status = r.status
    except HTTPError as exc:
        return url, exc.code, time.monotonic() - started, ""
    except (URLError, TimeoutError, OSError):
        return url, 0, time.monotonic() - started, ""
    banner = next((b for b in BANNERS if b in body), "")
    return url, status, time.monotonic() - started, banner


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:3001")
    parser.add_argument("--sample", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    with urlopen(f"{args.base}/sitemap.xml", timeout=60) as r:
        sitemap = r.read().decode()
    paths = [re.sub(r"^https?://[^/]+", "", u) for u in re.findall(r"<loc>([^<]+)</loc>", sitemap)]
    random.Random(args.seed).shuffle(paths)
    paths = paths[: args.sample]
    print(f"sitemap has the URLs; crawling {len(paths)} of them, {args.concurrency} at a time")

    started = time.monotonic()
    with ThreadPoolExecutor(args.concurrency) as pool:
        results = list(pool.map(lambda p: fetch(args.base + p, args.timeout), paths))
    elapsed = time.monotonic() - started

    ok = [r for r in results if r[1] == 200 and not r[3]]
    bad = [r for r in results if r not in ok]
    times = sorted(r[2] for r in results)
    print(f"{len(ok)}/{len(results)} healthy in {elapsed:.0f}s ({len(results) / elapsed:.1f} pages/s)")
    print(
        f"time per page: median {statistics.median(times):.1f}s, "
        f"p90 {times[int(len(times) * 0.9) - 1]:.1f}s, max {times[-1]:.1f}s"
    )
    print("slowest:")
    for url, _status, took, _banner in sorted(results, key=lambda r: -r[2])[:8]:
        print(f"  {took:5.1f}s {url}")
    for url, status, took, banner in bad[:20]:
        print(f"  FAIL {status or 'no response'} {took:.0f}s {banner} {url}")


if __name__ == "__main__":
    main()
