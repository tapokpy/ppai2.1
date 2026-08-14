from app.core.capabilities import load_capabilities_summary


def test_load_capabilities_summary_renders_bullet_list(tmp_path):
    config = tmp_path / "capabilities.yaml"
    config.write_text(
        """
capabilities:
  - name: Тест-функция
    description: Делает тестовую вещь.
  - name: Вторая функция
    description: Делает что-то ещё.
""",
        encoding="utf-8",
    )

    summary = load_capabilities_summary(str(config))

    assert "Тест-функция: Делает тестовую вещь." in summary
    assert "Вторая функция: Делает что-то ещё." in summary


def test_load_capabilities_summary_returns_empty_for_missing_file(tmp_path):
    summary = load_capabilities_summary(str(tmp_path / "nope.yaml"))

    assert summary == ""


def test_load_capabilities_summary_returns_empty_for_empty_list(tmp_path):
    config = tmp_path / "capabilities.yaml"
    config.write_text("capabilities: []\n", encoding="utf-8")

    summary = load_capabilities_summary(str(config))

    assert summary == ""


def test_load_capabilities_summary_returns_empty_for_malformed_yaml(tmp_path):
    config = tmp_path / "capabilities.yaml"
    # Unbalanced brackets — a genuine yaml.YAMLError, not just "empty".
    config.write_text("capabilities: [\n  - name: Тест\n", encoding="utf-8")

    summary = load_capabilities_summary(str(config))

    assert summary == ""


def test_load_capabilities_summary_skips_entries_missing_fields(tmp_path):
    config = tmp_path / "capabilities.yaml"
    config.write_text(
        """
capabilities:
  - name: Без описания
  - name: Полная
    description: Есть всё.
""",
        encoding="utf-8",
    )

    summary = load_capabilities_summary(str(config))

    assert "Без описания" not in summary
    assert "Полная: Есть всё." in summary
