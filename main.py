import asyncio
import os
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

@dataclass
class VisaInfo:
    """Класс для хранения информации о визе"""
    name: str
    description: str
    url: str
    manager_contact: Optional[str] = None

@dataclass
class BotConfig:
    """Класс для хранения конфигурации бота"""
    bot_token: str
    request_trigger: str
    default_manager_contact: str
    working_hours: Dict[str, int]
    company_info: Dict[str, str]

class ConfigManager:
    
    @staticmethod
    def load_config() -> BotConfig:
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        except FileNotFoundError:
            logger.warning("config.json не найден, используются значения по умолчанию")
            config_data = {}
        
        return BotConfig(
            bot_token=os.getenv("BOT_TOKEN", config_data.get("bot_token", "")),
            request_trigger=config_data.get("request_trigger", "#ЗАЯВКА"),
            default_manager_contact=config_data.get("default_manager_contact", "+375290000000"),
            working_hours=config_data.get("working_hours", {"start": 10, "end": 21}),
            company_info=config_data.get("company_info", {
                "address": "г. Минск, ул. Примерная, 1",
                "schedule": "пн-пт 10:00–19:00, сб 11:00–16:00, вс — по договорённости"
            })
        )
    
    @staticmethod
    def load_visas() -> Dict[str, VisaInfo]:
        """Загружает информацию о визах из файла"""
        try:
            with open('visas.json', 'r', encoding='utf-8') as f:
                visas_data = json.load(f)
            
            visas = {}
            for key, data in visas_data.items():
                visas[key] = VisaInfo(
                    name=data["name"],
                    description=data["description"],
                    url=data["url"],
                    manager_contact=data.get("manager_contact")
                )
            return visas
        except FileNotFoundError:
            logger.error("visas.json не найден! Создайте файл с визами.")
            return {}

class MessageTemplates:
    
    @staticmethod
    def welcome_message(user_name: str) -> str:
        return f"Привет, {user_name}! 👋\nДобро пожаловать в Zefir Travel!\nВыберите, что вас интересует:"
    
    @staticmethod
    def request_sent_message(is_working_hours: bool) -> str:
        if is_working_hours:
            return "Заявка отправлена!\nОжидайте, с вами свяжется менеджер."
        return "Заявка отправлена!\nВ рабочее время с вами свяжется менеджер."

class TravelBot:
    
    def __init__(self):
        self.config = ConfigManager.load_config()
        self.visas = ConfigManager.load_visas()
        self.application = None
        self.app = Flask('')
    
    def keep_alive(self):
        @self.app.route('/')
        def home():
            return "✅ Zefir Travel Bot работает!"

        def run():
            import logging
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.ERROR)
            self.app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

        t = Thread(target=run)
        t.daemon = True
        t.start()
    
    def is_working_hours(self) -> bool:
        moscow_tz = pytz.timezone('Europe/Moscow')
        current_hour = datetime.now(moscow_tz).hour
        return self.config.working_hours["start"] <= current_hour < self.config.working_hours["end"]
    
    def get_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🛂 Визы", callback_data="visas")],
            [InlineKeyboardButton("📞 Контакты", callback_data="contact")]
        ])
    
    async def send_request_message(self, context, chat_id: int, service_name: str, user_info: str):
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{self.config.request_trigger} Услуга: {service_name}\n{user_info}"
        )
        
        async def delete_message():
            await asyncio.sleep(3)
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
            except Exception as e:
                logger.error(f"Ошибка при удалении сообщения: {e}")
        
        asyncio.create_task(delete_message())
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text(
            MessageTemplates.welcome_message(user.first_name),
            reply_markup=self.get_main_menu_keyboard()
        )
    
    async def handle_visas(self, query, context):
        """Список виз"""
        buttons = [
            [InlineKeyboardButton(visa.name, callback_data=f"visa_{key}")]
            for key, visa in self.visas.items()
        ]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            "🛂 Визы:\nВыберите направление:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    async def handle_specific_visa(self, query, context, visa_key: str):
        """Конкретная виза"""
        if visa_key not in self.visas:
            await query.edit_message_text("Виза не найдена")
            return
        
        visa = self.visas[visa_key]
        manager_phone = visa.manager_contact or self.config.default_manager_contact
        
        await query.edit_message_text(
            f"{visa.description}\n\n📱 Контакт менеджера: {manager_phone}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Подробнее", url=visa.url)],
                [InlineKeyboardButton("Оставить заявку", callback_data=f"visa_request_{visa_key}")],
                [InlineKeyboardButton("🔙 Назад", callback_data="visas")]
            ]),
            parse_mode="HTML"
        )
    
    async def handle_visa_request(self, query, context, visa_key: str):
        """Заявка на визу"""
        visa = self.visas.get(visa_key)
        if not visa:
            await query.edit_message_text("Виза не найдена")
            return
        
        user = query.from_user
        user_info = f"Имя: {user.first_name} @{user.username or ''}"
        
        await self.send_request_message(context, query.message.chat.id, visa.name, user_info)
        
        await query.edit_message_text(
            MessageTemplates.request_sent_message(self.is_working_hours()),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="visas")]
            ])
        )
    
    async def handle_contacts(self, query, context):
        await query.edit_message_text(
            f"📞 Контакты:\n"
            f"📱 Общий номер: {self.config.default_manager_contact}\n"
            f"🏢 Адрес: {self.config.company_info['address']}\n"
            f"🕓 Время работы: {self.config.company_info['schedule']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
            ]),
            parse_mode="HTML"
        )
    
    async def handle_back_to_menu(self, query, context):
        await query.edit_message_text(
            MessageTemplates.welcome_message(query.from_user.first_name),
            reply_markup=self.get_main_menu_keyboard()
        )
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        try:
            if query.data == "visas":
                await self.handle_visas(query, context)
            elif query.data.startswith("visa_request_"):
                visa_key = query.data.replace("visa_request_", "")
                await self.handle_visa_request(query, context, visa_key)
            elif query.data.startswith("visa_"):
                visa_key = query.data.replace("visa_", "")
                await self.handle_specific_visa(query, context, visa_key)
            elif query.data == "contact":
                await self.handle_contacts(query, context)
            elif query.data == "back_to_menu":
                await self.handle_back_to_menu(query, context)
        except Exception as e:
            logger.error(f"Ошибка при обработке callback: {e}")
            await query.edit_message_text("Произошла ошибка. Попробуйте еще раз.")
    
    async def run(self):
        if not self.config.bot_token:
            logger.error("BOT_TOKEN не установлен!")
            return
        
        self.application = ApplicationBuilder().token(self.config.bot_token).build()
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        self.keep_alive()
        
        logger.info("Бот запущен в режиме polling")
        await self.application.run_polling()

async def main():
    bot = TravelBot()
    await bot.run()

if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
