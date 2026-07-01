"""Signal model: a gradient-boosted tree classifier predicting P(next day up).

Kept deliberately simple and regularized — daily equity direction is a very
low signal-to-noise problem and complex models overfit instantly.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from .features import FEATURE_COLUMNS, LABEL_COLUMN


def make_model(random_state: int = 0) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_depth=3,
        max_iter=200,
        learning_rate=0.05,
        l2_regularization=1.0,
        min_samples_leaf=50,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=random_state,
    )


def train(dataset: pd.DataFrame, random_state: int = 0) -> HistGradientBoostingClassifier:
    """Fit on an already-built dataset (see features.build_dataset)."""
    model = make_model(random_state)
    model.fit(dataset[FEATURE_COLUMNS], dataset[LABEL_COLUMN])
    return model


def predict_proba_up(model, features: pd.DataFrame) -> np.ndarray:
    """P(next day up) for each row of features (FEATURE_COLUMNS order)."""
    return model.predict_proba(features[FEATURE_COLUMNS])[:, 1]


def save_model(model, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def load_model(path: str | Path):
    return joblib.load(path)
