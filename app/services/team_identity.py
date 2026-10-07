"""Which of our team rows is this API-Football club?

Two sources name the same club differently. Football-Data.co.uk writes
"Ath Bilbao", "Ath Madrid", "Espanol", "Celta", "M'gladbach"; API-Football
writes "Athletic Club", "Atletico Madrid", "Espanyol", "Celta Vigo",
"Borussia Mönchengladbach". Get this wrong and one club has two rating
histories, each too short to mean anything — silently, with no error.

Why this is a *matching* problem and not a similarity search
-------------------------------------------------------------
Fuzzy-matching a name against every club in the database is unsafe. Measured
on real Copa del Rey data, the closest string to "Atletico Madrid" was
"Atletico-MG" (a Brazilian club) and to "Chiclana" was "China". Names alone do
not carry enough information.

What does carry it is *context*. La Liga 2024-25 has twenty clubs in the API
and the same twenty in our data, so the question is not "which of 3,579 teams
does this resemble" but "pair these twenty with those twenty" — a one-to-one
assignment, where even a weak resemblance is decisive because every wrong
answer has already been claimed by the right club. `assign_clubs` solves
exactly that, optimally, and reports how sure it is of each pair so that a
human reads the unsure ones instead of trusting them.

Pairs below `REVIEW_BELOW` are returned flagged, never silently accepted.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from scipy.optimize import linear_sum_assignment

from app.models.team import Team
from app.utils.team_names import fold_team_key, normalize_team_name

# Words that say what *kind* of club it is, not which one. "FC Cartagena" and
# "Cartagena" are the same club; "Real", "Sporting" and "United" are kept
# because they distinguish clubs within a city.
GENERIC_TOKENS = frozenset(
    {
        "fc",
        "cf",
        "ud",
        "cd",
        "sd",
        "ad",
        "ac",
        "as",
        "afc",
        "rcd",
        "sc",
        "sv",
        "vfb",
        "vfl",
        "tsg",
        "fsv",
        "fk",
        "ss",
        "ssc",
        "us",
        "usl",
        "calcio",
        "club",
        "de",
        "del",
        "la",
        "1",
        "ca",
        "sk",
        "nk",
    }
)

# Football-Data abbreviations, expanded so they can meet the API's full words.
ABBREVIATIONS = {
    "ath": "athletic",
    "sp": "sporting",
    "man": "manchester",
    "utd": "united",
    "nott": "nottingham",
    "st": "saint",
    "dep": "deportivo",
    "wands": "wanderers",
    "rov": "rovers",
    "inter": "internazionale",
    "ein": "eintracht",
    "m": "monchengladbach",
    "gladbach": "monchengladbach",
    "mgladbach": "monchengladbach",
    "bor": "borussia",
}

# Below this a pair is flagged for a human to read, however the assignment
# came out. Chosen on real La Liga, Serie A and Bundesliga rosters, where
# every correct pair scored above it and the wrong pairs it guarded against
# scored well below.
REVIEW_BELOW = 0.55


def _fold(text: str) -> str:
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9 ]+", " ", stripped.lower().replace("'", "")).strip()


def tokens(name: str) -> list[str]:
    folded = _fold(name)
    out: list[str] = []
    for tok in folded.split():
        tok = ABBREVIATIONS.get(tok, tok)
        if tok not in GENERIC_TOKENS:
            out.append(tok)
    return out or folded.split()


# Two single words count as the same word only if they are nearly identical
# ("Espanyol"/"Espanol" are; "Chiclana"/"China" are not). Character similarity
# alone is far too forgiving: it is what paired a Spanish amateur club with a
# country.
WORD_MATCH_AT = 0.8
# A whole-name string match must clear a higher bar still, for the same reason.
WHOLE_NAME_MATCH_AT = 0.85


def _token_score(a: str, b: str) -> float:
    """How well two single words agree: equal, prefix of the other, or near."""
    if a == b:
        return 1.0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 3 and long_.startswith(short):
        return 0.9
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio if ratio >= WORD_MATCH_AT else 0.0


def similarity(api_name: str, our_name: str) -> float:
    """0..1 — how plausibly two names are the same club.

    The best of two views: the whole name as a string, and the words matched
    one-to-one. The second is what lets "Ath Bilbao" meet "Athletic Club" (the
    abbreviation expands) and "Celta" meet "Celta Vigo" (a missing word costs
    little, a wrong one costs a lot).
    """
    a, b = tokens(api_name), tokens(our_name)
    whole = SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    whole = whole if whole >= WHOLE_NAME_MATCH_AT else 0.0
    if not a or not b:
        return whole
    # Each word of the shorter name finds its best partner in the longer one.
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    matched = sum(max(_token_score(s, t) for t in long_) for s in short) / len(short)
    # Penalise, lightly, the words left over: "Real Madrid" vs "Real Madrid
    # Castilla" are different clubs and the extra word must count for something.
    spare = (len(long_) - len(short)) / len(long_)
    return max(whole, matched * (1 - 0.35 * spare))


class TeamResolver:
    """Finds, or creates, the team row for an API-Football club.

    Order: stored API id, exact name, accent-folded name, then create. There is
    deliberately no fuzzy step — see the module docstring. A club that matches
    nothing is created and recorded in `created`, so a person can read the list
    for missed aliases; guessing here would fuse two clubs' histories.

    Shared by the historical ingest (`scripts/fetch_api_competitions.py`) and
    the live fixture ingest, so a club has one identity whichever way it
    arrives.
    """

    def __init__(self, session) -> None:
        self.session = session
        teams = session.query(Team).filter(Team.sport == "football").all()
        self.by_api_id = {t.api_football_id: t for t in teams if t.api_football_id is not None}
        self.by_name = {t.name: t for t in teams}
        self.by_folded: dict[str, Team] = {}
        for team in teams:
            self.by_folded.setdefault(fold_team_key(team.name), team)
        self.created: list[tuple[str, int | None, str]] = []

    def resolve(self, api_name: str, api_id: int | None, competition: str) -> Team:
        if api_id is not None and api_id in self.by_api_id:
            return self.by_api_id[api_id]

        name = normalize_team_name(api_name)
        team = self.by_name.get(name) or self.by_folded.get(fold_team_key(name))

        # A name match is not proof. If that row already belongs to a *different*
        # API id it is a different club that happens to share the name.
        if team is not None and team.api_football_id not in (None, api_id):
            team = None
            name = f"{name} ({competition})"

        if team is None:
            team = Team(name=name, league=competition, sport="football", api_football_id=api_id)
            self.session.add(team)
            self.session.flush()
            self.created.append((name, api_id, competition))
            self.by_name[name] = team
            self.by_folded.setdefault(fold_team_key(name), team)
        elif team.api_football_id is None and api_id is not None:
            team.api_football_id = api_id  # learn the id for next time
        if api_id is not None:
            self.by_api_id[api_id] = team
        return team


@dataclass(frozen=True)
class ClubMatch:
    api_id: int
    api_name: str
    our_name: str | None
    score: float
    # True when a person should look at this pair before it is trusted.
    needs_review: bool


def assign_clubs(
    api_clubs: list[tuple[int, str]], our_names: list[str], review_below: float = REVIEW_BELOW
) -> list[ClubMatch]:
    """Pair API clubs with our clubs one-to-one, maximising total similarity.

    Surplus API clubs (a club we have no row for) come back with
    `our_name=None` and `needs_review` set: the honest answer to "which of ours
    is this" is sometimes "none of them — it is new".
    """
    if not api_clubs:
        return []
    if not our_names:
        return [ClubMatch(i, n, None, 0.0, True) for i, n in api_clubs]

    cost = [[1.0 - similarity(name, ours) for ours in our_names] for _, name in api_clubs]
    rows, cols = linear_sum_assignment(cost)
    paired = dict(zip(rows.tolist(), cols.tolist(), strict=True))

    results = []
    for index, (api_id, api_name) in enumerate(api_clubs):
        if index not in paired:
            results.append(ClubMatch(api_id, api_name, None, 0.0, True))
            continue
        ours = our_names[paired[index]]
        score = 1.0 - cost[index][paired[index]]
        results.append(ClubMatch(api_id, api_name, ours, round(score, 3), score < review_below))
    return results


def merge_team(session, duplicate: Team, keeper: Team) -> dict:
    """Fold a duplicate team row into the club it duplicates, then delete it.

    A club arrives twice when two sources spell its name differently and nothing
    ties them together: "Flamengo" from the live feed beside "Flamengo RJ" from
    the history. Everything that pointed at the duplicate — matches, rating
    history, injuries — is re-pointed at the keeper, the keeper learns the
    duplicate's API id, and the duplicate row goes.

    Refuses rather than guesses when the two rows carry *different* API ids: that
    is two different clubs that merely resemble each other. If the duplicate had
    any completed matches, its rating history was computed for a club that does
    not exist, so the caller must rebuild Elo afterwards (`needs_elo_rebuild`).
    """
    from app.models.elo_history import EloHistory
    from app.models.injury import Injury
    from app.models.match import Match

    if duplicate.id == keeper.id:
        raise ValueError("cannot merge a team into itself")
    if duplicate.sport != keeper.sport:
        raise ValueError(f"different sports: {duplicate.sport!r} vs {keeper.sport!r}")
    if (
        duplicate.api_football_id is not None
        and keeper.api_football_id is not None
        and duplicate.api_football_id != keeper.api_football_id
    ):
        raise ValueError(
            f"{duplicate.name!r} and {keeper.name!r} have different API ids "
            f"({duplicate.api_football_id} vs {keeper.api_football_id}): different clubs"
        )

    counts = {}
    for column in (Match.home_team_id, Match.away_team_id):
        counts[column.key] = (
            session.query(Match).filter(column == duplicate.id).update({column: keeper.id})
        )
    completed = (
        session.query(Match)
        .filter(
            Match.status == "completed",
            (Match.home_team_id == keeper.id) | (Match.away_team_id == keeper.id),
        )
        .count()
    )
    for column in (EloHistory.team_id, EloHistory.opponent_team_id):
        counts[column.key] = (
            session.query(EloHistory).filter(column == duplicate.id).update({column: keeper.id})
        )
    counts["injuries"] = (
        session.query(Injury)
        .filter(Injury.team_id == duplicate.id)
        .update({Injury.team_id: keeper.id})
    )

    if keeper.api_football_id is None:
        keeper.api_football_id = duplicate.api_football_id
    session.delete(duplicate)
    session.flush()
    counts["needs_elo_rebuild"] = counts["team_id"] > 0 or counts["opponent_team_id"] > 0
    counts["keeper_completed_matches"] = completed
    return counts
