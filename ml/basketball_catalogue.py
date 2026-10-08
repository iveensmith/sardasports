"""Every basketball league the data provider lists, and the order to backfill them in.

`basketball_leagues.json` is the provider's own league list (API-Basketball
`/leagues`), kept in the repository so the site can name a league, place it in a
country and tell a women's competition from a men's one without a request. It is
reference data, not a claim about coverage: a league being listed here does not mean
the site holds results for it. What the site holds is whatever has been ingested.

**Display names.** A league name is only kept bare when it is unique across the
catalogue ("Euroleague", "ACB"). "LNB" is the top league in France, Chile, Paraguay
and the Dominican Republic, so those become "LNB (France)", "LNB (Chile)" and so
on. The NBA keeps the bare name it has always had in the database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name("basketball_leagues.json")

# The free plan serves past seasons from 2022 to 2024 (start years) only.
FIRST_FREE_YEAR = 2022
LAST_FREE_YEAR = 2024

# Backfill order: the leagues most people ask about first, then the rest of the
# professional leagues. Anything not listed is still ingested the moment it appears
# in the daily date feed; this list only decides what history to fetch first.
PRIORITY_IDS = [
    12,  # NBA
    120,  # Euroleague
    13,  # NBA W (WNBA)
    117,  # ACB, Spain
    52,  # Lega A, Italy
    40,  # BBL, Germany
    102,  # TBL, Turkey
    2,  # LNB, France
    31,  # CBA, China
    1,  # NBL, Australia
    56,  # B League, Japan
    91,  # KBL, South Korea
    45,  # Basket League, Greece
    51,  # Super League, Israel
    60,  # LKL, Lithuania
    72,  # Tauron Basket Liga, Poland
    26,  # NBB, Brazil
    18,  # Liga A, Argentina
    63,  # LNBP, Mexico
    20,  # NBA G League
    116,  # NCAA
    85,  # First League, Serbia
    89,  # Liga UPC, Slovenia
    30,  # Premijer liga, Croatia
    74,  # LPB, Portugal
    65,  # DBL, Netherlands
    374,  # Pro Basketball League, Belgium
    108,  # SLB, United Kingdom
    93,  # Ligan, Sweden
    34,  # Canal Digital Ligaen, Denmark
    37,  # Korisliiga, Finland
    68,  # BLNO, Norway
    61,  # NKL, Lithuania
    81,  # Super League, Russia
    66,  # NBL, New Zealand
    267,  # SBL, Taiwan
    76,  # BSN, Puerto Rico
    225,  # LBP, Colombia
    114,  # LNB, Chile
    78,  # Divizia A, Romania
    46,  # NB I A, Hungary
    71,  # 1 Liga, Poland
    8,  # Pro B, France
    42,  # Pro A, Germany
    95,  # Primera FEB, Spain
    104,  # Super Ligi, Turkey
    94,  # Liga Femenina, Spain
    53,  # Serie A1 W, Italy
    10,  # LFB W, France
    41,  # DBBL W, Germany
    92,  # WKBL W, South Korea
    3,  # NBL W, Australia
    125,  # WCBA W, China
    369,  # ENBL
    328,  # BAL, Africa
    389,  # WASL
    386,  # EASL
]


@dataclass(frozen=True)
class League:
    id: int
    name: str
    display: str
    country: str
    country_code: str | None
    kind: str  # "league" or "cup"
    women: bool
    seasons: tuple[str, ...]


@lru_cache(maxsize=1)
def catalogue() -> dict[int, League]:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    return {
        int(key): League(
            id=int(key),
            name=value["name"],
            display=value["display"],
            country=value["country"],
            country_code=value.get("country_code"),
            kind=value["type"],
            women=value["women"],
            seasons=tuple(value["seasons"]),
        )
        for key, value in raw.items()
    }


def league(league_id: int) -> League | None:
    return catalogue().get(league_id)


def display_name(league_id: int, fallback: str, country: str | None = None) -> str:
    """The competition name to store for a league id, however it arrived."""
    found = league(league_id)
    if found is not None:
        return found.display
    return f"{fallback} ({country})" if country else fallback


def by_display_name() -> dict[str, League]:
    return {entry.display: entry for entry in catalogue().values()}


def free_plan_seasons(league_id: int) -> list[str]:
    """The league's seasons that the free plan will serve (start year 2022 to 2024)."""
    found = league(league_id)
    if found is None:
        return []
    keep = []
    for label in found.seasons:
        try:
            start = int(str(label)[:4])
        except ValueError:
            continue
        if FIRST_FREE_YEAR <= start <= LAST_FREE_YEAR:
            keep.append(str(label))
    return sorted(keep)
