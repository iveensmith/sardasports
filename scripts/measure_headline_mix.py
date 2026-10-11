"""Measure the best-tip mix and hit rate for different corner/card bars.

Reads every graded stored prediction (calibrated at read time, as a visitor sees it), ranks
the calls against the fixture's own competition rates, and reports for each pair of bars how
the headline splits across markets and how often each market's headline came in.

    python scripts/measure_headline_mix.py
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import joinedload  # noqa: E402

from app.database.session import SessionLocal  # noqa: E402
from app.models.match import Match  # noqa: E402
from app.models.prediction import Prediction  # noqa: E402
from app.services.base_rates import competition_base_rates  # noqa: E402
from app.services.settlement import Outcome, result_from_match, settle_key  # noqa: E402
from app.services.stored_predictions import payload_from_stored  # noqa: E402
from ml.markets import candidate_calls, headline_call, rank_calls  # noqa: E402

BARS = [(10.0, 8.0), (7.5, 5.0), (6.0, 5.0), (5.0, 5.0), (7.5, 8.0)]


def main() -> None:
    with SessionLocal() as session:
        rows = (
            session.query(Prediction, Match)
            .join(Match, Match.id == Prediction.match_id)
            .options(joinedload(Match.home_team), joinedload(Match.away_team))
            .filter(Match.status == "completed", Match.home_score.is_not(None))
            .all()
        )
        prepared = []
        for prediction, match in rows:
            result = result_from_match(match)
            if result is None:
                continue
            ranked = rank_calls(
                candidate_calls(payload_from_stored(prediction)),
                competition_base_rates(session, match.competition),
            )
            prepared.append((ranked, result))

    print(f"{len(prepared)} graded predictions")
    for corners, cards in BARS:
        # Corners and cards no longer lead at all; this script predates that rule and is
        # kept for the claim-floor tables in the roadmap.
        mix: Counter = Counter()
        wins: dict = defaultdict(int)
        for ranked, result in prepared:
            best = headline_call(ranked)
            if best is None:
                continue
            mix[best.call.market] += 1
            outcome = settle_key(best.call.key, result)
            wins[best.call.market] += outcome == Outcome.WON
        total = sum(mix.values())
        print(f"\ncorners bar {corners}, cards bar {cards}")
        for market, count in mix.most_common():
            share, hit = 100 * count / total, 100 * wins[market] / count
            print(f"  {market:<14}{count:>6} {share:5.1f}%  hit {hit:5.1f}%")


if __name__ == "__main__":
    main()
