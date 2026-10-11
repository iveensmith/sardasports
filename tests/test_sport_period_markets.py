"""Basketball period markets and tennis set markets: pricing, consistency and grading.

The properties that matter, and that a regression would break quietly:
* every line ends in .5, so nothing can push;
* a market agrees with the number it was derived from (the tennis set scores sum to the match
  win probability, the basketball period winners follow the moneyline);
* a game recorded in halves is never offered a quarter;
* grading uses what was actually recorded, and an ungradable market has no result rather than
  a loss.
"""

from __future__ import annotations

import pytest

import ml.basketball_markets as bm
import ml.tennis_markets as tm
from app.services.sport_markets import attach_results, market_pick, markets_record, pick_correct
from ml.period_scores import basketball_periods, flip_tennis, tennis_sets

# ---------------------------------------------------------------- parsing


def test_quarters_are_read_and_overtime_is_kept_apart():
    scores = {
        "home": {
            "quarter_1": 20,
            "quarter_2": 25,
            "quarter_3": 22,
            "quarter_4": 30,
            "over_time": 8,
        },
        "away": {
            "quarter_1": 22,
            "quarter_2": 23,
            "quarter_3": 25,
            "quarter_4": 30,
            "over_time": 6,
        },
    }
    assert basketball_periods(scores) == {
        "home": [20, 25, 22, 30],
        "away": [22, 23, 25, 30],
        "ot": [8, 6],
    }


def test_a_game_with_any_quarter_missing_has_no_period_detail():
    scores = {
        "home": {"quarter_1": 20, "quarter_2": None, "quarter_3": 22, "quarter_4": 30},
        "away": {"quarter_1": 22, "quarter_2": 23, "quarter_3": 25, "quarter_4": 30},
    }
    assert basketball_periods(scores) is None


def test_tennis_sets_flip_to_the_other_slots_point_of_view():
    periods = tennis_sets([(6, 4), (3, 6), (7, 6)])
    assert periods == {"sets": [[6, 4], [3, 6], [7, 6]]}
    assert flip_tennis(periods) == {"sets": [[4, 6], [6, 3], [6, 7]]}


# ---------------------------------------------------------------- basketball

GAMES = [
    ("NBA", 116.2, 111.4, 0.64),
    ("Euroleague", 82.5, 79.0, 0.58),
    ("NCAA", 74.0, 69.5, 0.60),
    ("CBA", 104.0, 99.0, 0.45),
    ("Some Unlisted League", 80.0, 78.0, 0.5),
]


@pytest.mark.parametrize("competition, home, away, p", GAMES)
def test_every_basketball_line_ends_in_a_half_point(competition, home, away, p):
    markets = bm.price_game(home, away, p, competition)
    assert markets
    for market in markets:
        for line in market.get("lines", []):
            assert (line["line"] * 2) % 2 == 1, (market["id"], line["line"])


@pytest.mark.parametrize("competition, home, away, p", GAMES)
def test_basketball_probabilities_are_proper(competition, home, away, p):
    for market in bm.price_game(home, away, p, competition):
        for line in market.get("lines", []):
            if "prob_over" in line:
                assert line["prob_over"] + line["prob_under"] == pytest.approx(100.0, abs=0.11)
            if "prob_home" in line:
                assert line["prob_home"] + line["prob_away"] == pytest.approx(100.0, abs=0.11)
        if market["type"] == "three_way":
            assert market["home"] + market["tie"] + market["away"] == pytest.approx(100.0, abs=0.2)


def test_an_over_line_gets_less_likely_as_the_line_rises():
    for market in bm.price_game(116.2, 111.4, 0.64, "NBA"):
        if market["type"] == "over_under":
            overs = [line["prob_over"] for line in market["lines"]]
            assert overs == sorted(overs, reverse=True), market["id"]


def test_a_game_recorded_in_halves_is_priced_for_halves_only():
    ids = {m["id"] for m in bm.price_game(74.0, 69.5, 0.6, "NCAA")}
    assert {"h1_total", "h2_total", "h1_winner", "h2_winner"} <= ids
    assert not any(i.startswith("q") for i in ids)


def test_a_quarter_league_gets_quarters_and_halves():
    ids = {m["id"] for m in bm.price_game(82.5, 79.0, 0.58, "Euroleague")}
    assert {"q1_total", "q2_total", "q3_total", "q4_total", "h1_total", "h2_total"} <= ids
    assert {"team_total_home", "team_total_away", "spread"} <= ids


def test_the_quarters_add_up_to_the_game():
    markets = {m["id"]: m for m in bm.price_game(116.2, 111.4, 0.64, "NBA")}
    quarters = sum(markets[f"q{i}_total"]["expected"] for i in range(1, 5))
    halves = markets["h1_total"]["expected"] + markets["h2_total"]["expected"]
    assert quarters == pytest.approx(halves, abs=0.5)


