from mltrader.risk import RiskLimits, orders_from_weights, target_weights

LIMITS = RiskLimits(max_position_pct=0.20, max_gross_exposure=1.0)


def test_no_signal_means_all_zero_weights():
    weights = target_weights({"SPY": 0.50, "QQQ": 0.40}, 0.55, LIMITS)
    assert weights == {"SPY": 0.0, "QQQ": 0.0}


def test_selected_symbols_capped_at_max_position():
    weights = target_weights({"SPY": 0.70, "QQQ": 0.60, "AAPL": 0.10}, 0.55, LIMITS)
    assert weights["SPY"] == weights["QQQ"] == 0.20  # 1.0/2 capped at 0.20
    assert weights["AAPL"] == 0.0


def test_gross_exposure_split_when_many_signals():
    proba = {s: 0.9 for s in ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J")}
    weights = target_weights(proba, 0.55, LIMITS)
    assert sum(weights.values()) <= LIMITS.max_gross_exposure + 1e-9
    assert all(w == 0.10 for w in weights.values())


def test_orders_diff_current_holdings_sells_first():
    weights = {"SPY": 0.20, "QQQ": 0.0}
    orders = orders_from_weights(
        weights,
        prices={"SPY": 500.0, "QQQ": 400.0},
        current_notional={"QQQ": 5_000.0},
        equity=100_000.0,
        limits=LIMITS,
    )
    assert [o["side"] for o in orders] == ["sell", "buy"]
    sell, buy = orders
    assert sell == {"symbol": "QQQ", "side": "sell", "notional": 5_000.0}
    assert buy == {"symbol": "SPY", "side": "buy", "notional": 20_000.0}


def test_dust_orders_skipped():
    orders = orders_from_weights(
        {"SPY": 0.20},
        prices={"SPY": 500.0},
        current_notional={"SPY": 19_999.60},
        equity=100_000.0,
        limits=LIMITS,
    )
    assert orders == []
