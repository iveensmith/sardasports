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

from app.services.confidence_scale import rank_out_of_ten
from app.services.settlement import MatchResult, Outcome, settle_key
from ml.competition_catalogue import meta_for
from ml.markets import (
    BTTS,
    DOUBLE_CHANCE,
    GOALS,
    MATCH_RESULT,
    RankedCall,
    best_per_market,
    candidate_calls,
    headline_call,
    is_strong_tip,
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
# Double chance is handled separately in `odds_for` — see `_double_chance_price`.
_ODDS_GROUP = {MATCH_RESULT: "match_winner", GOALS: "goals", BTTS: "btts"}
_ODDS_SELECTION = {
    f"{MATCH_RESULT}:home": "home",
    f"{MATCH_RESULT}:draw": "draw",
    f"{MATCH_RESULT}:away": "away",
}

# Double chance -> the pair of 1X2 legs it covers.
_DOUBLE_CHANCE_LEGS = {
    "home_draw": ("home", "draw"),
    "away_draw": ("away", "draw"),
    "home_away": ("home", "away"),
}


def _double_chance_price(selection: str, odds_markets: dict) -> float | None:
    """A double-chance price, derived from the 1X2 prices already ingested.

    No bookmaker double-chance line is fetched — only 1X2, goals and BTTS
    are (see `fetch_odds.py`). But "1X" is exactly "not 2", so its fair price
    is computable from the same two prices behind the 1X2 columns: convert
    each leg to an implied probability, sum them, invert. This is the same
    reasoning `candidate_calls` already applies to the *probability* side
    ("introduces no new estimate and cannot disagree with the match-result
    call") — applied to price instead, using real quoted prices, not an
    invented number.
    """
    legs = _DOUBLE_CHANCE_LEGS.get(selection)
    if legs is None:
        return None
    winner = (odds_markets or {}).get("match_winner") or {}
    try:
        a = float(winner[legs[0]])
        b = float(winner[legs[1]])
    except (TypeError, ValueError, KeyError):
        return None
    if a <= 1.0 or b <= 1.0:
        return None
    implied = 1.0 / a + 1.0 / b
    return round(1.0 / implied, 2) if implied > 0 else None


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
    if market == DOUBLE_CHANCE:
        return _double_chance_price(selection, odds_markets)
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


def _tip(
    entry: RankedCall,
    odds_markets: dict | None,
    result: MatchResult | None,
    *,
    fair_price_fallback: bool = False,
) -> dict:
    """One market's cell: what the engine picked, at what price, and how it went.

    `fair_price_fallback` is used for every cell on the board (see `build_row`):
    when no bookmaker price exists for a pick — a fixture no bookmaker priced,
    or a line the fetcher didn't store — a bare dash reads as "no pick", when
    the engine has in fact made one and quantified it. The fallback is the
    pick's own fair price (100 / probability): computed, not invented, from a
    number already on the row, and flagged as an estimate rather than a market
    price with `odds_is_estimated` so the two are never read as the same thing.
    """
    call = entry.call
    outcome = settle_key(call.key, result) if result is not None else None
    odds = odds_for(call.market, call.selection, odds_markets)
    odds_is_estimated = False
    if odds is None and fair_price_fallback and call.probability > 0:
        odds = round(100.0 / call.probability, 2)
        odds_is_estimated = True
    return {
        "market": call.market,
        "selection": call.selection,
        "label": call.label,
        "short_label": call.short_label,
        "probability": round(call.probability, 1),
        "base_rate": entry.base_rate,
        "lift": None if entry.lift is None else round(entry.lift, 1),
        "notable": entry.notable,
        "strong": is_strong_tip(call.probability),
        "odds": odds,
        "odds_is_estimated": odds_is_estimated,
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


def effective_odds_markets(match) -> dict | None:
    """The match's stored bookmaker prices, with the legacy 1X2 columns folded in.

    Older rows (the Football-Data CSV load) carry their 1X2 prices only in
    `odds_home_win / odds_draw / odds_away_win`, not in the `odds_markets`
    blob the live fetcher writes. They are real quoted prices, so they are
    used as the 1X2 line when the blob has none. Returns a new dict; the
    stored blob is never modified.
    """
    markets = dict(match.odds_markets or {})
    if not markets.get("match_winner"):
        legacy = {
            "home": getattr(match, "odds_home_win", None),
            "draw": getattr(match, "odds_draw", None),
            "away": getattr(match, "odds_away_win", None),
        }
        if any(value is not None for value in legacy.values()):
            markets["match_winner"] = {k: v for k, v in legacy.items() if v is not None}
    return markets or None


# The prediction's own key for each 1X2 selection (see ml.markets.candidate_calls).
_PREDICTION_KEYS = {"home": "home_win", "draw": "draw", "away": "away_win"}


def match_odds_filled(odds_markets: dict | None, prediction: dict | None) -> tuple[dict, dict]:
    """The 1 / X / 2 prices with no gaps, and which of them are estimates.

    A quoted bookmaker price always wins. Where none was quoted, the
    selection's fair price (100 / the engine's probability for it) is used and
    flagged, so the board shows a number in every cell without presenting a
    model figure as a bookmaker's. Selections the engine gave no probability
    for stay empty — there is nothing to compute a price from.
    """
    quoted = match_odds(odds_markets)
    filled: dict = {}
    estimated: dict = {}
    for selection, price in quoted.items():
        probability = _as_number((prediction or {}).get(_PREDICTION_KEYS[selection]))
        if price is None and probability is not None and probability > 0:
            filled[selection] = round(100.0 / probability, 2)
            estimated[selection] = True
        else:
            filled[selection] = price
            estimated[selection] = False
    return filled, estimated


def _as_number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def confidence_out_of_ten(confidence: float | None) -> float | None:
    """The engine scores confidence 0-100; the board shows it out of ten.

    One decimal place, because "8.0" and "7.5" are meaningfully different to
    a reader scanning a column and "80" and "75" are not obviously on the
    same scale as the probabilities beside them.
    """
    if confidence is None:
        return None
    return round(confidence / 10.0, 1)


def _board_confidence(confidence: float | None) -> float | None:
    """The score the board shows: a rank among past fixtures where there are enough to rank
    against (see `confidence_scale`), otherwise the raw score over ten."""
    ranked = rank_out_of_ten(confidence)
    return ranked if ranked is not None else confidence_out_of_ten(confidence)


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
    odds_markets = effective_odds_markets(match)
    odds, odds_estimated = match_odds_filled(odds_markets, prediction)

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
        # Quoted prices where a bookmaker gave one, the engine's fair price
        # otherwise; `odds_estimated` says which, per selection.
        "odds": odds,
        "odds_estimated": odds_estimated,
        # One cell per board column, absent when the engine could not price
        # that market for this competition.
        "tips": {
            market: _tip(by_market[market], odds_markets, result, fair_price_fallback=True)
            for market in BOARD_COLUMNS
            if market in by_market
        },
        "best_tip": (_tip(best, odds_markets, result, fair_price_fallback=True) if best else None),
        "confidence": _board_confidence(prediction.get("confidence") if prediction else None),
        "confidence_label": (prediction or {}).get("confidence_label"),
    }


def row_outcome(row: dict) -> str | None:
    """How the row's headline tip went — what a graded board colours on."""
    best = row.get("best_tip")
    return best.get("outcome") if best else None


def is_won(row: dict) -> bool:
    return row_outcome(row) == Outcome.WON.value
