import os

from mltrader.config import Settings, load_dotenv


def test_dotenv_loads_and_respects_existing_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "ALPACA_API_KEY=file_key\n"
        "MLT_SYMBOLS='AAPL,MSFT'\n"
        "MLT_ENTRY_THRESHOLD=0.60\n"
        "malformed line without equals\n"
    )
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("MLT_SYMBOLS", raising=False)
    monkeypatch.setenv("MLT_ENTRY_THRESHOLD", "0.70")  # real env wins

    load_dotenv(env_file)

    assert os.environ["ALPACA_API_KEY"] == "file_key"
    assert os.environ["MLT_ENTRY_THRESHOLD"] == "0.70"
    settings = Settings()
    assert settings.symbols == ["AAPL", "MSFT"]
    assert settings.entry_threshold == 0.70


def test_missing_dotenv_is_fine(tmp_path):
    load_dotenv(tmp_path / "does_not_exist.env")
