import numpy as np

from mltrader.features import (
    FEATURE_COLUMNS,
    FWD_RETURN_COLUMN,
    LABEL_COLUMN,
    build_dataset,
    build_features,
    rsi,
)


def test_feature_columns_present(bars):
    feats = build_features(bars)
    assert list(feats.columns) == FEATURE_COLUMNS


def test_dataset_has_no_nans_and_drops_last_day(bars):
    ds = build_dataset(bars)
    assert not ds.isna().any().any()
    # last bar has no forward return, so it can't appear in the dataset
    assert bars.index[-1] not in ds.index


def test_label_matches_forward_return_sign(bars):
    ds = build_dataset(bars)
    assert ((ds[FWD_RETURN_COLUMN] > 0).astype(int) == ds[LABEL_COLUMN]).all()


def test_no_lookahead_in_features(bars):
    """Features for day t must be unchanged when future bars are removed."""
    full = build_features(bars).dropna()
    cut = len(bars) - 100
    truncated = build_features(bars.iloc[:cut]).dropna()
    common = truncated.index.intersection(full.index)
    assert len(common) > 500
    np.testing.assert_allclose(
        full.loc[common].to_numpy(), truncated.loc[common].to_numpy(), rtol=1e-10
    )


def test_rsi_bounded(bars):
    values = rsi(bars["close"]).dropna()
    assert values.between(0, 100).all()
