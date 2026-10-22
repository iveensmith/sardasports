"""Set the premium plans and their prices from code.

The plans are priced in US dollars so a member anywhere can pay by card. The owner set, on
23 Oct 2026:

    weekly        $5
    monthly       $18
    yearly        $150
    VIP monthly   $55.99   (not set by the owner: the figure it was first converted to, from
                           NGN 75,000 at 1 USD = 1,334.42 NGN; it stays switched off, see below)

To change a price, change it below and run this again, or edit the plan in /admin/premium; a new
price applies to new payments only.

VIP is created switched off. It has no benefit of its own yet (everything a paid plan unlocks, it
unlocks too), so selling it as something different would promise what the site does not do. Switch
it on in /admin/premium once there is something that only VIP members get.

    python -m scripts.seed_plans            # show what would change
    python -m scripts.seed_plans --apply    # make the changes

Safe to run twice. A plan that exists under one of these codes is updated to the values here.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.premium import Plan
from app.services import premium_service

PLANS = [
    {
        "code": "weekly",
        "name": "Weekly",
        "description": "Every prediction, every day, for a week.",
        "price_minor": 500,
        "currency": "USD",
        "interval": "week",
        "active": True,
    },
    {
        "code": "monthly",
        "name": "Monthly",
        "description": "Every prediction, every day, for a month.",
        "price_minor": 1800,
        "currency": "USD",
        "interval": "month",
        "active": True,
    },
    {
        "code": "yearly",
        "name": "Yearly",
        "description": "Every prediction, every day, for a year.",
        "price_minor": 15000,
        "currency": "USD",
        "interval": "year",
        "active": True,
    },
    {
        "code": "vip_monthly",
        "name": "VIP",
        "description": "",
        "price_minor": 5599,
        "currency": "USD",
        "interval": "month",
        "active": False,
    },
]

FIELDS = ("name", "description", "price_minor", "currency", "interval", "active")


def plan_changes(db: Session) -> list[dict]:
    """For each plan above: what is stored now (None if new) and what it would become."""
    out = []
    for wanted in PLANS:
        row = db.query(Plan).filter(Plan.code == wanted["code"]).first()
        before = None if row is None else {field: getattr(row, field) for field in FIELDS}
        after = {field: wanted[field] for field in FIELDS}
        out.append({"code": wanted["code"], "before": before, "after": after})
    return out


def apply_plans(db: Session) -> None:
    for wanted in PLANS:
        premium_service.save_plan(db, **wanted)
    db.commit()


def _money(minor: int, currency: str) -> str:
    return f"{minor / 100:,.2f} {currency}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--apply", action="store_true", help="make the changes (default: show them)"
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        for change in plan_changes(db):
            after, before = change["after"], change["before"]
            price = _money(after["price_minor"], after["currency"])
            state = "on sale" if after["active"] else "OFF"
            code = change["code"]
            if before is None:
                print(f"  {code:12} new       {price} per {after['interval']} ({state})")
            elif before == after:
                print(f"  {code:12} unchanged {price} per {after['interval']} ({state})")
            else:
                was = _money(before["price_minor"], before["currency"])
                old = "on sale" if before["active"] else "OFF"
                print(
                    f"  {code:12} CHANGES   {was} per {before['interval']} ({old})"
                    f"  ->  {price} per {after['interval']} ({state})"
                )
        if not args.apply:
            print("\ndry run: nothing changed. Run again with --apply.")
            return 0
        apply_plans(db)
        print("\napplied.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
