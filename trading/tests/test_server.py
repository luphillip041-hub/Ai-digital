import pytest
from fastapi.testclient import TestClient

from mltrader.config import Settings
from mltrader.server import create_app


@pytest.fixture(scope="module")
def client():
    settings = Settings(api_key="", secret_key="", symbols=["SPY", "QQQ"])
    return TestClient(create_app(settings))


def test_index_serves_dashboard(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "mltrader" in res.text


def test_summary_demo_mode(client):
    data = client.get("/api/summary").json()
    assert data["mode"] == "demo"
    assert data["equity"] == 100_000.0
    assert data["symbols"] == ["SPY", "QQQ"]


def test_signals_one_per_symbol(client):
    data = client.get("/api/signals", params={"years": 3}).json()
    symbols = [s["symbol"] for s in data["signals"]]
    assert symbols == ["SPY", "QQQ"]
    for s in data["signals"]:
        assert 0 <= s["proba"] <= 1
        assert s["long"] == (s["proba"] >= data["threshold"])


def test_backtest_payload_shape(client):
    data = client.get("/api/backtest", params={"symbol": "SPY", "years": 3}).json()
    assert data["symbol"] == "SPY"
    assert len(data["dates"]) == len(data["strategy"]) == len(data["benchmark"])
    assert data["metrics"]["days"] == len(data["dates"])
    assert data["strategy"][0] > 0


def test_backtest_unknown_symbol_404(client):
    assert client.get("/api/backtest", params={"symbol": "NOPE"}).status_code == 404


def test_rebalance_demo_never_sends(client):
    data = client.post("/api/rebalance", json={"dry_run": False}).json()
    assert data["sent"] is False
    assert data["dry_run"] is True
    assert set(data["signals"]) == {"SPY", "QQQ"}
    for order in data["orders"]:
        assert order["side"] == "buy"  # demo starts flat, so only buys are possible
