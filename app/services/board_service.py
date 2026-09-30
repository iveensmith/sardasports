"""Assembling one row of the prediction board.

The board is a table, and a table row is a different shape from a prediction.
A prediction is "here are probabilities for every market"; a row is "here is
this fixture, its price, the engine's pick in each column, the one pick worth
leading with, and — once it has been played — whether each of those came in".

That last part is the reason this module exists rather than the frontend
assembling it. Grading has to happen next to the prediction it grades, by one
rule, automatically. A board that shows tips before kick-off and quietly
forgets them afterwards is a different and much less honest product than one
that shows yesterday's card with every pick marked won or lost.

Readable URLs are built here too: `/match/spain-vs-croatia-prediction-144414`
rather than `/match/144414`. The numeric id stays on the end because team
names are not unique over time — two clubs rename, two fixtures repeat — and
resolving by id is exact while the slug is for the reader and for search.
"""

from __future__ import annotations

import re
import unicodedata

from app.services.settlement import MatchResult, Outcome, settle_key
from ml.competition_catalogue import meta_for
from ml.markets import (
    BTTS,
    GOALS,
    MATCH_RESULT,
    RankedCall,
    best_per_market,
    candidate_calls,
    headline_call,
    rank_calls,
)
from ml.team_badges import badge_dict

# Which markets get their own column on the board, in reading order. Corners,
# cards and half-time goals are priced by the engine but left to the fixture
# page: a row has room for three columns and a best tip, and these are the
# three a reader scans for.
BOARD_COLUMNS = (MATCH_RESULT, GOALS, BTTS)

# How a market's selection maps into the `odds_markets` blob the odds fetcher
# stores. Markets absent here are ones no bookmaker line was ingested for, so
# their calls are shown without a price rather than with a fabricated one.
_ODDS_GROUP = {MATCH_RESULT: "match_winner", GOALS: "goals", BTTS: "btts"}
_ODDS_SELECTION = {
    f"{MATCH_RESULT}:home": "home",
    f"{MATCH_RESULT}:draw": "draw",
    f"{MATCH_RESULT}:away": "away",
}


def slugify(value: str) -> str:
    """ "Bayern München" -> "bayern-munchen".

    Accents are folded rather than stripped, so "Türkiye" becomes "turkiye"
    and not "trkiye". Everything else non-alphanumeric collapses to a single
    hyphen.
    """
    folded = unicodedata.normalize("NFKD", value)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_only.lower())).strip("-")


def match_slug(home_team: str, away_team: str, match_id: int) -> str:
    """The readable part of a fixture URL, id included for exact resolution."""
    return f"{slugify(home_team)}-vs-{slugify(away_team)}-prediction-{match_id}"


def match_id_from_slug(slug: str) -> int | None:
    """Recover the id from a slug, ignoring whatever the name part says.

    The name is decoration: a team renamed since the URL was shared still
    resolves, and a hand-edited slug cannot land on the wrong fixture.
    """
    found = re.search(r"(\d+)$", slug or "")
    return int(found.group(1)) if found else None


def odds_for(market: str, selection: str, odds_markets: dict | None) -> float | None:
    """The best offered price for a selection, or None if it was not quoted."""
    if not odds_markets:
        return None
    group = _ODDS_GROUP.get(market)
    if group is None:
        return None
    prices = odds_markets.get(group) or {}
    key = _ODDS_SELECTION.get(f"{market}:{selection}", selection)
    price = prices.get(key)
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    return price if price > 1.0 else None


def _tip(entry: RankedCall, odds_markets: dict | None, result: MatchResult | None) -> dict:
    """One market's cell: what the engine picked, at what price, and how it went."""
    call = entry.call
    outcome = settle_key(call.key, result) if result is not None else None
    return {
        "market": call.market,
        "selection": call.selection,
        "label": call.label,
        "short_label": call.short_label,
        "probability": round(call.probability, 1),
        "base_rate": entry.base_rate,
        "lift": None if entry.lift is None else round(entry.lift, 1),
        "notable": entry.notable,
        "odds": odds_for(call.market, call.selection, odds_markets),
        # None before kick-off, "won"/"lost"/"void" afterwards. Absent rather
        # than a default, so an ungraded row can never render as a loss.
        "outcome": outcome.value if outcome is not None else None,
    }


def match_odds(odds_markets: dict | None) -> dict:
    """The 1 / X / 2 prices, which get their own three columns."""
    winner = (odds_markets or {}).get("match_winner") or {}

    def price(key):
        try:
            value = float(winner.get(key))
        except (TypeError, ValueError):
            return None
        return value if value > 1.0 else None

    return {"home": price("home"), "draw": price("draw"), "away": price("away")}


def confidence_out_of_ten(confidence: float | None) -> float | None:
    """The engine scores confidence 0-100; the board shows it out of ten.

    One decimal place, because "8.0" and "7.5" are meaningfully different to
    a reader scanning a column and "80" and "75" are not obviously on the
    same scale as the probabilities beside them.
    """
    if confidence is None:
        return None
    return round(confidence / 10.0, 1)


def build_row(
    match,
    prediction: dict | None,
    base_rates: dict[str, float],
    home_team: str,
    away_team: str,
) -> dict:
    """One board row: fixture, prices, a pick per column, the best tip, and grades."""
    meta = meta_for(match.competition)
    result = None
    if match.home_score is not None and match.away_score is not None:
        from app.services.settlement import result_from_match

        result = result_from_match(match)

    ranked = rank_calls(candidate_calls(prediction), base_rates) if prediction else []
    by_market = {entry.call.market: entry for entry in best_per_market(ranked)}
    best = headline_call(ranked)

    return {
        "match_id": match.id,
        "slug": match_slug(home_team, away_team, match.id),
        "match_date": match.match_date.isoformat(),
        "status": match.status,
        "sport": match.sport,
        "competition": {
            "name": match.competition,
            "short_name": meta.short_name if meta else match.competition,
            "country": meta.country if meta else None,
            "country_code": meta.country_code if meta else None,
            "tier": meta.tier if meta else None,
        },
        "home_team": home_team,
        "away_team": away_team,
        # What to render beside each name: a flag for a national side, a
        # monogram for anything we have no licensed crest for.
        "home_badge": badge_dict(home_team),
        "away_badge": badge_dict(away_team),
        # None until played, rather than 0-0, which is a real scoreline.
        "score": (
            {"home": match.home_score, "away": match.away_score} if result is not None else None
        ),
        "odds": match_odds(match.odds_markets),
        # One cell per board column, absent when the engine could not price
        # that market for this competition.
        "tips": {
            market: _tip(by_market[market], match.odds_markets, result)
            for market in BOARD_COLUMNS
            if market in by_market
        },
        "best_tip": _tip(best, match.odds_markets, result) if best else None,
        "confidence": confidence_out_of_ten(prediction.get("confidence") if prediction else None),
        "confidence_label": (prediction or {}).get("confidence_label"),
    }


def row_outcome(row: dict) -> str | None:
    """How the row's headline tip went — what a graded board colours on."""
    best = row.get("best_tip")
    return best.get("outcome") if best else None


def is_won(row: dict) -> bool:
    return row_outcome(row) == Outcome.WON.value
