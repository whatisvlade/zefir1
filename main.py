import asyncio
import os
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from flask import Flask, request
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime
import concurrent.futures
import pytz

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TourInfo:
    """Класс для хранения информации о туре"""
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
    avia_tour_link: str
    working_hours: Dict[str, int]
    company_info: Dict[str, str]
    webhook_url: Optional[str] = None

class ConfigManager:
    """Менеджер для работы с конфигурацией"""
    
    @staticmethod
    def load_config() -> BotConfig:
        """Загружает конфигурацию из файла или переменных окружения"""
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
            avia_tour_link=config_data.get("avia_tour_link", "https://tours.example.com"),
            working_hours=config_data.get("working_hours", {"start": 10, "end": 21}),
            company_info=config_data.get("company_info", {
                "address": "г. Минск, ул. Примерная, 1",
                "schedule": "пн-пт 10:00–19:00, сб 11:00–16:00, вс — по договорённости"
            }),
            webhook_url=os.getenv("WEBHOOK_URL", config_data.get("webhook_url"))
        )
    
    @staticmethod
    def load_tours() -> Dict[str, TourInfo]:
        """Загружает информацию о турах из файла"""
        try:
            with open('tours.json', 'r', encoding='utf-8') as f:
                tours_data = json.load(f)
            
            tours = {}
            for key, data in tours_data.items():
                tours[key] = TourInfo(
                    name=data["name"],
                    description=data["description"],
                    url=data["url"],
                    manager_contact=data.get("manager_contact")
                )
            return tours
        except FileNotFoundError:
            logger.error("tours.json не найден! Создайте файл с турами.")
            return {}

class MessageTemplates:
    """Шаблоны сообщений"""
    
    @staticmethod
    def welcome_message(user_name: str) -> str:
        return f"Привет, {user_name}! 👋\nДобро пожаловать в Zefir Travel!\nВыберите, что вас интересует:"
    
    @staticmethod
    def request_sent_message(is_working_hours: bool) -> str:
        if is_working_hours:
            return "Заявка отправлена!\nОжидайте, с вами свяжется менеджер."
        return "Заявка отправлена!\nВ рабочее время с вами свяжется менеджер."
    
    @staticmethod
    def avia_request_sent_message(is_working_hours: bool) -> str:
        if is_working_hours:
            return "Заявка на подбор тура отправлена!\nОжидайте, с вами свяжется менеджер."
        return "Заявка на подбор тура отправлена!\nВ рабочее время с вами свяжется менеджер."

