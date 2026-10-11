"""Basketball and tennis markets: attach what happened, and count how often the call was right.

The markets themselves are priced by `ml.basketball_markets` and `ml.tennis_markets` and stored
in the prediction's payload. Once a match is over, `attach_results` adds what each one actually
settled as (from the per-period scores kept on the match), so a board can mark every line won
or lost. `market_picks` reduces each market to the single call the engine would back, which is
what the record counts.

A market that cannot be graded (the match has no period detail, or the source recorded a
tennis match without set scores) simply has no result: it is never shown as lost.
"""

from __future__ import annotations

from ml import basketball_markets, tennis_markets


def _grade(sport: str, match, market: dict) -> dict | None:
    periods = match.period_scores
    if match.home_score is None or match.away_score is None:
        return None
    if sport == "basketball":
        return basketball_markets.grade_market(
            market, periods, (match.home_score, match.away_score)
        )
    if sport == "tennis":
        sets = (periods or {}).get("sets") if periods else None
        return tennis_markets.grade_market(market, sets, match.home_score, match.away_score)
    return None


def attach_results(sport: str, match, markets: list[dict] | None) -> list[dict]:
    """The markets, each with a `result` when the match is over and it can be graded."""
    out = []
    for market in markets or []:
        item = dict(market)
        if match.status == "completed":
            result = _grade(sport, match, market)
            if result is not None:
                item["result"] = result
        out.append(item)
    return out


def _nearest_even(lines: list[dict], key: str) -> tuple[int, dict]:
    index = min(range(len(lines)), key=lambda i: abs(lines[i][key] - 50.0))
    return index, lines[index]


def market_pick(market: dict) -> dict | None:
    """The one call the engine would back on this market, with its probability.

    For a market with several lines it is the line nearest a coin flip (the line a bettor is
    actually choosing on); the easy tail lines would otherwise flatter the record.
    Returns {"side": ..., "probability": ..., "line_index": int | None} or None.
    """
    kind = market.get("type")
    if kind == "over_under" and market.get("lines"):
        i, line = _nearest_even(market["lines"], "prob_over")
        over = line["prob_over"] >= 50.0
        return {
            "side": "over" if over else "under",
            "probability": line["prob_over"] if over else line["prob_under"],
            "line_index": i,
        }
    if kind == "handicap" and market.get("lines"):
        i, line = _nearest_even(market["lines"], "prob_home")
        home = line["prob_home"] >= 50.0
        return {
            "side": "home" if home else "away",
            "probability": line["prob_home"] if home else line["prob_away"],
            "line_index": i,
        }
    if kind in ("three_way", "two_way"):
        home, away = market.get("home"), market.get("away")
        if home is None or away is None:
            return None
        side = "home" if home >= away else "away"
        return {"side": side, "probability": max(home, away), "line_index": None}
    if kind == "yes_no":
        yes = market.get("yes")
        if yes is None:
            return None
        return {
            "side": "yes" if yes >= 50.0 else "no",
            "probability": yes if yes >= 50.0 else market.get("no"),
            "line_index": None,
        }
    if kind == "correct_score" and market.get("scores"):
        top = max(range(len(market["scores"])), key=lambda i: market["scores"][i]["prob"])
        return {
            "side": market["scores"][top]["score"],
            "probability": market["scores"][top]["prob"],
            "line_index": top,
        }
    return None


def pick_correct(market: dict, pick: dict) -> bool | None:
    """Whether `pick` was right, from the market's attached `result`. None if it can't tell."""
    result = market.get("result")
    if not result:
        return None
    kind = market.get("type")
    i = pick.get("line_index")
    if kind in ("over_under", "handicap"):
        outcomes = result.get("lines") or []
        if i is None or i >= len(outcomes):
            return None
        return outcomes[i] == pick["side"]
    if kind in ("three_way", "two_way", "yes_no"):
        outcome = result.get("result")
        if outcome == "tie":
            return None  # a drawn period settles a two-way call as void
        return outcome == pick["side"]
    if kind == "correct_score":
        scores = result.get("scores") or []
        if i is None or i >= len(scores):
            return None
        return bool(scores[i])
    return None


def markets_record(rows: list[tuple[bool, str, object, list[dict]]]) -> dict:
    """Per-market accuracy over graded predictions.

    `rows` is (live, sport, match, markets). Returns
    ``{market_id: {"name", "group", "live": {...}, "reconstructed": {...}}}`` where each side
    is ``{"settled", "won"}``, ordered by how many were settled.
    """
    table: dict[str, dict] = {}
    for live, sport, match, markets in rows:
        for market in attach_results(sport, match, markets):
            pick = market_pick(market)
            if pick is None:
                continue
            correct = pick_correct(market, pick)
            if correct is None:
                continue
            entry = table.setdefault(
                market["id"],
                {
                    "name": market.get("name"),
                    "group": market.get("group"),
                    "live": {"settled": 0, "won": 0},
                    "reconstructed": {"settled": 0, "won": 0},
                },
            )
            side = entry["live" if live else "reconstructed"]
            side["settled"] += 1
            side["won"] += 1 if correct else 0
    return dict(
        sorted(
            table.items(),
            key=lambda kv: -(kv[1]["live"]["settled"] + kv[1]["reconstructed"]["settled"]),
        )
    )
