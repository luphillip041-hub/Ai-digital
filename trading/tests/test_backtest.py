import numpy as np
import pytest

from mltrader.backtest import walk_forward_backtest


def test_backtest_runs_and_metrics_are_finite(bars):
    result = walk_forward_backtest(bars)
    assert len(result.equity) > 200
    for value in (result.total_return, result.cagr, result.sharpe,
                  result.max_drawdown, result.hit_rate, result.exposure):
        assert np.isfinite(value)
    assert result.max_drawdown <= 0
    assert 0 <= result.exposure <= 1
    assert (result.equity > 0).all()


def test_impossible_threshold_means_flat_and_zero_return(bars):
    result = walk_forward_backtest(bars, entry_threshold=1.01)
    assert result.exposure == 0
    assert result.total_return == pytest.approx(0.0)


def test_costs_reduce_returns(bars):
    free = walk_forward_backtest(bars, cost_bps=0.0)
    costly = walk_forward_backtest(bars, cost_bps=50.0)
    if free.positions.diff().abs().sum() > 0:
        assert costly.total_return < free.total_return


def test_insufficient_data_raises(bars):
    with pytest.raises(ValueError, match="Not enough data"):
        walk_forward_backtest(bars.iloc[:300])


def test_summary_renders(bars):
    text = walk_forward_backtest(bars).summary()
    assert "Sharpe" in text and "max drawdown" in text
