"""The prediction board's three views.

The board's whole argument is that a blended probability hides which of the
engine's three independent estimators actually backed it. These tests pin
that derivation and the rule that decides when the engine has no coherent
view — both are easy to get subtly wrong and neither fails loudly.
"""

from __future__ import annotations

from app.api.routes_board import _passed, _pick_from, agreement_for
from ml.ensemble import EnsembleInput, combine


def _prediction(elo, poisson, xgboost, confidence_label="High"):
    """A prediction payload shaped like the service emits."""
    out = combine(
        EnsembleInput(
            elo_probs=elo,
            poisson_probs=poisson,
            xgboost_probs=xgboost,
            expected_goals_home=1.4,
            expected_goals_away=1.1,
            top_scorelines=[],
            prob_btts_yes=0.5,
            feature_completeness=1.0,
        )
    )
    return {
        "home_win": out.home_win,
        "draw": out.draw,
        "away_win": out.away_win,
        "confidence": out.confidence,
        "confidence_label": confidence_label,
        "estimator_probs": out.estimator_probs,
    }


def test_pick_is_the_argmax_outcome():
    assert _pick_from([60.0, 25.0, 15.0]) == "home"
    assert _pick_from([20.0, 50.0, 30.0]) == "draw"
    assert _pick_from([10.0, 30.0, 60.0]) == "away"
    assert _pick_from(None) is None
    assert _pick_from([]) is None


def test_unanimous_agreement_is_reported_as_such():
    prediction = _prediction((0.6, 0.25, 0.15), (0.55, 0.3, 0.15), (0.58, 0.27, 0.15))
    agreement = agreement_for(prediction)
    assert agreement["agreeing"] == 3
    assert agreement["total"] == 3
    assert agreement["unanimous"] is True
    assert agreement["pick"] == "home"


def test_a_dissenting_estimator_is_counted_and_named():
    """The point of the feature: the blend must not hide the split."""
    prediction = _prediction((0.6, 0.25, 0.15), (0.55, 0.3, 0.15), (0.15, 0.25, 0.6))
    agreement = agreement_for(prediction)
    assert agreement["unanimous"] is False
    assert agreement["agreeing"] == 2
    assert agreement["by_estimator"]["xgboost"] == "away"
    assert agreement["by_estimator"]["elo"] == "home"


def test_no_agreement_reported_when_there_is_nothing_to_compare():
    """Basketball and tennis blend one model with an Elo baseline.

    Reporting "1 of 1 agree" would dress a single opinion up as a
    consensus, so the field is absent rather than trivially unanimous.
    """
    assert agreement_for({"estimator_probs": {"elo": [50.0, 25.0, 25.0]}}) is None
    assert agreement_for({"estimator_probs": {}}) is None
    assert agreement_for({}) is None


def test_minority_backing_counts_as_not_called():
    """Confidence does not measure outcome agreement, so it cannot catch this.

    A fixture where one estimator backs the pick and two dissent can still
    be labelled "High" — the confidence score compares probability vectors,
    not chosen outcomes. Without this rule such a fixture is presented as a
    confident call.
    """
    agreement = {"agreeing": 1, "total": 3, "unanimous": False, "pick": "home"}
    assert _passed({"confidence_label": "High"}, agreement) is True


def test_majority_backing_is_a_real_disagreement_not_a_pass():
    agreement = {"agreeing": 2, "total": 3, "unanimous": False, "pick": "home"}
    assert _passed({"confidence_label": "High"}, agreement) is False


def test_low_confidence_is_not_called_whatever_the_split():
    agreement = {"agreeing": 3, "total": 3, "unanimous": True, "pick": "home"}
    assert _passed({"confidence_label": "Low"}, agreement) is True


def test_an_unpriced_fixture_is_not_called():
    assert _passed(None, None) is True


def test_two_estimator_sports_are_never_passed_on_the_split_rule():
    """The minority rule needs three estimators to mean anything.

    With two, "1 of 2" is a tie rather than a minority, and treating it as
    the engine declining would mislabel every basketball and tennis fixture.
    """
    agreement = {"agreeing": 1, "total": 2, "unanimous": False, "pick": "home"}
    assert _passed({"confidence_label": "High"}, agreement) is False
