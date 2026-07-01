import numpy as np

from mltrader.features import build_dataset
from mltrader.model import load_model, predict_proba_up, save_model, train


def test_train_and_predict_proba_range(bars):
    ds = build_dataset(bars)
    model = train(ds)
    proba = predict_proba_up(model, ds)
    assert proba.shape == (len(ds),)
    assert ((proba >= 0) & (proba <= 1)).all()


def test_save_and_load_roundtrip(bars, tmp_path):
    ds = build_dataset(bars)
    model = train(ds)
    path = tmp_path / "model.joblib"
    save_model(model, path)
    loaded = load_model(path)
    np.testing.assert_allclose(
        predict_proba_up(model, ds), predict_proba_up(loaded, ds)
    )
