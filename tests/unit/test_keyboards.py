from app.bot.keyboards.inline import response_actions


def test_response_actions_callback_data():
    markup = response_actions(message_id=42)

    callback_data = [button.callback_data for row in markup.inline_keyboard for button in row]

    assert callback_data == [
        "export_docx:42",
        "export_xlsx:42",
        "ask_cloud:42",
        "save_kb:42",
    ]
