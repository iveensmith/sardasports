"""Repair team rows corrupted by encoding, and merge accent duplicates.

Two defects, both of which split one real competitor across two `teams`
rows and so split its match history and its Elo:

1. **Mojibake.** `clean_data.py` used to read every raw CSV as latin-1.
   That is correct for Football-Data.co.uk but wrong for the UTF-8 CSVs the
   API-sourced adapters write, so "Türkiye" was stored as "TÃ¼rkiye". The
   root cause is fixed (clean_data now tries UTF-8 first); this repairs the
   rows already written.

2. **Accent-only differences.** Football-Data.co.uk writes "Castellon",
   API-Football writes "Castellón". Both are the same club, and storing
   both leaves the newer row with no history and no rating.

Merging keeps the row with the most matches as canonical — that is the one
carrying the Elo history — and repoints `matches`, `elo_history` and
`injuries` at it before deleting the duplicate.

Idempotent: a second run finds nothing to do. Dry by default.

Usage:
    uv run python scripts/repair_team_names.py            # report only
    uv run python scripts/repair_team_names.py --apply
"""

from __future__ import annotations

import argparse
import logging
import re
from collections import defaultdict

from sqlalchemy import text

from app.database.session import SessionLocal
from app.utils.team_names import fold_team_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# UTF-8 bytes rendered as latin-1 leave these tell-tale sequences.
MOJIBAKE_PATTERN = re.compile(r"[ÃÂ]\S|â€|ï¿½")

# Every column that points at teams.id, so a merge leaves nothing dangling.
TEAM_REFERENCES = [
    ("matches", "home_team_id"),
    ("matches", "away_team_id"),
    ("elo_history", "team_id"),
    ("elo_history", "opponent_team_id"),
    ("injuries", "team_id"),
]


def demojibake(name: str) -> str | None:
    """The correct UTF-8 reading of a latin-1-mangled name, or None."""
    if not MOJIBAKE_PATTERN.search(name):
        return None
    try:
        fixed = name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return fixed if fixed != name else None


def _match_count(session, team_id: int) -> int:
    return session.execute(
        text("select count(*) from matches " "where home_team_id = :tid or away_team_id = :tid"),
        {"tid": team_id},
    ).scalar_one()


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair mojibake and accent-duplicate teams")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        rows = session.execute(text("select id, name, sport from teams")).all()

        # Group first, rename second. Renaming a mojibake row up front can
        # collide with the correctly-encoded row for the same competitor —
        # "TÃ¼rkiye" -> "Türkiye" hits UNIQUE(sport, name) when the real
        # "Türkiye" already exists. That pair is a *merge*, not a rename, so
        # the corrected spelling feeds the grouping key and the survivor is
        # renamed afterwards, once its duplicates are gone.
        groups: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
        for tid, name, sport in rows:
            canonical = demojibake(name) or name
            groups[(sport, fold_team_key(canonical))].append((tid, name))

        fixed_names = 0
        merged = 0
        for (sport, key), members in sorted(groups.items()):
            if not key:
                continue
            counted = sorted(
                ((tid, name, _match_count(session, tid)) for tid, name in members),
                key=lambda x: -x[2],
            )
            keep_id, keep_name, keep_n = counted[0]

            # Repair the survivor's spelling once nothing else claims it.
            corrected = demojibake(keep_name)
            if corrected:
                logger.info("mojibake: %r -> %r (id=%s)", keep_name, corrected, keep_id)
                fixed_names += 1

            for dup_id, dup_name, dup_n in counted[1:]:
                logger.info(
                    "merge [%s]: %r (id=%s, %d matches) <- %r (id=%s, %d matches)",
                    sport,
                    keep_name,
                    keep_id,
                    keep_n,
                    dup_name,
                    dup_id,
                    dup_n,
                )
                if args.apply:
                    for table, column in TEAM_REFERENCES:
                        session.execute(
                            text(f"update {table} set {column} = :keep where {column} = :dup"),
                            {"keep": keep_id, "dup": dup_id},
                        )
                    session.execute(text("delete from teams where id = :i"), {"i": dup_id})
                merged += 1

            # Rename after the deletes, so the target name is free.
            if corrected and args.apply:
                session.execute(
                    text("update teams set name = :n where id = :i"),
                    {"n": corrected, "i": keep_id},
                )

        if args.apply:
            session.commit()
            logger.info(
                "Applied: %d name(s) repaired, %d duplicate(s) merged.", fixed_names, merged
            )
        else:
            logger.info(
                "Dry run: %d name(s) would be repaired, %d duplicate(s) merged. "
                "Re-run with --apply.",
                fixed_names,
                merged,
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
