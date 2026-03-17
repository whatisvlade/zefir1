from flask import Flask, request, jsonify
import requests
import os

app = Flask('')
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

def answer_callback(callback_query_id):
    requests.post(f"{TELEGRAM_API}/answerCallbackQuery",
                  json={"callback_query_id": callback_query_id})

def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id,
               "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{TELEGRAM_API}/editMessageText", json=payload)

# Главное меню
def main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🛂 Визы", "callback_data": "visas"}],
            [{"text": "📞 Контакты", "callback_data": "contact"}]
        ]
    }

# amoCRM шлёт webhook сюда при новом сообщении от клиента
@app.route('/amo-webhook', methods=['POST'])
def amo_webhook():
    data = request.json or request.form.to_dict()
    # amoCRM передаёт chat_id клиента в Telegram
    chat_id = data.get("chat_id") or data.get("client_id")
    user_name = data.get("name", "друг")

    if chat_id:
        send_message(
            chat_id,
            f"Привет, {user_name}! 👋\nДобро пожаловать в Zefir Travel!\nВыберите, что вас интересует:",
            reply_markup=main_menu_keyboard()
        )
    return jsonify({"ok": True})

# Telegram шлёт callback_query сюда (через webhook на боте)
@app.route('/tg-webhook', methods=['POST'])
def tg_webhook():
    update = request.json

    if "callback_query" in update:
        cq = update["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]
        data = cq["data"]
        answer_callback(cq["id"])

        if data == "visas":
            # Строим кнопки из visas.json
            buttons = [[{"text": v["name"], "callback_data": f"visa_{k}"}]
                       for k, v in visas.items()]
            buttons.append([{"text": "🔙 Назад", "callback_data": "back"}])
            edit_message(chat_id, message_id, "🛂 Выберите направление:",
                         {"inline_keyboard": buttons})

        elif data.startswith("visa_") and not data.startswith("visa_req_"):
            key = data.replace("visa_", "")
            visa = visas.get(key)
            if visa:
                edit_message(chat_id, message_id,
                    f"{visa['description']}\n\n📱 {visa.get('manager_contact', DEFAULT_PHONE)}",
                    {"inline_keyboard": [
                        [{"text": "🔗 Подробнее", "url": visa["url"]}],
                        [{"text": "Оставить заявку", "callback_data": f"visa_req_{key}"}],
                        [{"text": "🔙 Назад", "callback_data": "visas"}]
                    ]}
                )

        elif data.startswith("visa_req_"):
            key = data.replace("visa_req_", "")
            visa = visas.get(key)
            user = cq["from"]
            # Отправляем заявку — amoCRM сам создаст сделку через свой канал
            requests.post(f"{TELEGRAM_API}/sendMessage", json={
                "chat_id": os.getenv("MANAGER_CHAT_ID"),  # чат менеджера
                "text": f"#ЗАЯВКА\nВиза: {visa['name']}\nКлиент: {user.get('first_name')} @{user.get('username','')}\nchat_id: {chat_id}"
            })
            edit_message(chat_id, message_id, "✅ Заявка отправлена!\nМенеджер свяжется с вами.",
                {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "visas"}]]})

        elif data == "contact":
            edit_message(chat_id, message_id,
                f"📞 Контакты:\n📱 {DEFAULT_PHONE}\n🏢 {COMPANY_ADDRESS}\n🕓 {SCHEDULE}",
                {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "back"}]]})

        elif data == "back":
            user_name = cq["from"].get("first_name", "")
            edit_message(chat_id, message_id,
                f"Привет, {user_name}! 👋\nВыберите, что вас интересует:",
                reply_markup=main_menu_keyboard())

    return jsonify({"ok": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
