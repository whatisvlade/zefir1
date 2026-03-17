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
MANAGER_CHAT_ID = os.getenv("MANAGER_CHAT_ID")

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
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id,
               "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{TELEGRAM_API}/editMessageText", json=payload)

def answer_callback(callback_query_id):
    requests.post(f"{TELEGRAM_API}/answerCallbackQuery",
                  json={"callback_query_id": callback_query_id})

def main_menu(chat_id, message_id, user_name, edit=False):
    keyboard = {"inline_keyboard": [
        [{"text": "🛂 Визы", "callback_data": "visas"}],
        [{"text": "📞 Контакты", "callback_data": "contact"}]
    ]}
    text = f"Привет, {user_name}! 👋\nДобро пожаловать в Zefir Travel!\nВыберите, что вас интересует:"
    if edit:
        edit_message(chat_id, message_id, text, keyboard)
    else:
        send_message(chat_id, text, keyboard)

@app.route('/')
def home():
    return "✅ Zefir Travel Bot работает!"

@app.route('/tg-webhook', methods=['POST'])
def tg_webhook():
    update = request.json
    if not update:
        return jsonify({"ok": True})

    # Обработка команды /start
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        user_name = msg.get("from", {}).get("first_name", "")
        if msg.get("text") == "/start":
            main_menu(chat_id, None, user_name, edit=False)
        return jsonify({"ok": True})

    # Обработка кнопок
    if "callback_query" in update:
        cq = update["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]
        data = cq["data"]
        user_name = cq["from"].get("first_name", "")
        user = cq["from"]
        answer_callback(cq["id"])

        if data == "visas":
            buttons = [[{"text": v["name"], "callback_data": f"visa_{k}"}]
                       for k, v in visas.items()]
            buttons.append([{"text": "🔙 Назад", "callback_data": "back"}])
            edit_message(chat_id, message_id, "🛂 Визы:\nВыберите направление:",
                         {"inline_keyboard": buttons})

        elif data.startswith("visa_req_"):
            key = data.replace("visa_req_", "")
            visa = visas.get(key, {})
            if MANAGER_CHAT_ID:
                requests.post(f"{TELEGRAM_API}/sendMessage", json={
                    "chat_id": MANAGER_CHAT_ID,
                    "text": f"#ЗАЯВКА\nВиза: {visa.get('name','')}\nКлиент: {user.get('first_name','')} @{user.get('username','')}\nchat_id: {chat_id}"
                })
            edit_message(chat_id, message_id,
                "✅ Заявка отправлена!\nМенеджер свяжется с вами в рабочее время.",
                {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "visas"}]]})

        elif data.startswith("visa_"):
            key = data.replace("visa_", "")
            visa = visas.get(key)
            if visa:
                phone = visa.get("manager_contact", DEFAULT_PHONE)
                edit_message(chat_id, message_id,
                    f"{visa['description']}\n\n📱 Контакт менеджера: {phone}",
                    {"inline_keyboard": [
                        [{"text": "🔗 Подробнее", "url": visa["url"]}],
                        [{"text": "✉️ Оставить заявку", "callback_data": f"visa_req_{key}"}],
                        [{"text": "🔙 Назад", "callback_data": "visas"}]
                    ]})

        elif data == "contact":
            edit_message(chat_id, message_id,
                f"📞 Контакты:\n📱 {DEFAULT_PHONE}\n🏢 {COMPANY_ADDRESS}\n🕓 {SCHEDULE}",
                {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "back"}]]})

        elif data == "back":
            main_menu(chat_id, message_id, user_name, edit=True)

    return jsonify({"ok": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
