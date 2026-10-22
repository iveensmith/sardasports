"""Carrying trained models to the server's database.

The engine finds a model through its `model_versions` row, and a row made on Windows stores a
path with backslashes that means nothing on the server. These pin the three things that matter:
only models with a file behind them travel, the server's rows get a path that works there, and a
half-uploaded set is refused rather than half-applied.
"""

from __future__ import annotations

import json
from datetime import datetime

from app.models import ModelVersion
from scripts.sync_models import apply_import, export_rows, main, plan_import

BACKSLASH = chr(92)
WINDOWS_PATH = BACKSLASH.join(["ml", "models", "xgboost_match_result_20261022T085734Z.json"])
CUTOFF = datetime(2026, 10, 22)


def _row(name, version, path, active=True, trained=datetime(2026, 10, 22, 9, 0)):
    return ModelVersion(
        model_name=name,
        version=version,
        artifact_path=path,
        metrics={"accuracy": 0.5},
        is_active=active,
        trained_at=trained,
    )


def _files(folder, *names):
    for name in names:
        (folder / name).write_text("x")


def test_export_carries_only_new_active_models_that_have_a_file(db_session, tmp_path):
    _files(tmp_path, "xgboost_match_result_20261022T085734Z.json", "old_1.json", "stale_1.json")
    db_session.add_all(
        [
            _row("xgboost_match_result", "20261022T085734Z", WINDOWS_PATH),
            _row("old", "1", "ml/models/old_1.json", trained=datetime(2026, 10, 1)),
            _row("stale", "1", "ml/models/stale_1.json", active=False),
            _row("calibration_x", "1", "n/a (calibration curve)"),
            _row("missing", "1", "ml/models/missing_1.json"),
        ]
    )
    db_session.commit()

    rows = export_rows(db_session, CUTOFF, tmp_path)

    assert [r["model_name"] for r in rows] == ["xgboost_match_result"]
    # Whatever separators the path was written with, only the file's own name travels.
    assert rows[0]["file"] == "xgboost_match_result_20261022T085734Z.json"


def _exported():
    return [
        {
            "model_name": "gbm_btts",
            "version": "20261022T090003Z",
            "file": "gbm_btts_20261022T090003Z.pkl",
            "metrics": {"accuracy": 0.549},
            "trained_at": "2026-10-22T09:00:03",
        }
    ]


def test_import_registers_a_version_the_server_lacks_with_a_path_that_works_there(
    db_session, tmp_path
):
    _files(tmp_path, "gbm_btts_20261022T090003Z.pkl", "gbm_btts_20261022T090003Z_scaler.json")
    db_session.add(_row("gbm_btts", "20260922T152525Z", "ml/models/gbm_btts_old.pkl"))
    db_session.add(_row("other_model", "1", "ml/models/other_1.pkl"))
    db_session.commit()

    plan, problems = plan_import(db_session, _exported(), tmp_path)
    assert problems == []
    assert plan[0]["add"] is True and plan[0]["switch_off"] == ["20260922T152525Z"]

    apply_import(db_session, plan)

    db_session.expire_all()
    new = db_session.query(ModelVersion).filter_by(version="20261022T090003Z").one()
    assert new.is_active is True
    assert new.artifact_path == "ml/models/gbm_btts_20261022T090003Z.pkl"
    old = db_session.query(ModelVersion).filter_by(version="20260922T152525Z").one()
    assert old.is_active is False  # kept, so it can be switched back to
    # A different model is not touched.
    assert db_session.query(ModelVersion).filter_by(model_name="other_model").one().is_active


def test_applying_twice_changes_nothing_the_second_time(db_session, tmp_path):
    _files(tmp_path, "gbm_btts_20261022T090003Z.pkl", "gbm_btts_20261022T090003Z_scaler.json")

    for _ in range(2):
        plan, problems = plan_import(db_session, _exported(), tmp_path)
        assert problems == []
        apply_import(db_session, plan)

    assert db_session.query(ModelVersion).filter_by(model_name="gbm_btts").count() == 1
    assert plan[0]["add"] is False and plan[0]["already_active"] is True


def test_a_missing_model_file_or_scaler_makes_the_import_unsafe(db_session, tmp_path):
    _files(tmp_path, "gbm_btts_20261022T090003Z.pkl")  # the scaler was not uploaded

    _plan, problems = plan_import(db_session, _exported(), tmp_path)

    assert len(problems) == 1 and "gbm_btts_20261022T090003Z_scaler.json" in problems[0]


def test_export_creates_the_folder_it_writes_to(db_session, tmp_path):
    """The first real run failed because the output folder did not exist."""
    models = tmp_path / "models"
    models.mkdir()
    _files(models, "xgboost_match_result_20261022T085734Z.json")
    db_session.add(_row("xgboost_match_result", "20261022T085734Z", WINDOWS_PATH))
    db_session.commit()
    out = tmp_path / "does" / "not" / "exist" / "models.json"

    code = main(
        ["export", "--trained-after", "2026-10-22", "--out", str(out), "--models-dir", str(models)]
    )

    assert code == 0
    assert [r["model_name"] for r in json.loads(out.read_text())] == ["xgboost_match_result"]
