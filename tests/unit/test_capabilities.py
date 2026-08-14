from app.core.capabilities import format_capabilities_for_user, load_capabilities_summary


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


def test_format_capabilities_for_user_is_first_person_not_system_prompt_phrasing(tmp_path):
    config = tmp_path / "capabilities.yaml"
    config.write_text(
        "capabilities:\n  - name: Чертежи\n    description: Читаю .dxf/.dwg.\n", encoding="utf-8"
    )

    text = format_capabilities_for_user(str(config))

    assert "Вот что я умею" in text
    assert "Чертежи: Читаю .dxf/.dwg." in text
    # Not the system-prompt phrasing, which addresses the LLM as "ты" in a
    # way that would misleadingly read as addressing the human user instead
    # if sent to them verbatim.
    assert "которыми ты реально располагаешь" not in text


def test_format_capabilities_for_user_returns_friendly_message_when_missing(tmp_path):
    text = format_capabilities_for_user(str(tmp_path / "nope.yaml"))

    assert text != ""
    assert "недоступен" in text


def test_format_capabilities_for_user_escapes_html_placeholders(tmp_path):
    # Real capabilities.yaml entries use literal "<ID>"-style placeholders
    # in their descriptions (e.g. "/project_bom <ID>"). The bot sends this
    # text straight to Telegram with parse_mode=HTML, which rejects
    # unescaped "<...>" as an unsupported tag and fails to send the whole
    # reply — this must come out escaped, not raw.
    config = tmp_path / "capabilities.yaml"
    config.write_text(
        "capabilities:\n  - name: Проекты\n    description: \"/project_bom <ID> считает BOM.\"\n",
        encoding="utf-8",
    )

    text = format_capabilities_for_user(str(config))

    assert "<ID>" not in text
    assert "&lt;ID&gt;" in text