def test_a_favourite_is_favoured_in_each_period_and_the_spread_follows_the_moneyline():
    markets = {m["id"]: m for m in bm.price_game(116.2, 111.4, 0.75, "NBA")}
    assert markets["q1_winner"]["home"] > markets["q1_winner"]["away"]
    assert markets["h1_winner"]["home"] > markets["h1_winner"]["away"]
    even = {m["id"]: m for m in bm.price_game(116.2, 111.4, 0.5, "NBA")}
    assert even["q1_winner"]["home"] == pytest.approx(even["q1_winner"]["away"], abs=0.2)
    # the middle spread line is close to a coin flip, as a fair handicap should be
    middle = even["spread"]["lines"][1]
    assert 35.0 <= middle["prob_home"] <= 65.0


def test_nothing_is_priced_without_a_profile(monkeypatch):
    monkeypatch.setattr(bm, "load_profiles", lambda: {})
    assert bm.price_game(116.2, 111.4, 0.64, "NBA") == []


PERIODS = {"home": [30, 28, 25, 31], "away": [27, 30, 29, 20], "ot": None}


def test_basketball_grading_uses_the_recorded_quarters():
    markets = {m["id"]: m for m in bm.price_game(116.2, 111.4, 0.64, "NBA")}
    final = (114, 106)
    q1 = bm.grade_market(markets["q1_total"], PERIODS, final)
    assert q1["actual"] == 57
    assert all(r in ("over", "under") for r in q1["lines"])
    assert bm.grade_market(markets["q1_winner"], PERIODS, final)["result"] == "home"
    assert bm.grade_market(markets["q2_winner"], PERIODS, final)["result"] == "away"
    assert bm.grade_market(markets["h1_total"], PERIODS, final)["actual"] == 115
    assert bm.grade_market(markets["spread"], PERIODS, final)["actual"] == 8
    assert bm.grade_market(markets["team_total_home"], PERIODS, final)["actual"] == 114


def test_overtime_counts_in_team_totals_and_the_spread_but_not_in_quarters():
    periods = {"home": [25, 25, 25, 25], "away": [25, 25, 25, 25], "ot": [10, 12]}
    markets = {m["id"]: m for m in bm.price_game(116.2, 111.4, 0.64, "NBA")}
    final = (110, 112)
    assert bm.grade_market(markets["team_total_away"], periods, final)["actual"] == 112
    assert bm.grade_market(markets["spread"], periods, final)["actual"] == -2
    assert bm.grade_market(markets["q4_winner"], periods, final)["result"] == "tie"
    assert bm.grade_market(markets["h2_total"], periods, final)["actual"] == 100


def test_a_halves_game_is_graded_from_its_two_recorded_slots():
    periods = {"home": [0, 38, 0, 40], "away": [0, 30, 0, 41], "ot": None}
    markets = {m["id"]: m for m in bm.price_game(74.0, 69.5, 0.6, "NCAA")}
    assert bm.grade_market(markets["h1_total"], periods, (78, 71))["actual"] == 68
    assert bm.grade_market(markets["h2_winner"], periods, (78, 71))["result"] == "away"


def test_a_market_that_cannot_be_graded_has_no_result_not_a_loss():
    markets = {m["id"]: m for m in bm.price_game(116.2, 111.4, 0.64, "NBA")}
    assert bm.grade_market(markets["q1_total"], None, (114, 106)) is None


# ---------------------------------------------------------------- tennis


@pytest.mark.parametrize("best_of", [3, 5])
@pytest.mark.parametrize("p", [0.52, 0.65, 0.8, 0.35, 0.2])
def test_set_scores_sum_to_one_and_the_home_total_is_the_match_win_probability(best_of, p):
    dist = tm.set_score_distribution(p, best_of)
    needed = best_of // 2 + 1
    assert sum(dist.values()) == pytest.approx(1.0)
    home_wins = sum(v for (h, a), v in dist.items() if h == needed)
    assert home_wins == pytest.approx(p)


def test_the_set_distribution_mirrors_when_the_slots_swap():
    a = tm.set_score_distribution(0.7, 3)
    b = tm.set_score_distribution(0.3, 3)
    for (h, aw), v in a.items():
        assert b[(aw, h)] == pytest.approx(v)


@pytest.mark.parametrize("best_of", [3, 5])
def test_tennis_lines_end_in_a_half_point_and_probabilities_are_proper(best_of):
    for market in tm.price_match(0.64, best_of, "Hard", "ATP"):
        for line in market.get("lines", []):
            assert (line["line"] * 2) % 2 == 1, (market["id"], line["line"])
            if "prob_over" in line:
                assert line["prob_over"] + line["prob_under"] == pytest.approx(100.0, abs=0.11)
            if "prob_home" in line:
                assert line["prob_home"] + line["prob_away"] == pytest.approx(100.0, abs=0.11)
        if market["type"] == "correct_score":
            assert sum(s["prob"] for s in market["scores"]) == pytest.approx(100.0, abs=0.3)


