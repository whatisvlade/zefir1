import asyncio
import os
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
REQUEST_TRIGGER = "#ЗАЯВКА"

# --- Контакты менеджеров ---
MANAGER_CONTACTS = {
    "default": "+375290000000",  # Общий по умолчанию
    "georgia": "+375291234567",
    "abkhazia": "+375292345678",
    "gelendzhik": "+375293456789",
    "dagestan": "+375294567890",
    "piter": "+375295678901",
    "teriberka": "+375296789012",
    "belarus": "+375297890123",
    "avia": "+375298888888",  # Менеджер по авиа турам
}

# --- Автобусные туры ---
BUS_TOURS = {
    "georgia": {
        "name": "Грузия",
        "desc": "Грузия — прекрасная страна с горами, морем и вином.",
        "url": "https://example.com/georgia"
    },
    "abkhazia": {
        "name": "Абхазия",
        "desc": "<b>Абхазия: Два варианта!</b> 1️⃣ <b>АВТОБУСНЫЙ</b> ... 2️⃣ <b>ЖД</b> ...",
        "url": "https://zefirtravel.by/avtobusnie-tury-iz-minska-s-otdyhom-na-more/?set_filter=y&arFilterTours_262_1198337567=Y"
    },
    "gelendzhik": {
        "name": "Геленджик",
        "desc": "<b>Тур в Геленджик</b> <b>Даты:</b> ...",
        "url": "https://zefirtravel.by/avtobusnie-tury-iz-minska-s-otdyhom-na-more/?set_filter=y&arFilterTours_262_2671772459=Y"
    },
    "dagestan": {
        "name": "Дагестан",
        "desc": "<b>Тур в Дагестан</b> Даты: ...",
        "url": "https://zefirtravel.by/offers/tur-v-dagestan-serdtse-kavkaza/"
    },
    "piter": {
        "name": "Питер",
        "desc": "<b>Тур в Санкт-Петербург</b> <b>Даты:</b> ...",
        "url": "https://zefirtravel.by/offers/tur-v-sankt-peterburg-kareliya/"
    },
    "teriberka": {
        "name": "Териберка",
        "desc": "<b>Тур в Териберку!</b> <b>Даты:</b> ...",
        "url": "https://zefirtravel.by/offers/teriberka-aysfloating-i-mogushchestvennye-kity/"
    },
    "belarus": {
        "name": "Беларусь",
        "desc": "<b>Западные сокровища Беларуси: Коссово и Ружаны</b> Даты: ...",
        "url": "https://zefirtravel.by/offers/zapadnye-sokrovishcha-belarusi-kossovo-i-ruzhany/"
    },
}

# --- Авиа туры ---
AVIA_TOUR_LINK = "https://tours.example.com"

app = Flask('')

@app.route('/')
def home():
    return "✅ Бот работает"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\nДобро пожаловать в Zefir Travel!\nВыберите, что вас интересует:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚌 Автобусные туры", callback_data="bus_tours")],
            [InlineKeyboardButton("✈️ Авиа туры", callback_data="avia_tours")],
            [InlineKeyboardButton("📞 Контакты", callback_data="contact")]
        ])
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # --- Автобусные туры ---
    if query.data == "bus_tours":
        buttons = [
            [InlineKeyboardButton(f"🌍 {BUS_TOURS[key]['name']}", callback_data=f"tour_{key}")]
            for key in BUS_TOURS
        ]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
        await query.edit_message_text(
            "🚌 Автобусные туры:\nВыберите направление:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    # --- Страница конкретного автобусного тура ---
    elif query.data.startswith("tour_"):
        tour_key = query.data.replace("tour_", "")
        if tour_key in BUS_TOURS:
            tour = BUS_TOURS[tour_key]
            manager_phone = MANAGER_CONTACTS.get(tour_key, MANAGER_CONTACTS["default"])
            await query.edit_message_text(
                f"{tour['desc']}\n\n📱 Контакт менеджера: {manager_phone}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Подробнее / Программа тура", url=tour['url'])],
                    [InlineKeyboardButton("Оставить заявку", callback_data=f"request_{tour_key}")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="bus_tours")]
                ]),
                parse_mode="HTML"
            )

    # --- Заявка на тур ---
    elif query.data.startswith("request_"):
        direction = query.data.replace("request_", "")
        tour_name = BUS_TOURS.get(direction, {}).get("name", direction)
        back_btn = "bus_tours"
        user = query.from_user
        msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=f"{REQUEST_TRIGGER} Тур: {tour_name}\nИмя: {user.first_name} @{user.username or ''}"
        )
        async def delete_request_msg(bot, chat_id, message_id):
            await asyncio.sleep(3)
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                pass
        asyncio.create_task(delete_request_msg(context.bot, query.message.chat.id, msg.message_id))
        now_hour = datetime.now().hour
        if 21 <= now_hour or now_hour < 10:
            resp = "Заявка отправлена!\nВ рабочее время с вами свяжется менеджер."
        else:
            resp = "Заявка отправлена!\nОжидайте, с вами свяжется менеджер."
        await query.edit_message_text(
            resp,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data=back_btn)]])
        )

    # --- Авиа туры ---
    elif query.data == "avia_tours":
        manager_phone = MANAGER_CONTACTS.get("avia", MANAGER_CONTACTS["default"])
        await query.edit_message_text(
            "✈️ Авиа туры:\n\n"
            "Выберите действие:\n\n"
            f"📱 Контакт менеджера: {manager_phone}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Самостоятельный подбор тура", url=AVIA_TOUR_LINK)],
                [InlineKeyboardButton("Оставить заявку (подбор тура с менеджером)", callback_data="avia_request")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
            ]),
            parse_mode="HTML"
        )

    elif query.data == "avia_request":
        user = query.from_user
        msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=f"{REQUEST_TRIGGER} Авиа тур\nИмя: {user.first_name} @{user.username or ''}"
        )
        async def delete_request_msg(bot, chat_id, message_id):
            await asyncio.sleep(3)
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                pass
        asyncio.create_task(delete_request_msg(context.bot, query.message.chat.id, msg.message_id))
        now_hour = datetime.now().hour
        if 21 <= now_hour or now_hour < 10:
            resp = "Заявка на подбор тура отправлена!\nВ рабочее время с вами свяжется менеджер."
        else:
            resp = "Заявка на подбор тура отправлена!\nОжидайте, с вами свяжется менеджер."
        await query.edit_message_text(
            resp,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="avia_tours")]])
        )

    # --- Контакты ---
    elif query.data == "contact":
        manager_phone = MANAGER_CONTACTS.get("default")
        await query.edit_message_text(
            f"📞 Контакты:\n"
            f"📱 Общий номер: {manager_phone}\n"
            "🏢 Адрес: г. Минск, ул. Примерная, 1\n"
            "🕓 Время работы: пн-пт 10:00–19:00, сб 11:00–16:00, вс — по договорённости",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]),
            parse_mode="HTML"
        )

    # --- Назад ---
    elif query.data == "back_to_menu":
        await query.edit_message_text(
            f"Привет, {query.from_user.first_name}! 👋\nДобро пожаловать в Zefir Travel!\nВыберите, что вас интересует:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚌 Автобусные туры", callback_data="bus_tours")],
                [InlineKeyboardButton("✈️ Авиа туры", callback_data="avia_tours")],
                [InlineKeyboardButton("📞 Контакты", callback_data="contact")]
            ])
        )

async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_button))
    keep_alive()
    await application.run_polling()

if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
