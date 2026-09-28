"""SHAP-based explainability for the XGBoost match-result model.

For a single prediction, returns the features that most pushed the model
toward (or away from) its predicted outcome — real SHAP values from the
actual trained model, computed on the actual scaled feature vector used for
that prediction. Never returns invented numbers: if no model is loaded, or
SHAP fails for any reason, callers get `None` and the API surfaces no
`explanation` field rather than a fabricated one.
"""

from __future__ import annotations

import weakref

import numpy as np
import shap
import xgboost as xgb

from ml.training.common import FEATURE_COLUMNS

TOP_N_FEATURES = 5

# A TreeExplainer depends only on the model, never on the row being
# explained, but constructing one re-parses the whole booster — measured at
# ~0.98s per call, which was the single largest cost in a prediction and
# made a 40-fixture board spend ~40 seconds rebuilding the same object.
#
# Keyed weakly by model identity so a retrain that swaps the active model in
# simply gets a new entry and the old explainer is collected with the old
# model, rather than pinning a stale booster in memory forever.
_EXPLAINER_CACHE: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _explainer_for(model: xgb.XGBClassifier) -> shap.TreeExplainer:
    explainer = _EXPLAINER_CACHE.get(model)
    if explainer is None:
        explainer = shap.TreeExplainer(model)
        _EXPLAINER_CACHE[model] = explainer
    return explainer


def explain_prediction(
    model: xgb.XGBClassifier | None,
    scaled_features: np.ndarray | None,
    predicted_class_index: int,
) -> list[dict] | None:
    """Top contributing features for `predicted_class_index` (0=home, 1=draw, 2=away).

    `scaled_features` must be the same scaled 2D array (shape (1, n_features))
    that was passed to `model.predict_proba` for this prediction.
    """
    if model is None or scaled_features is None:
        return None

    try:
        explainer = _explainer_for(model)
        raw = explainer.shap_values(scaled_features)
        class_values = _select_class_values(raw, predicted_class_index)
    except Exception:  # noqa: BLE001 - explainability is best-effort, never breaks /predict
        return None

    contributions = list(zip(FEATURE_COLUMNS, class_values, strict=True))
    contributions.sort(key=lambda pair: abs(pair[1]), reverse=True)

    return [
        {"feature": name, "impact_percentage_points": round(float(value) * 100, 2)}
        for name, value in contributions[:TOP_N_FEATURES]
    ]


def _select_class_values(raw, class_index: int) -> np.ndarray:
    """Normalize the several shapes shap.TreeExplainer can return for a
    multiclass model into a flat (n_features,) array for one class/sample."""
    arr = np.asarray(raw)

    if arr.ndim == 3:
        # (n_samples, n_features, n_classes) — modern shap unified API.
        if arr.shape[-1] > class_index:
            return arr[0, :, class_index]
        # (n_classes, n_samples, n_features) — older layout.
        return arr[class_index, 0, :]

    if isinstance(raw, list):
        # list[n_classes] of (n_samples, n_features).
        return np.asarray(raw[class_index])[0]

    # (n_samples, n_features) — binary/regression-style output, single class.
    return arr[0]