def test_the_formats_get_their_own_markets():
    best_of_3 = {m["id"] for m in tm.price_match(0.6, 3, "Clay", "WTA")}
    best_of_5 = tm.price_match(0.6, 5, "Hard", "ATP")
    assert {"set_score", "total_sets", "set_handicap", "first_set_winner", "tiebreak"} <= best_of_3
    scores = next(m for m in best_of_5 if m["id"] == "set_score")["scores"]
    assert len(scores) == 6
    assert (
        len(next(m for m in tm.price_match(0.6, 3, None, None) if m["id"] == "set_score")["scores"])
        == 4
    )


def test_an_unknown_format_is_not_priced():
    assert tm.price_match(0.6, None, "Hard", "ATP") == []


SETS = [[6, 4], [3, 6], [7, 6]]


def test_tennis_grading_uses_the_sets_that_were_played():
    markets = {m["id"]: m for m in tm.price_match(0.6, 3, "Hard", "ATP")}
    assert tm.grade_market(markets["set_score"], SETS, 2, 1)["actual"] == "2-1"
    assert sum(tm.grade_market(markets["set_score"], SETS, 2, 1)["scores"]) == 1
    assert tm.grade_market(markets["total_sets"], SETS, 2, 1)["lines"] == ["over"]
    assert tm.grade_market(markets["first_set_winner"], SETS, 2, 1)["result"] == "home"
    assert tm.grade_market(markets["first_set_total_games"], SETS, 2, 1)["actual"] == 10
    assert tm.grade_market(markets["tiebreak"], SETS, 2, 1)["result"] == "yes"
    assert tm.grade_market(markets["game_handicap"], SETS, 2, 1)["actual"] == 0
    assert tm.grade_market(markets["home_to_win_a_set"], SETS, 2, 1)["result"] == "yes"
    assert tm.grade_market(markets["away_to_win_a_set"], SETS, 2, 1)["result"] == "yes"


def test_a_straight_sets_win_leaves_the_loser_without_a_set():
    markets = {m["id"]: m for m in tm.price_match(0.6, 3, "Hard", "ATP")}
    straight = [[6, 2], [6, 3]]
    assert tm.grade_market(markets["away_to_win_a_set"], straight, 2, 0)["result"] == "no"
    assert tm.grade_market(markets["tiebreak"], straight, 2, 0)["result"] == "no"


def test_set_dependent_markets_are_not_graded_without_set_scores():
    markets = {m["id"]: m for m in tm.price_match(0.6, 3, "Hard", "ATP")}
    assert tm.grade_market(markets["first_set_winner"], None, 2, 0) is None
    assert (
        tm.grade_market(markets["set_score"], None, 2, 0) is not None
    )  # the score alone is enough


# ---------------------------------------------------------------- the record


class _Match:
    def __init__(self, sport, home_score, away_score, period_scores, status="completed"):
        self.sport = sport
        self.home_score = home_score
        self.away_score = away_score
        self.period_scores = period_scores
        self.status = status


def test_a_pick_is_the_line_nearest_a_coin_flip():
    market = {
        "type": "over_under",
        "lines": [
            {"line": 100.5, "prob_over": 70.0, "prob_under": 30.0},
            {"line": 105.5, "prob_over": 52.0, "prob_under": 48.0},
            {"line": 110.5, "prob_over": 30.0, "prob_under": 70.0},
        ],
    }
    pick = market_pick(market)
    assert (pick["side"], pick["line_index"]) == ("over", 1)


def test_a_tied_period_is_void_for_a_winner_pick():
    market = {
        "type": "three_way",
        "home": 45.0,
        "tie": 5.0,
        "away": 50.0,
        "result": {"result": "tie"},
    }
    pick = market_pick(market)
    assert pick["side"] == "away"
    assert pick_correct(market, pick) is None


def test_the_record_counts_graded_calls_and_keeps_live_apart_from_reconstructed():
    match = _Match("basketball", 114, 106, PERIODS)
    markets = bm.price_game(116.2, 111.4, 0.64, "NBA")
    table = markets_record(
        [(True, "basketball", match, markets), (False, "basketball", match, markets)]
    )

    assert "q1_total" in table
    entry = table["q1_total"]
    assert entry["live"]["settled"] == 1 and entry["reconstructed"]["settled"] == 1


def test_results_are_attached_only_once_the_match_is_over():
    markets = bm.price_game(116.2, 111.4, 0.64, "NBA")
    upcoming = attach_results(
        "basketball", _Match("basketball", None, None, None, "scheduled"), markets
    )
    assert all("result" not in m for m in upcoming)
    finished = attach_results("basketball", _Match("basketball", 114, 106, PERIODS), markets)
    assert any("result" in m for m in finished)
