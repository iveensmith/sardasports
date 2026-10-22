"""Carry trained models from a development machine to the server's database.

Models are trained on a development machine (training them inside the server's engine froze the
box on 12 Oct 2026; see docs/deployment.md). Copying the model files is not enough: the engine
finds a model through its `model_versions` row, and a row made on a Windows machine stores a
path written with backslashes, which means nothing on the server. This exports the active rows
for models trained after a date, and on the server registers them with paths that work there.

    # on the development machine
    python -m scripts.sync_models export --trained-after 2026-10-22 --out models.json

    # on the server, after the files are in the models folder (a dry run unless --apply)
    python -m scripts.sync_models import models.json
    python -m scripts.sync_models import models.json --apply

`import` is all-or-nothing: if any model file or its scaler is missing, nothing is changed. It
adds a row for a version the server does not have, makes that version the active one for its
name, and switches the name's other versions off, so it is safe to run twice. It never deletes a
row, so the previous versions stay available to switch back to.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models import ModelVersion

# Where the files are, as the engine sees them: relative to its working directory.
MODELS_DIR = "ml/models"


def _file_name(artifact_path: str) -> str:
    """The file's own name, whichever system's separators the path was written with."""
    return PureWindowsPath(artifact_path).name


def _scaler_name(file_name: str) -> str:
    path = PurePosixPath(file_name)
    return f"{path.stem}_scaler.json"


def export_rows(session: Session, trained_after: datetime, models_dir: Path) -> list[dict]:
    """Active versions trained after a date whose model file exists in `models_dir`.

    A row with no file behind it (a calibration curve, kept in the database alone) is not a
    model to carry, and is left out.
    """
    rows = (
        session.query(ModelVersion)
        .filter(ModelVersion.is_active.is_(True), ModelVersion.trained_at >= trained_after)
        .order_by(ModelVersion.model_name)
        .all()
    )
    out = []
    for row in rows:
        name = _file_name(row.artifact_path)
        if not (models_dir / name).is_file():
            continue
        out.append(
            {
                "model_name": row.model_name,
                "version": row.version,
                "file": name,
                "metrics": row.metrics,
                "trained_at": row.trained_at.isoformat(),
            }
        )
    return out


def plan_import(
    session: Session, rows: list[dict], models_dir: Path
) -> tuple[list[dict], list[str]]:
    """What importing would do, and what is wrong with it (empty means safe to apply)."""
    plan, problems = [], []
    for row in rows:
        for needed in (row["file"], _scaler_name(row["file"])):
            if not (models_dir / needed).is_file():
                problems.append(f"{row['model_name']}: {needed} is not in {models_dir}")
        existing = (
            session.query(ModelVersion)
            .filter(
                ModelVersion.model_name == row["model_name"], ModelVersion.version == row["version"]
            )
            .first()
        )
        others = (
            session.query(ModelVersion)
            .filter(
                ModelVersion.model_name == row["model_name"],
                ModelVersion.is_active.is_(True),
                ModelVersion.version != row["version"],
            )
            .all()
        )
        plan.append(
            {
                **row,
                "add": existing is None,
                "already_active": existing is not None and bool(existing.is_active),
                "switch_off": [o.version for o in others],
            }
        )
    return plan, problems


def apply_import(session: Session, plan: list[dict]) -> None:
    for item in plan:
        artifact = f"{MODELS_DIR}/{item['file']}"
        row = (
            session.query(ModelVersion)
            .filter(
                ModelVersion.model_name == item["model_name"],
                ModelVersion.version == item["version"],
            )
            .first()
        )
        if row is None:
            row = ModelVersion(
                model_name=item["model_name"],
                version=item["version"],
                artifact_path=artifact,
                metrics=item["metrics"],
                trained_at=datetime.fromisoformat(item["trained_at"]),
            )
            session.add(row)
        row.artifact_path = artifact
        row.is_active = True
        session.query(ModelVersion).filter(
            ModelVersion.model_name == item["model_name"], ModelVersion.version != item["version"]
        ).update({ModelVersion.is_active: False})
    session.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="write the active rows trained after a date")
    export.add_argument("--trained-after", required=True, help="YYYY-MM-DD")
    export.add_argument("--out", required=True)
    export.add_argument("--models-dir", default=MODELS_DIR)
    load = sub.add_parser("import", help="register exported models in this database")
    load.add_argument("file")
    load.add_argument("--models-dir", default=MODELS_DIR)
    load.add_argument("--apply", action="store_true", help="make the changes (default: show them)")
    args = parser.parse_args(argv)

    session = SessionLocal()
    try:
        if args.command == "export":
            rows = export_rows(
                session, datetime.fromisoformat(args.trained_after), Path(args.models_dir)
            )
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
            print(f"wrote {len(rows)} models to {args.out}")
            for row in rows:
                print(f"  {row['model_name']:36} {row['version']}  {row['file']}")
            return 0

        rows = json.loads(Path(args.file).read_text(encoding="utf-8"))
        plan, problems = plan_import(session, rows, Path(args.models_dir))
        for item in plan:
            state = (
                "add and activate"
                if item["add"]
                else ("already active" if item["already_active"] else "activate")
            )
            off = f"  (switches off {', '.join(item['switch_off'])})" if item["switch_off"] else ""
            print(f"  {item['model_name']:36} {item['version']}  {state}{off}")
        if problems:
            print("\nNOT SAFE TO APPLY:")
            for problem in problems:
                print("  -", problem)
            return 1
        if not args.apply:
            print(f"\ndry run: {len(plan)} models. Nothing changed; run again with --apply.")
            return 0
        apply_import(session, plan)
        print(f"\napplied: {len(plan)} models registered and active.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