class TravelBot:
    """Основной класс бота"""
    
    def __init__(self):
        self.config = ConfigManager.load_config()
        self.tours = ConfigManager.load_tours()
        self.app = Flask('')
        self.application = None
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        
    def setup_flask(self):
        """Настройка Flask приложения"""
        @self.app.route('/')
        def home():
            return "✅ Бот работает"
        
        @self.app.route('/webhook', methods=['POST'])
        def webhook():
            """Обработчик webhook от Telegram"""
            try:
                json_data = request.get_json()
                if json_data and self.application:
                    update = Update.de_json(json_data, self.application.bot)
                    # Запускаем обработку в отдельном потоке
                    self.executor.submit(self._process_update_sync, update)
                return "OK", 200
            except Exception as e:
                logger.error(f"Ошибка в webhook: {e}")
                return "Error", 500
    
    def _process_update_sync(self, update):
        """Синхронная обертка для обработки обновлений"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.application.process_update(update))
            loop.close()
        except Exception as e:
            logger.error(f"Ошибка при обработке обновления: {e}")
    
    def keep_alive(self):
        """Запуск Flask сервера в отдельном потоке"""
        def run():
            import logging
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.ERROR)  # Скрыть предупреждения Flask
            self.app.run(host='0.0.0.0', port=8080)
        
        t = Thread(target=run)
        t.daemon = True
        t.start()
    
    def is_working_hours(self) -> bool:
        """Проверяет, рабочее ли время (московское время)"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        current_hour = datetime.now(moscow_tz).hour
        start_hour = self.config.working_hours["start"]
        end_hour = self.config.working_hours["end"]
        return start_hour <= current_hour < end_hour
    
    def get_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Возвращает клавиатуру главного меню"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🚌 Автобусные туры", callback_data="bus_tours")],
            [InlineKeyboardButton("✈️ Авиа туры", callback_data="avia_tours")],
            [InlineKeyboardButton("📞 Контакты", callback_data="contact")]
        ])
    
    async def send_request_message(self, context: ContextTypes.DEFAULT_TYPE, 
                                 chat_id: int, tour_name: str, user_info: str):
        """Отправляет сообщение с заявкой и удаляет его через 3 секунды"""
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{self.config.request_trigger} Тур: {tour_name}\n{user_info}"
        )
        
        async def delete_message():
            await asyncio.sleep(3)
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
            except Exception as e:
                logger.error(f"Ошибка при удалении сообщения: {e}")
        
        asyncio.create_task(delete_message())
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        await update.message.reply_text(
            MessageTemplates.welcome_message(user.first_name),
            reply_markup=self.get_main_menu_keyboard()
        )
    
    async def handle_bus_tours(self, query, context):
        """Обработка автобусных туров"""
        buttons = [
            [InlineKeyboardButton(f"{tour.name}", callback_data=f"tour_{key}")]
            for key, tour in self.tours.items()
        ]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            "🚌 Автобусные туры:\nВыберите направление:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    async def handle_specific_tour(self, query, context, tour_key: str):
        """Обработка конкретного тура"""
        if tour_key not in self.tours:
            await query.edit_message_text("Тур не найден")
            return
        
        tour = self.tours[tour_key]
        manager_phone = tour.manager_contact or self.config.default_manager_contact
        
        await query.edit_message_text(
            f"{tour.description}\n\n📱 Контакт менеджера: {manager_phone}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Подробнее / Программа тура", url=tour.url)],
                [InlineKeyboardButton("Оставить заявку", callback_data=f"request_{tour_key}")],
                [InlineKeyboardButton("🔙 Назад", callback_data="bus_tours")]
            ]),
            parse_mode="HTML"
        )
    
    async def handle_tour_request(self, query, context, tour_key: str):
        """Обработка заявки на тур"""
        tour = self.tours.get(tour_key)
        if not tour:
            await query.edit_message_text("Тур не найден")
            return
        
        user = query.from_user
        user_info = f"Имя: {user.first_name} @{user.username or ''}"
        
        await self.send_request_message(
            context, query.message.chat.id, tour.name, user_info
        )
        
        response_text = MessageTemplates.request_sent_message(self.is_working_hours())
        await query.edit_message_text(
            response_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="bus_tours")]
            ])
        )
    
    async def handle_avia_tours(self, query, context):
        """Обработка авиа туров"""
        await query.edit_message_text(
            f"✈️ Авиа туры:\n\n"
            f"Выберите действие:\n\n"
            f"📱 Контакт менеджера: {self.config.default_manager_contact}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Самостоятельный подбор тура", url=self.config.avia_tour_link)],
                [InlineKeyboardButton("Оставить заявку (подбор тура с менеджером)", callback_data="avia_request")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
            ]),
            parse_mode="HTML"
        )
    
    async def handle_avia_request(self, query, context):
        """Обработка заявки на авиа тур"""
        user = query.from_user
        user_info = f"Имя: {user.first_name} @{user.username or ''}"
        
        await self.send_request_message(
            context, query.message.chat.id, "Авиа тур", user_info
        )
        
        response_text = MessageTemplates.avia_request_sent_message(self.is_working_hours())
        await query.edit_message_text(
            response_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="avia_tours")]
            ])
        )
    
    async def handle_contacts(self, query, context):
        """Обработка контактов"""
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
        """Возврат в главное меню"""
        await query.edit_message_text(
            MessageTemplates.welcome_message(query.from_user.first_name),
            reply_markup=self.get_main_menu_keyboard()
        )
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Основной обработчик callback запросов"""
        query = update.callback_query
        await query.answer()
        
        try:
            if query.data == "bus_tours":
                await self.handle_bus_tours(query, context)
            elif query.data.startswith("tour_"):
                tour_key = query.data.replace("tour_", "")
                await self.handle_specific_tour(query, context, tour_key)
            elif query.data.startswith("request_"):
                tour_key = query.data.replace("request_", "")
                await self.handle_tour_request(query, context, tour_key)
            elif query.data == "avia_tours":
                await self.handle_avia_tours(query, context)
            elif query.data == "avia_request":
                await self.handle_avia_request(query, context)
            elif query.data == "contact":
                await self.handle_contacts(query, context)
            elif query.data == "back_to_menu":
                await self.handle_back_to_menu(query, context)
        except Exception as e:
            logger.error(f"Ошибка при обработке callback: {e}")
            await query.edit_message_text("Произошла ошибка. Попробуйте еще раз.")
    
    async def run(self):
        """Запуск бота"""
        if not self.config.bot_token:
            logger.error("BOT_TOKEN не установлен!")
            return
        
        self.application = ApplicationBuilder().token(self.config.bot_token).build()
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Устанавливаем webhook
        webhook_url = self.config.webhook_url
        if webhook_url:
            await self.application.bot.set_webhook(url=f"{webhook_url}/webhook")
            logger.info(f"Webhook установлен: {webhook_url}/webhook")
        else:
            # Удаляем webhook если его нет
            await self.application.bot.delete_webhook()
            logger.info("Webhook удален, используется polling")
        
        self.setup_flask()
        self.keep_alive()
        
        logger.info("Бот запущен")
        
        # Если есть webhook URL, запускаем только Flask, иначе polling
        if webhook_url:
            # Инициализируем приложение для webhook
            await self.application.initialize()
            await self.application.start()
            # Держим приложение запущенным
            while True:
                await asyncio.sleep(1)
        else:
            await self.application.run_polling()

async def main():
    """Главная функция"""
    bot = TravelBot()
    await bot.run()

if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
