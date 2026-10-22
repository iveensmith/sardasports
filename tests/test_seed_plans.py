"""The premium plans are set from code, in dollars, and VIP stays off until it has a benefit."""

from __future__ import annotations

from app.models.premium import Plan
from scripts.seed_plans import PLANS, apply_plans, plan_changes


def test_the_four_plans_are_priced_in_dollars_at_the_owners_prices(db_session):
    apply_plans(db_session)

    rows = {p.code: p for p in db_session.query(Plan).all()}
    assert {code: (p.price_minor, p.currency, p.interval) for code, p in rows.items()} == {
        "weekly": (500, "USD", "week"),
        "monthly": (1800, "USD", "month"),
        "yearly": (15000, "USD", "year"),
        "vip_monthly": (5599, "USD", "month"),
    }


def test_vip_is_off_until_it_has_something_only_vip_members_get(db_session):
    apply_plans(db_session)

    active = {p.code for p in db_session.query(Plan).filter(Plan.active.is_(True))}
    assert active == {"weekly", "monthly", "yearly"}


def test_a_dry_run_changes_nothing_and_says_what_would_change(db_session):
    db_session.add(
        Plan(
            code="monthly",
            name="Old",
            price_minor=50,
            currency="USD",
            interval="month",
            active=True,
        )
    )
    db_session.commit()

    changes = {c["code"]: c for c in plan_changes(db_session)}

    assert changes["weekly"]["before"] is None
    assert changes["monthly"]["before"]["price_minor"] == 50
    assert changes["monthly"]["after"]["price_minor"] == 1800
    assert db_session.query(Plan).count() == 1


def test_running_it_twice_changes_nothing_the_second_time(db_session):
    apply_plans(db_session)
    apply_plans(db_session)

    assert db_session.query(Plan).count() == len(PLANS)
    assert all(c["before"] == c["after"] for c in plan_changes(db_session))
