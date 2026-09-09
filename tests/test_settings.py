import importlib

import app.config.settings as settings_module


def test_config_defaults_when_env_vars_unset(monkeypatch):
    for var in [
        "DATABASE_URL", "DATABASE_PATH", "MOMO_WEBHOOK_SECRET",
        "ORANGE_WEBHOOK_SECRET", "CAMPAY_WEBHOOK_SECRET",
        "SMOBILPAY_WEBHOOK_SECRET", "DEFAULT_AGGREGATOR",
    ]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_ENGINE", "sqlite")
    importlib.reload(settings_module)

    assert settings_module.Config.DB_ENGINE == "sqlite"
    assert settings_module.Config.DATABASE_PATH == "data/ecommerce.db"
    assert settings_module.Config.DATABASE_URL is None
    assert settings_module.Config.DEFAULT_AGGREGATOR == "campay"


def test_config_reads_env_vars_when_set(monkeypatch):
    monkeypatch.setenv("DB_ENGINE", "postgresql")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("MOMO_WEBHOOK_SECRET", "momo-secret")
    monkeypatch.setenv("ORANGE_WEBHOOK_SECRET", "orange-secret")
    monkeypatch.setenv("CAMPAY_WEBHOOK_SECRET", "campay-secret")
    monkeypatch.setenv("SMOBILPAY_WEBHOOK_SECRET", "smobilpay-secret")
    monkeypatch.setenv("DEFAULT_AGGREGATOR", "smobilpay")
    importlib.reload(settings_module)

    assert settings_module.Config.DB_ENGINE == "postgresql"
    assert settings_module.Config.DATABASE_URL == "postgresql://example/db"
    assert settings_module.Config.MOMO_WEBHOOK_SECRET == "momo-secret"
    assert settings_module.Config.ORANGE_WEBHOOK_SECRET == "orange-secret"
    assert settings_module.Config.CAMPAY_WEBHOOK_SECRET == "campay-secret"
    assert settings_module.Config.SMOBILPAY_WEBHOOK_SECRET == "smobilpay-secret"
    assert settings_module.Config.DEFAULT_AGGREGATOR == "smobilpay"
