from app.bot.keyboards.inline import response_actions
from app.bot.keyboards.reply import (
    BTN_COMPONENTS,
    BTN_MODULE_CALC,
    BTN_POWER_CALC,
    BTN_STOCK_SUMMARY,
    main_menu,
)


def test_main_menu_has_expected_buttons():
    markup = main_menu()

    texts = [button.text for row in markup.keyboard for button in row]

    assert texts == [BTN_POWER_CALC, BTN_MODULE_CALC, BTN_STOCK_SUMMARY, BTN_COMPONENTS]
    assert markup.resize_keyboard is True


def test_response_actions_callback_data():
    markup = response_actions(message_id=42)

    callback_data = [button.callback_data for row in markup.inline_keyboard for button in row]

    assert callback_data == [
        "export_docx:42",
        "export_xlsx:42",
        "ask_cloud:42",
        "save_kb:42",
    ]
