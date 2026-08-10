from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def response_actions(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 DOCX", callback_data=f"export_docx:{message_id}"),
                InlineKeyboardButton(text="📊 Excel", callback_data=f"export_xlsx:{message_id}"),
            ],
            [
                InlineKeyboardButton(text="☁️ Переспросить в Cloud", callback_data=f"ask_cloud:{message_id}"),
                InlineKeyboardButton(text="💾 Сохранить в Базу Знаний", callback_data=f"save_kb:{message_id}"),
            ],
        ]
    )


def calculator_export_actions(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 Коммерческое предложение (DOCX)", callback_data=f"export_docx:{message_id}"),
                InlineKeyboardButton(text="📊 Смета (Excel)", callback_data=f"export_xlsx:{message_id}"),
            ],
        ]
    )
