"""A short-lived in-process cache that runs each computation once, however many ask.

Why it exists
-------------
A board for one day is expensive to build the first time and identical for every
reader afterwards. The web app asks for the same day several times at once (the
home page's yesterday/today/tomorrow, Next's prefetch, a second tab), and a plain
cache does not help with that: ten requests arriving together all miss, and all
ten start the work. On a busy day that piled up the backend's thread pool, held a
database connection per request until the pool ran dry, and kept going for
minutes after the browsers had given up.

`CoalescingCache.get_or_compute` fixes the *simultaneous* case: the first caller
for a key computes, every other caller for that key waits for that one result.
Waiters do not touch the database, so they hold no connection while they wait.

Two further limits keep a burst of *different* keys from doing the same damage:
only `max_concurrent` computations run at once (CPU-bound Python gains nothing
from more, and each holds a pooled connection), and a waiter that has waited too
long computes for itself rather than hanging with the leader.

A failed computation is never cached. Its waiters do not inherit the failure;
the next one to wake becomes the new leader and tries again.

Results are returned as deep copies. The cached object is shared by every reader,
and a route that sorts or annotates what it was handed would otherwise change it
for the next request.
"""

from __future__ import annotations

import copy
import threading
import weakref
from collections import OrderedDict
from collections.abc import Callable, Hashable
from time import monotonic
from typing import Any

_ALL_CACHES: weakref.WeakSet[CoalescingCache] = weakref.WeakSet()


class _Flight:
    """One computation in progress, and what its waiters need to know about it."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.ok = False
        self.value: Any = None


class CoalescingCache:
    def __init__(
        self,
        ttl_seconds: float,
        *,
        max_entries: int = 64,
        max_concurrent: int = 2,
        wait_timeout_seconds: float = 120.0,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._wait_timeout = wait_timeout_seconds
        self._lock = threading.Lock()
        self._entries: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._flights: dict[Hashable, _Flight] = {}
        self._slots = threading.BoundedSemaphore(max_concurrent)
        _ALL_CACHES.add(self)

    def clear(self) -> None:
        """Forget every stored result. Computations already running still finish."""
        with self._lock:
            self._entries.clear()

    def get_or_compute(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        deadline = monotonic() + self._wait_timeout
        while True:
            with self._lock:
                hit = self._entries.get(key)
                if hit is not None and hit[0] > monotonic():
                    self._entries.move_to_end(key)
                    return copy.deepcopy(hit[1])
                flight = self._flights.get(key)
                leader = flight is None
                if leader:
                    flight = self._flights[key] = _Flight()

            if leader:
                return self._lead(key, flight, compute)

            remaining = deadline - monotonic()
            if remaining <= 0 or not flight.done.wait(remaining):
                # The leader is taking far too long. Computing for ourselves is
                # slower than waiting would have been, but it is bounded.
                return compute()
            if flight.ok:
                return copy.deepcopy(flight.value)
            # The leader failed: go round again and either find a new leader's
            # flight to wait on or become the leader.

    def _lead(self, key: Hashable, flight: _Flight, compute: Callable[[], Any]) -> Any:
        try:
            with self._slots:
                value = compute()
            flight.value, flight.ok = value, True
            with self._lock:
                self._entries[key] = (monotonic() + self._ttl, value)
                self._entries.move_to_end(key)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
            return copy.deepcopy(value)
        finally:
            with self._lock:
                self._flights.pop(key, None)
            flight.done.set()


def clear_all_caches() -> None:
    """Empty every `CoalescingCache` in the process (used between tests, and handy
    after a bulk data change when waiting out the TTL would be a nuisance)."""
    for cache in list(_ALL_CACHES):
        cache.clear()
