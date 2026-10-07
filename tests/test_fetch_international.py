"""The national-team loader must read the 90-minute score.

Its first version read the API's headline `goals`, which includes extra time,
so a tie decided after 120 minutes was stored with a winner it did not have at
90. The fixtures below are real World Cup 2022 matches.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.fetch_international import ninety_minute_score, rows_from_items

SAMPLE = json.loads(
    (Path(__file__).parent / "data" / "api_football_sample.json").read_text(encoding="utf-8")
)["wc"]


def _by_round(round_name):
    return next(i for i in SAMPLE if i["league"]["round"] == round_name)


def test_the_2022_final_is_two_all_at_90_minutes_not_three_all():
    final = _by_round("Final")
    assert (final["goals"]["home"], final["goals"]["away"]) == (3, 3)
    assert ninety_minute_score(final) == (2, 2)


def test_a_quarter_final_that_went_to_penalties_is_goalless_at_90_minutes():
    tie = _by_round("Quarter-finals")  # Croatia v Brazil
    assert (tie["goals"]["home"], tie["goals"]["away"]) == (1, 1)
    assert ninety_minute_score(tie) == (0, 0)


def test_an_ordinary_result_is_unchanged():
    group = _by_round("Group Stage - 1")
    assert ninety_minute_score(group) == (group["goals"]["home"], group["goals"]["away"])


def test_goals_are_only_a_fallback_for_a_payload_with_no_fulltime():
    assert ninety_minute_score({"goals": {"home": 4, "away": 1}, "score": {}}) == (4, 1)
    assert ninety_minute_score({"goals": {"home": 4, "away": 1}}) == (4, 1)


def test_rows_carry_the_90_minute_score():
    rows = rows_from_items([_by_round("Final")])
    assert len(rows) == 1
    assert (rows[0]["FTHG"], rows[0]["FTAG"]) == (2, 2)
