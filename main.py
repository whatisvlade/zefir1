from flask import Flask, request, jsonify
import requests
import os
import json

app = Flask('')

BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
DEFAULT_PHONE = os.getenv("DEFAULT_PHONE", "+375290000000")
COMPANY_ADDRESS = os.getenv("COMPANY_ADDRESS", "г. Минск, ул. Примерная, 1")
SCHEDULE = os.getenv("SCHEDULE", "пн-пт 10:00–19:00, сб 11:00–16:00")

# Загрузка виз
try:
    with open('visas.json', 'r', encoding='utf-8') as f:
        visas = json.load(f)
except FileNotFoundError:
    visas = {}

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    r = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)
    print("send_message:", r.status_code, r.text, flush=True)

def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    r = requests.post(f"{TELEGRAM_API}/editMessageText", json=payload)
    print("edit_message:", r.status_code, r.text, flush=True)

def answer_callback(callback_query_id):
    r = requests.post(
        f"{TELEGRAM_API}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id}
    )
    print("answer_callback:", r.status_code, r.text, flush=True)

def main_menu(chat_id, message_id, user_name, edit=False):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🛂 Визы", "callback_data": "visas"}],
            [{"text": "📞 Контакты", "callback_data": "contact"}]
        ]
    }
    text = (
        f"Привет, {user_name}! 👋\n"
        f"Добро пожаловать в Zefir Travel!\n"
        f"Выберите, что вас интересует:"
    )
    if edit and message_id is not None:
        edit_message(chat_id, message_id, text, keyboard)
    else:
        send_message(chat_id, text, keyboard)

@app.route('/')
def home():
    return "✅ Zefir Travel Bot работает!"

@app.route('/tg-webhook', methods=['POST'])
def tg_webhook():
    update = request.json
    print("UPDATE:", update, flush=True)

    if not update:
        return jsonify({"ok": True})

    # Обработка команды /start
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        user_name = msg.get("from", {}).get("first_name", "")
        text = msg.get("text", "")
        print("MESSAGE:", chat_id, text, flush=True)

        if text == "/start":
            main_menu(chat_id, None, user_name, edit=False)

        return jsonify({"ok": True})

    # Обработка кнопок
    if "callback_query" in update:
        cq = update["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]
        data = cq["data"]
        user_name = cq["from"].get("first_name", "")
        print("CALLBACK:", chat_id, message_id, data, flush=True)

        answer_callback(cq["id"])

        if data == "visas":
            buttons = [
                [{"text": v["name"], "callback_data": f"visa_{k}"}]
                for k, v in visas.items()
            ]
            buttons.append([{"text": "🔙 Назад", "callback_data": "back"}])

            edit_message(
                chat_id,
                message_id,
                "🛂 Визы:\nВыберите направление:",
                {"inline_keyboard": buttons}
            )

        elif data.startswith("visa_req_"):
            key = data.replace("visa_req_", "")
            visa = visas.get(key, {})

            edit_message(
                chat_id,
                message_id,
                (
                    f"✅ Заявка на визу <b>{visa.get('name', '')}</b> отправлена!\n"
                    "Менеджер свяжется с вами в рабочее время."
                ),
                {"inline_keyboard": [
                    [{"text": "🔙 Назад", "callback_data": "visas"}]
                ]}
            )

        elif data.startswith("visa_"):
            key = data.replace("visa_", "")
            visa = visas.get(key)
            if visa:
                phone = visa.get("manager_contact", DEFAULT_PHONE)
                edit_message(
                    chat_id,
                    message_id,
                    f"{visa['description']}\n\n📱 Контакт менеджера: {phone}",
                    {"inline_keyboard": [
                        [{"text": "🔗 Подробнее", "url": visa["url"]}],
                        [{"text": "✉️ Оставить заявку", "callback_data": f"visa_req_{key}"}],
                        [{"text": "🔙 Назад", "callback_data": "visas"}]
                    ]}
                )

        elif data == "contact":
            edit_message(
                chat_id,
                message_id,
                (
                    f"📞 Контакты:\n"
                    f"📱 {DEFAULT_PHONE}\n"
                    f"🏢 {COMPANY_ADDRESS}\n"
                    f"🕓 {SCHEDULE}"
                ),
                {"inline_keyboard": [
                    [{"text": "🔙 Назад", "callback_data": "back"}]
                ]}
            )

        elif data == "back":
            main_menu(chat_id, message_id, user_name, edit=True)

    return jsonify({"ok": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
