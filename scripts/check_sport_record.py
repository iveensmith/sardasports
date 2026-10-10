"""A health report for the basketball and tennis predictions stored in advance.

Run it every few days while the record is young:

    python scripts/check_sport_record.py

For each sport it prints how many predictions were stored before the match and how they did
(with a 95% interval, because 27 results say very little and the report should say so),
whether the winner probabilities were calibrated (when the engine said 70%, did the side win
about 70% of the time?), how much of what is being played is priced at all and which leagues
are not, and what looks wrong: matches stuck as scheduled long after their start, and a feed
that has stopped bringing results in.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from app.database.session import SessionLocal
from app.models import Match, SportPrediction
from app.services.sport_predictions import SPORTS, _grade


def wilson(won: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = won / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def main() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    db = SessionLocal()
    try:
        for sport in SPORTS:
            print(f"\n=== {sport} ===")
            rows = (
                db.query(SportPrediction, Match)
                .join(Match, Match.id == SportPrediction.match_id)
                .filter(SportPrediction.sport == sport)
                .all()
            )
            live = [(p, m) for p, m in rows if p.created_at < m.match_date]
            done = [(p, m) for p, m in live if m.status == "completed"]
            print(f"stored in advance: {len(live)}, finished and graded: {len(done)}")

            winner = total = won_w = won_t = 0
            buckets: dict[int, list[int]] = {}
            for p, m in done:
                graded_w, graded_t = _grade(
                    m, p.home_win_pct, p.away_win_pct, p.total_line, p.prob_over_pct
                )
                if graded_w is not None:
                    winner += 1
                    won_w += int(graded_w)
                    confidence = max(p.home_win_pct, p.away_win_pct)
                    buckets.setdefault(int(confidence // 10) * 10, []).append(int(graded_w))
                if graded_t is not None:
                    total += 1
                    won_t += int(graded_t)
            for label, won, n in (("winner", won_w, winner), ("total", won_t, total)):
                low, high = wilson(won, n)
                rate = "n/a" if n == 0 else f"{100 * won / n:.1f}%"
                print(
                    f"  {label}: {won}/{n} ({rate}); 95% interval {100*low:.0f}% to {100*high:.0f}%"
                )
            if buckets:
                print("  calibration (the side the engine backed, by how sure it was):")
                for low in sorted(buckets):
                    hits = buckets[low]
                    print(
                        f"    said {low}-{low + 9}%: right {sum(hits)}/{len(hits)}"
                        f" ({100 * sum(hits) / len(hits):.0f}%)"
                    )

            # What is being played, and how much of it is priced.
            since = now - timedelta(days=2)
            played = (
                db.query(Match.competition, Match.id)
                .filter(Match.sport == sport, Match.match_date >= since, Match.match_date <= now)
                .all()
            )
            priced_ids = {
                r[0]
                for r in db.query(SportPrediction.match_id).filter(
                    SportPrediction.match_id.in_([i for _, i in played] or [0])
                )
            }
            by_league: dict[str, list[int]] = {}
            for competition, match_id in played:
                row = by_league.setdefault(competition, [0, 0])
                row[0] += 1
                row[1] += match_id in priced_ids
            unpriced = sorted(
                ((c, v[0] - v[1]) for c, v in by_league.items() if v[0] > v[1]),
                key=lambda kv: -kv[1],
            )
            total_played = sum(v[0] for v in by_league.values())
            total_priced = sum(v[1] for v in by_league.values())
            print(f"  played in the last 2 days: {total_played}, of which priced: {total_priced}")
            if unpriced:
                print("  most unpriced (no pick: too little history):")
                for competition, count in unpriced[:8]:
                    print(f"    {competition}: {count}")

            # Things that look wrong.
            stuck = (
                db.query(Match)
                .filter(
                    Match.sport == sport,
                    Match.status == "scheduled",
                    Match.match_date < now - timedelta(hours=12),
                )
                .count()
            )
            newest = (
                db.query(Match.match_date)
                .filter(Match.sport == sport, Match.status == "completed")
                .order_by(Match.match_date.desc())
                .first()
            )
            print(f"  stuck as scheduled over 12 hours after the start: {stuck}")
            if newest:
                hours = (now - newest[0]).total_seconds() / 3600
                flag = "  <-- feed may have stopped" if hours > 36 else ""
                print(
                    f"  newest finished match: {newest[0]:%d %b %H:%M} UTC "
                    f"({hours:.0f} h ago){flag}"
                )
    finally:
        db.close()


if __name__ == "__main__":
    main()
