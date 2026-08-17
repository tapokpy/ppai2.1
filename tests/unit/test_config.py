from app.core.config import Settings


def test_admin_ids_parsed_from_csv():
    settings = Settings(ADMIN_IDS="123456789,987654321")
    assert settings.admin_ids == [123456789, 987654321]


def test_admin_ids_empty_by_default():
    settings = Settings(ADMIN_IDS="")
    assert settings.admin_ids == []


def test_defaults_are_sane():
    settings = Settings()
    assert settings.RAG_SCORE_THRESHOLD == 0.75
    assert settings.CLOUD_DAILY_LIMIT_PER_USER == 50
    assert settings.CLOUD_ENABLED is False


def test_disabled_tools_parsed_from_csv():
    settings = Settings(TOOLS_DISABLED="warehouse_lookup, list_projects")
    assert settings.disabled_tools == {"warehouse_lookup", "list_projects"}


def test_disabled_tools_empty_by_default():
    settings = Settings(TOOLS_DISABLED="")
    assert settings.disabled_tools == set()
