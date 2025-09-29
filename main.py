import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
from datetime import datetime, timedelta
import re

# Включим логирование для отслеживания ошибок
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен бота (замени на свой!)
BOT_TOKEN = "ТВОЙ_ТОКЕН_ЗДЕСЬ"

# Состояния для ConversationHandler
SETTING_DATE, SETTING_FREQUENCY = range(2)

# Хранилище данных пользователей
user_data_store = {}


class CountdownBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()

    def setup_handlers(self):
        """Настройка обработчиков команд"""
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                SETTING_DATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.set_date)
                ],
                SETTING_FREQUENCY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.set_frequency)
                ],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)]
        )

        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler("status", self.show_status))
        self.application.add_handler(CommandHandler("stop", self.stop_reminders))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало работы с ботом"""
        await update.message.reply_text(
            "🎉 Привет! Я бот для отсчёта времени до важных дат!\n\n"
            "📅 Введи дату, до которой хочешь вести отсчёт.\n"
            "Можно ввести в формате:\n"
            "• 31.12.2024\n"
            "• 2024-12-31\n"
            "• 'через 30 дней'\n"
            "• 'через 2 месяца'\n\n"
            "Для отмены введи /cancel"
        )

        return SETTING_DATE

    def parse_date(self, date_text: str):
        """Парсит дату из строки без использования dateutil"""
        date_text = date_text.strip()

        # Если относительная дата
        if date_text.lower().startswith('через'):
            return self.parse_relative_date(date_text)

        # Попробуем разные форматы дат
        formats = [
            '%d.%m.%Y',  # 31.12.2024
            '%Y-%m-%d',  # 2024-12-31
            '%d/%m/%Y',  # 31/12/2024
            '%d %m %Y',  # 31 12 2024
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_text, fmt)
            except ValueError:
                continue

        # Если ни один формат не подошел
        raise ValueError("Не могу распознать формат даты")

    def parse_relative_date(self, text: str) -> datetime:
        """Парсит относительные даты типа 'через X дней/месяцев'"""
        text = text.lower()
        today = datetime.now()

        if 'день' in text or 'дня' in text or 'дней' in text:
            numbers = re.findall(r'\d+', text)
            if numbers:
                days = int(numbers[0])
                return today + timedelta(days=days)

        elif 'недел' in text:
            numbers = re.findall(r'\d+', text)
            if numbers:
                weeks = int(numbers[0])
                return today + timedelta(weeks=weeks)

        elif 'месяц' in text or 'месяца' in text or 'месяцев' in text:
            numbers = re.findall(r'\d+', text)
            if numbers:
                months = int(numbers[0])
                # Простое добавление месяцев
                new_month = today.month + months
                year = today.year + (new_month - 1) // 12
                month = (new_month - 1) % 12 + 1
                day = today.day
                # Проверяем валидность даты
                try:
                    return datetime(year, month, day)
                except ValueError:
                    # Если день невалидный (например, 31 февраля), берем последний день месяца
                    next_month = datetime(year, month, 28) + timedelta(days=4)  # Переходим на следующий месяц
                    return next_month - timedelta(days=next_month.day)

        raise ValueError("Не могу распознать формат даты")

    async def set_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка введённой даты"""
        user_id = update.effective_user.id
        date_text = update.message.text

        try:
            # Парсим дату
            target_date = self.parse_date(date_text)

            # Проверяем, что дата в будущем
            if target_date <= datetime.now():
                await update.message.reply_text(
                    "❌ Дата должна быть в будущем! Попробуй ещё раз:"
                )
                return SETTING_DATE

            # Сохраняем дату
            if user_id not in user_data_store:
                user_data_store[user_id] = {}

            user_data_store[user_id]['target_date'] = target_date

            # Создаем клавиатуру для выбора частоты
            keyboard = [
                ["Каждый день", "Каждую неделю"],
                ["Каждый месяц", "Только один раз"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

            await update.message.reply_text(
                f"✅ Дата установлена: {target_date.strftime('%d.%m.%Y')}\n\n"
                "📊 Теперь выбери частоту напоминаний:",
                reply_markup=reply_markup
            )

            return SETTING_FREQUENCY

        except Exception as e:
            await update.message.reply_text(
                f"❌ Не могу распознать дату. Ошибка: {str(e)}\n"
                "Попробуй ещё раз! Примеры: '31.12.2024', 'через 30 дней'"
            )
            return SETTING_DATE

    async def set_frequency(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора частоты"""
        user_id = update.effective_user.id
        frequency = update.message.text

        # Проверяем валидность выбора
        valid_frequencies = ["Каждый день", "Каждую неделю", "Каждый месяц", "Только один раз"]
        if frequency not in valid_frequencies:
            await update.message.reply_text(
                "❌ Пожалуйста, выбери частоту из предложенных вариантов:",
                reply_markup=ReplyKeyboardMarkup([
                    ["Каждый день", "Каждую неделю"],
                    ["Каждый месяц", "Только один раз"]
                ], one_time_keyboard=True)
            )
            return SETTING_FREQUENCY

        # Сохраняем частоту
        user_data_store[user_id]['frequency'] = frequency

        await update.message.reply_text(
            "✅ Отлично! Напоминания настроены! 🎉\n\n"
            f"📅 Целевая дата: {user_data_store[user_id]['target_date'].strftime('%d.%m.%Y')}\n"
            f"📊 Частота: {frequency}\n\n"
            "Используй команды:\n"
            "/status - посмотреть статус\n"
            "/stop - остановить напоминания\n"
            "/start - настроить новую дату",
            reply_markup=ReplyKeyboardRemove()
        )

        # Запускаем напоминания
        await self.schedule_reminders(user_id, context)

        return ConversationHandler.END

    async def schedule_reminders(self, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Настройка расписания напоминаний"""
        user_data = user_data_store.get(user_id)
        if not user_data:
            return

        target_date = user_data['target_date']
        frequency = user_data['frequency']

        # Удаляем старые задания
        if 'job' in user_data:
            user_data['job'].schedule_removal()

        # Создаем новое задание в зависимости от частоты
        if frequency == "Каждый день":
            job = context.job_queue.run_repeating(
                self.send_reminder,
                interval=86400,  # 24 часа в секундах
                first=10,  # Первое напоминание через 10 секунд
                user_id=user_id
            )
        elif frequency == "Каждую неделю":
            job = context.job_queue.run_repeating(
                self.send_reminder,
                interval=604800,  # 7 дней в секундах
                first=10,
                user_id=user_id
            )
        elif frequency == "Каждый месяц":
            job = context.job_queue.run_repeating(
                self.send_reminder,
                interval=2592000,  # ~30 дней в секундах
                first=10,
                user_id=user_id
            )
        else:  # Только один раз
            time_until = (target_date - datetime.now()).total_seconds()
            if time_until > 0:
                job = context.job_queue.run_once(
                    self.send_reminder,
                    when=time_until,
                    user_id=user_id
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Целевая дата уже прошла!"
                )
                return

        user_data['job'] = job
        user_data_store[user_id] = user_data

    async def send_reminder(self, context: ContextTypes.DEFAULT_TYPE):
        """Отправка напоминания"""
        job = context.job
        user_id = job.user_id
        user_data = user_data_store.get(user_id)

        if user_data and 'target_date' in user_data:
            target_date = user_data['target_date']
            now = datetime.now()

            if now < target_date:
                days_left = (target_date - now).days

                message = (
                    f"⏰ Напоминание!\n"
                    f"📅 До целевой даты ({target_date.strftime('%d.%m.%Y')}) "
                    f"осталось {days_left} дней!\n"
                    f"🎯 Это {target_date.strftime('%d %B %Y')}"
                )
            else:
                message = (
                    f"🎉 Поздравляю! Целевая дата наступила!\n"
                    f"📅 {target_date.strftime('%d.%m.%Y')} - этот день настал!"
                )
                # Останавливаем напоминания
                if 'job' in user_data:
                    user_data['job'].schedule_removal()
                user_data_store[user_id] = user_data

            await context.bot.send_message(chat_id=user_id, text=message)

    async def show_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать текущий статус"""
        user_id = update.effective_user.id
        user_data = user_data_store.get(user_id)

        if not user_data or 'target_date' not in user_data:
            await update.message.reply_text(
                "❌ У тебя нет активных отсчётов.\n"
                "Используй /start чтобы начать!"
            )
            return

        target_date = user_data['target_date']
        frequency = user_data.get('frequency', 'Не установлена')
        now = datetime.now()

        if now < target_date:
            days_left = (target_date - now).days
            status_text = (
                f"📊 Текущий статус:\n"
                f"🎯 Целевая дата: {target_date.strftime('%d.%m.%Y')}\n"
                f"⏳ Осталось дней: {days_left}\n"
                f"📅 Частота напоминаний: {frequency}\n"
                f"📅 Сегодня: {now.strftime('%d.%m.%Y')}"
            )
        else:
            status_text = (
                f"🎉 Целевая дата достигнута!\n"
                f"📅 {target_date.strftime('%d.%m.%Y')} - этот день настал!"
            )

        await update.message.reply_text(status_text)

    async def stop_reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Остановить напоминания"""
        user_id = update.effective_user.id

        if user_id in user_data_store:
            if 'job' in user_data_store[user_id]:
                user_data_store[user_id]['job'].schedule_removal()
            del user_data_store[user_id]

            await update.message.reply_text(
                "✅ Напоминания остановлены!\n"
                "Используй /start чтобы начать заново."
            )
        else:
            await update.message.reply_text("❌ У тебя нет активных напоминаний.")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена текущей операции"""
        await update.message.reply_text(
            "❌ Операция отменена.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    def run_bot(self):
        """Запуск бота"""
        print("Бот запущен! Нажми Ctrl+C для остановки.")
        self.application.run_polling()


# Запуск бота
if __name__ == "__main__":
    BOT_TOKEN = "8385192761:AAHYEylTefdFqSS8nkNFIAmISUoSlJqE4S4"

    if BOT_TOKEN == "ТВОЙ_ТОКЕН_ЗДЕСЬ":
        print("❌ ОШИБКА: Замени 'ТВОЙ_ТОКЕН_ЗДЕСЬ' на реальный токен бота!")
    else:
        bot = CountdownBot()
        bot.run_bot()  # Теперь этот метод существует!