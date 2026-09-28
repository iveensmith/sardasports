"""Team name normalization.

Different data sources spell the same club differently ("Man United" vs.
"Manchester United", "Nott'm Forest" vs. "Nottingham Forest"). This module
centralizes normalization so ingestion, features, and the API all agree on
one canonical name per club.
"""

from __future__ import annotations

import re
import unicodedata

# Known aliases -> canonical name. Extend as new data sources/leagues are added.
ALIASES: dict[str, str] = {
    "man united": "Manchester United",
    "man utd": "Manchester United",
    "man city": "Manchester City",
    "spurs": "Tottenham Hotspur",
    "tottenham": "Tottenham Hotspur",
    "wolves": "Wolverhampton Wanderers",
    "nott'm forest": "Nottingham Forest",
    "nottm forest": "Nottingham Forest",
    "newcastle": "Newcastle United",
    "west brom": "West Bromwich Albion",
    "west ham": "West Ham United",
    "leicester": "Leicester City",
    "leeds": "Leeds United",
    "norwich": "Norwich City",
    "brighton": "Brighton & Hove Albion",
    "sheffield united": "Sheffield United",
    "qpr": "Queens Park Rangers",
}


def fold_team_key(name: str) -> str:
    """A comparison key that ignores accents, case and punctuation spacing.

    Sources disagree on diacritics for the same club — Football-Data.co.uk
    writes "Castellon", API-Football writes "Castellón" — and storing both
    creates two teams, splitting one club's match history in half and
    leaving the newer row with no Elo. Canonical *display* names keep their
    accents; only lookups fold.
    """
    if not isinstance(name, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def normalize_team_name(raw_name: str) -> str:
    """Return the canonical form of a team name.

    Defensively handles a non-string input (e.g. a pandas NaN float from a
    source CSV with a blank field) by returning an empty string rather than
    raising — callers that need a real name still validate for a non-empty
    result afterward; this just means a malformed row gets dropped, not a
    pipeline crash.
    """
    if not isinstance(raw_name, str):
        return ""
    cleaned = re.sub(r"\s+", " ", raw_name.strip())
    alias = ALIASES.get(cleaned.lower())
    if alias:
        return alias
    return cleaned
