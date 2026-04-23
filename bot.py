import telebot
import os
import random
import datetime
import pytz
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.environ.get("TOKEN")
BOT_USERNAME = "YourMinesBot"  # ← замени на юзернейм бота без @

bot = telebot.TeleBot(TOKEN)

# ===== НАСТРОЙКА ВРЕМЕНИ =====
KYIV_TZ = pytz.timezone('Europe/Kiev')

def get_kyiv_time():
    return datetime.datetime.now(KYIV_TZ)

def format_kyiv_time(dt=None):
    if dt is None:
        dt = get_kyiv_time()
    return dt.strftime("%d.%m.%Y %H:%M")

def format_date_only(dt=None):
    if dt is None:
        dt = get_kyiv_time()
    return dt.strftime("%d.%m.%Y")
# ==============================

ADMINS = [6227572453, 6794644473]
user_orders = {}

order_counter = 1

# ===== ХРАНИЛИЩЕ ПОЛЬЗОВАТЕЛЕЙ =====
user_data = {}
total_stars_withdrawn = 0
support_tickets = {}
ticket_counter = 1

def get_or_create_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "reg_date": format_date_only(),
            "balance": 5,
            "bet": 1,
            "total_games": 0,
            "mines_games": 0,
            "last_bonus": None,
            "transactions": [],
            "bought_stars": 0,
        }
    return user_data[user_id]

def get_status(total_orders):
    if total_orders >= 50:
        return "💎 VIP клиент"
    elif total_orders >= 20:
        return "🥇 Золотой клиент"
    elif total_orders >= 10:
        return "🥈 Серебряный клиент"
    elif total_orders >= 3:
        return "🥉 Постоянный клиент"
    else:
        return "🥉 Обычный клиент"

def generate_order_number():
    global order_counter
    n = order_counter
    order_counter += 1
    return n

# ===== МЕНЮ =====
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    
    # ID кастомных эмодзи
    EMOJI_MINES = "5375445874988036618"
    EMOJI_PROFILE = "5280781432824802048"
    EMOJI_DEPOSIT = "5267500801240092311"
    EMOJI_WITHDRAW = "5220064167356025824"
    EMOJI_BONUS = "5449800250032143374"
    EMOJI_SUPPORT = "5413623448440160154"
    
    # Первый ряд - красный (Мины)
    markup.row(
        KeyboardButton("Мины", style="danger", icon_custom_emoji_id=EMOJI_MINES)
    )
    # Второй ряд - зеленый (Профиль) и синий (Пополнить)
    markup.row(
        KeyboardButton("Профиль", style="success", icon_custom_emoji_id=EMOJI_PROFILE),
        KeyboardButton("Пополнить", style="primary", icon_custom_emoji_id=EMOJI_DEPOSIT)
    )
    # Третий ряд - синий (Вывести) и зеленый (Бонус)
    markup.row(
        KeyboardButton("Вывести", style="primary", icon_custom_emoji_id=EMOJI_WITHDRAW),
        KeyboardButton("Бонус", style="success", icon_custom_emoji_id=EMOJI_BONUS)
    )
    # Четвертый ряд - красный (Поддержка)
    markup.row(
        KeyboardButton("Поддержка", style="danger", icon_custom_emoji_id=EMOJI_SUPPORT)
    )
    return markup

MENU_BUTTONS = ["Мины", "Профиль", "Пополнить", "Вывести", "Бонус", "Поддержка"]

# ===== НАСТРОЙКИ ИГРЫ =====
MODES = {
    "3x3": {"rows": 3, "cols": 3},
    "5x5": {"rows": 5, "cols": 5},
    "10x10": {"rows": 10, "cols": 10},
}

games = {}
temp_mode = {}
temp_mines = {}
waiting_for_custom_deposit = set()
waiting_for_withdraw_amount = set()

class MinesweeperGame:
    def __init__(self, rows, cols, mines, bet):
        self.rows = rows
        self.cols = cols
        self.mines_count = mines
        self.bet = bet
        self.board = [[0]*cols for _ in range(rows)]
        self.revealed = [[False]*cols for _ in range(rows)]
        self.game_over = False
        self.win = False
        self.safe_cells = rows * cols - mines
        self.revealed_count = 0
        self._place_mines()
        self._calc_numbers()

    def _place_mines(self):
        positions = random.sample(range(self.rows * self.cols), self.mines_count)
        for pos in positions:
            r, c = divmod(pos, self.cols)
            self.board[r][c] = -1

    def _calc_numbers(self):
        for r in range(self.rows):
            for c in range(self.cols):
                if self.board[r][c] == -1:
                    continue
                self.board[r][c] = sum(
                    1 for dr in (-1,0,1) for dc in (-1,0,1)
                    if 0 <= r+dr < self.rows and 0 <= c+dc < self.cols
                    and self.board[r+dr][c+dc] == -1
                )

    def open_cell(self, r, c):
        if self.revealed[r][c] or self.game_over:
            return 0
        self.revealed[r][c] = True
        if self.board[r][c] == -1:
            self.game_over = True
            return 0
        self.revealed_count += 1
        self._check_win()
        return self._calculate_profit()

    def _calculate_profit(self):
        if self.revealed_count == 0:
            return 0
        progress = self.revealed_count / self.safe_cells
        multiplier = 1 + (progress * (self.mines_count / self.safe_cells) * 5)
        return round(self.bet * multiplier, 1)

    def _check_win(self):
        if self.revealed_count >= self.safe_cells:
            self.win = True
            self.game_over = True

    def cell_symbol(self, r, c):
        if not self.revealed[r][c]:
            return "⬜"
        if self.board[r][c] == -1:
            return "💣"
        return "✅"

# ===== ИГРОВЫЕ КЛАВИАТУРЫ =====

def mode_select():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("3×3", callback_data="mode_3x3"),
        InlineKeyboardButton("5×5", callback_data="mode_5x5"),
        InlineKeyboardButton("10×10", callback_data="mode_10x10"),
    )
    return markup

def mines_select(rows, cols):
    if rows == 3 and cols == 3:
        options = [2, 3, 4, 5, 6, 7, 8]
    elif rows == 5 and cols == 5:
        options = [3, 5, 7, 10, 12, 15]
    elif rows == 10 and cols == 10:
        options = [5, 10, 15, 20, 25, 30]
    
    markup = InlineKeyboardMarkup()
    for i in range(0, len(options), 3):
        row_buttons = [
            InlineKeyboardButton(f"💣 {m}", callback_data=f"mines_{m}")
            for m in options[i:i+3]
        ]
        markup.row(*row_buttons)
    return markup

def bet_select(mines_count):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("⭐ 1", callback_data=f"bet_1_{mines_count}"),
        InlineKeyboardButton("⭐ 3", callback_data=f"bet_3_{mines_count}"),
        InlineKeyboardButton("⭐ 5", callback_data=f"bet_5_{mines_count}"),
    )
    markup.row(
        InlineKeyboardButton("⭐ 10", callback_data=f"bet_10_{mines_count}"),
        InlineKeyboardButton("⭐ 25", callback_data=f"bet_25_{mines_count}"),
        InlineKeyboardButton("⭐ 50", callback_data=f"bet_50_{mines_count}"),
    )
    return markup

def game_board(game):
    markup = InlineKeyboardMarkup()
    for r in range(game.rows):
        row_buttons = [
            InlineKeyboardButton(
                text=game.cell_symbol(r, c),
                callback_data=f"cell_{r}_{c}"
            ) for c in range(game.cols)
        ]
        markup.row(*row_buttons)
    markup.row(InlineKeyboardButton("🔄 Новая игра", callback_data="new_game"))
    markup.row(InlineKeyboardButton("💵 Забрать выигрыш", callback_data="cash_out"))
    return markup

def deposit_menu():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("⭐ 15", callback_data="dep_15"),
        InlineKeyboardButton("⭐ 30", callback_data="dep_30"),
        InlineKeyboardButton("⭐ 50", callback_data="dep_50"),
    )
    markup.row(
        InlineKeyboardButton("⭐ 100", callback_data="dep_100"),
        InlineKeyboardButton("⭐ 200", callback_data="dep_200"),
        InlineKeyboardButton("⭐ 500", callback_data="dep_500"),
    )
    markup.row(InlineKeyboardButton("✏️ Своя сумма", callback_data="dep_custom"))
    return markup

def support_inline_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("✉️ Написать", callback_data="support_write"))
    return markup

def support_cancel_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("❌ Отменить", callback_data="support_cancel"))
    return markup

def admin_reply_keyboard(user_id, ticket_id):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💬 Ответить", callback_data=f"admin_reply_{user_id}_{ticket_id}"),
        InlineKeyboardButton("✅ Закрыть тикет", callback_data=f"admin_close_{user_id}_{ticket_id}")
    )
    return markup

def support_reply_keyboard(ticket_id):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("❌ Закрыть тикет", callback_data=f"user_close_{ticket_id}"))
    return markup

# ========== START ==========

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    ud = get_or_create_user(user_id)

    bot.send_message(
        user_id,
        "👋 Добро пожаловать!\n💼 Выберите действие:",
        reply_markup=main_menu()
    )

# ========== ПРОФИЛЬ ==========

@bot.message_handler(func=lambda m: m.text == "Профиль")
def profile(message):
    user_id = message.chat.id
    ud = get_or_create_user(user_id)

    user_obj = message.from_user
    username_str = f"@{user_obj.username}" if user_obj.username else "не указан"

    reg_date = ud.get("reg_date", format_date_only())
    balance = ud.get("balance", 0)
    bought_stars = ud.get("bought_stars", 0)
    total_games = ud.get("total_games", 0)
    mines_games = ud.get("mines_games", 0)

    total_orders = bought_stars
    status = get_status(total_orders)

    # История транзакций
    dep_text = "Нет операций"
    wit_text = "Нет операций"
    
    deposits = [t for t in ud['transactions'] if t['type'] == 'deposit']
    if deposits:
        dep_text = "\n".join([f"{t['date']} | {t['amount']} ⭐ | {t['code']}" for t in deposits[-5:]])
    
    withdraws = [t for t in ud['transactions'] if t['type'] == 'withdraw']
    if withdraws:
        wit_text = "\n".join([f"{t['date']} | {t['amount']} ⭐ | {t['code']}" for t in withdraws[-5:]])

    profile_text = (
        f"👤 *Ваш профиль* 🌟\n\n"
        f"🆔 ID: `{user_id}` 🔑\n"
        f"👤 Имя пользователя: {username_str} 📛\n"
        f"📅 Дата регистрации: {reg_date} ⏰\n\n"
        f"💰 Баланс: *{balance} ⭐* ✨\n\n"
        f"🏆 Статус: {status}\n\n"
        f"📊 *Статистика:* 📈\n"
        f"🎮 Всего игр: *{total_games}*\n"
        f"💣 Игр в мины: *{mines_games}*\n"
        f"⭐️ Куплено звёзд: *{bought_stars}*\n\n"
        f"📥 *Пополнения:*\n{dep_text}\n\n"
        f"📤 *Выводы:*\n{wit_text}"
    )

    bot.send_message(user_id, profile_text, parse_mode="Markdown")

# ========== ПОПОЛНЕНИЕ ==========

@bot.message_handler(func=lambda m: m.text == "Пополнить")
def deposit_handler(message):
    bot.send_message(message.chat.id, "💎 Выберите сумму пополнения:", reply_markup=deposit_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith("dep_"))
def deposit_callback(call):
    if call.data == "dep_custom":
        waiting_for_custom_deposit.add(call.message.chat.id)
        bot.edit_message_text("✏️ Введите сумму пополнения (от 1 ⭐):", call.message.chat.id, call.message.message_id)
        return
    
    amount = int(call.data[4:])
    process_deposit(call.message, amount)

def process_deposit(message, amount):
    user_id = message.chat.id
    code = f"#{random.randint(10000, 99999)}"
    ud = get_or_create_user(user_id)
    ud['balance'] += amount
    ud['bought_stars'] += amount
    ud['transactions'].append({
        'type': 'deposit',
        'amount': amount,
        'date': format_kyiv_time(),
        'code': code
    })
    
    for admin_id in ADMINS:
        try:
            bot.send_message(
                admin_id,
                f"📥 *Новое пополнение!*\n"
                f"👤 Пользователь: `{user_id}`\n"
                f"💎 Сумма: {amount} ⭐\n"
                f"🔑 Код: {code}\n"
                f"📅 Дата: {format_kyiv_time()}",
                parse_mode="Markdown"
            )
        except:
            pass
    
    bot.send_message(user_id, f"✅ Пополнение на {amount} ⭐ успешно!\nКод: {code}")

@bot.message_handler(func=lambda m: m.chat.id in waiting_for_custom_deposit and m.text and m.text.isdigit())
def custom_deposit(message):
    amount = int(message.text)
    if amount < 1:
        bot.send_message(message.chat.id, "❌ Минимальная сумма пополнения: 1 ⭐")
        return
    
    waiting_for_custom_deposit.discard(message.chat.id)
    process_deposit(message, amount)

# ========== ВЫВОД ==========

@bot.message_handler(func=lambda m: m.text == "Вывести")
def withdraw_handler(message):
    waiting_for_withdraw_amount.add(message.chat.id)
    bot.send_message(
        message.chat.id,
        "💸 Введите сумму для вывода (минимум 50 ⭐):\n"
        "Для отмены напишите 'отмена'",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda m: m.chat.id in waiting_for_withdraw_amount and m.text and m.text.isdigit())
def withdraw_amount(message):
    amount = int(message.text)
    user_id = message.chat.id
    ud = get_or_create_user(user_id)
    
    if amount < 50:
        bot.send_message(user_id, "❌ Минимальная сумма вывода: 50 ⭐")
        return
    
    if ud['balance'] < amount:
        bot.send_message(user_id, f"❌ Недостаточно звёзд! Ваш баланс: {ud['balance']} ⭐")
        return
    
    code = f"#{random.randint(10000, 99999)}"
    ud['balance'] -= amount
    ud['transactions'].append({
        'type': 'withdraw',
        'amount': amount,
        'date': format_kyiv_time(),
        'code': code
    })
    
    for admin_id in ADMINS:
        try:
            bot.send_message(
                admin_id,
                f"📤 *Новый вывод!*\n"
                f"👤 Пользователь: `{user_id}`\n"
                f"💸 Сумма: {amount} ⭐\n"
                f"🔑 Код: {code}\n"
                f"📅 Дата: {format_kyiv_time()}",
                parse_mode="Markdown"
            )
        except:
            pass
    
    waiting_for_withdraw_amount.discard(user_id)
    bot.send_message(
        user_id,
        f"✅ Заявка на вывод {amount} ⭐ создана!\n"
        f"🔑 Код заявки: {code}\n"
        f"💰 Остаток баланса: {ud['balance']} ⭐"
    )

@bot.message_handler(func=lambda m: m.chat.id in waiting_for_withdraw_amount and m.text and m.text.lower() == 'отмена')
def cancel_withdraw(message):
    waiting_for_withdraw_amount.discard(message.chat.id)
    bot.send_message(message.chat.id, "❌ Вывод отменён")

# ========== БОНУС ==========

@bot.message_handler(func=lambda m: m.text == "Бонус")
def daily_bonus(message):
    user_id = message.chat.id
    ud = get_or_create_user(user_id)
    now = get_kyiv_time()
    
    if ud['last_bonus']:
        if isinstance(ud['last_bonus'], str):
            try:
                ud['last_bonus'] = datetime.datetime.strptime(ud['last_bonus'], "%Y-%m-%d %H:%M:%S%z")
            except:
                ud['last_bonus'] = datetime.datetime.strptime(ud['last_bonus'], "%Y-%m-%d %H:%M:%S")
                ud['last_bonus'] = KYIV_TZ.localize(ud['last_bonus'])
        
        time_diff = now - ud['last_bonus']
        if time_diff < datetime.timedelta(hours=24):
            remaining = datetime.timedelta(hours=24) - time_diff
            hours, remainder = divmod(remaining.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            bot.send_message(
                user_id,
                f"🎁 Ежедневный бонус уже получен!\n"
                f"Приходите через: {hours}ч {minutes}м {seconds}с"
            )
            return
    
    bonus = random.randint(1, 5)
    ud['balance'] += bonus
    ud['last_bonus'] = now.strftime("%Y-%m-%d %H:%M:%S%z")
    
    bot.send_message(
        user_id,
        f"🎁 Поздравляем! Вы получили {bonus} ⭐!\n"
        f"💰 Ваш баланс: {ud['balance']} ⭐"
    )

# ========== ПОДДЕРЖКА ==========

@bot.message_handler(func=lambda m: m.text == "Поддержка")
def support(message):
    bot.send_message(message.chat.id,
        "😊 *Есть вопросы?* Нажимай «Написать» — мы с радостью поможем! 😺\n\n"
        "🤔 *Частые вопросы:*\n\n"
        "1️⃣ *Сколько ждать выполнение заказа?*\n"
        "— Обычно от 5 до 70 минут.",
        reply_markup=support_inline_keyboard(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "support_write")
def support_write(call):
    global ticket_counter
    bot.answer_callback_query(call.id)
    ticket_id = ticket_counter
    ticket_counter += 1
    support_tickets[call.message.chat.id] = {
        "ticket_id": ticket_id, "status": "waiting_message",
        "user_id": call.message.chat.id,
        "username": f"@{call.from_user.username}" if call.from_user.username else f"ID: {call.message.chat.id}"
    }
    msg = bot.send_message(call.message.chat.id,
        f"📩 *Тикет #{ticket_id}*\n\nВведите ваш запрос:",
        reply_markup=support_cancel_keyboard(), parse_mode="Markdown")
    support_tickets[call.message.chat.id]["message_id"] = msg.message_id

@bot.callback_query_handler(func=lambda call: call.data == "support_cancel")
def support_cancel(call):
    bot.answer_callback_query(call.id)
    if call.message.chat.id in support_tickets:
        del support_tickets[call.message.chat.id]
    bot.edit_message_text("❌ *Запрос отменен*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    bot.send_message(call.message.chat.id,
        "😊 *Есть вопросы?* Нажимай «Написать»!\n\n1️⃣ *Сколько ждать заказ?*\n— От 5 до 70 минут.",
        reply_markup=support_inline_keyboard(), parse_mode="Markdown")

@bot.message_handler(
    func=lambda m: m.chat.id in support_tickets and support_tickets[m.chat.id].get("status") == "waiting_message",
    content_types=['text', 'photo', 'document'])
def handle_support_message(message):
    ticket_data = support_tickets[message.chat.id]
    ticket_id = ticket_data["ticket_id"]
    username = ticket_data["username"]
    try:
        bot.edit_message_reply_markup(message.chat.id, ticket_data["message_id"], reply_markup=None)
    except: pass
    bot.send_message(message.chat.id,
        f"✅ *Тикет #{ticket_id} отправлен!*\n⏳ Ожидайте ответа.",
        reply_markup=main_menu(), parse_mode="Markdown")
    admin_msg = (f"📩 *НОВЫЙ ТИКЕТ #{ticket_id}*\n━━━━━━━━━━━━━━━━━━\n"
                 f"👤 {username} | 🆔 `{message.chat.id}`\n━━━━━━━━━━━━━━━━━━\n")
    for admin_id in ADMINS:
        try:
            if message.content_type == 'text':
                bot.send_message(admin_id, admin_msg + f"💬 *Сообщение:*\n{message.text}",
                                 reply_markup=admin_reply_keyboard(message.chat.id, ticket_id), parse_mode="Markdown")
            elif message.content_type == 'photo':
                caption = message.caption or ""
                bot.send_photo(admin_id, message.photo[-1].file_id,
                               caption=admin_msg + "📸 Фото" + (f"\n{caption}" if caption else ""),
                               reply_markup=admin_reply_keyboard(message.chat.id, ticket_id), parse_mode="Markdown")
            elif message.content_type == 'document':
                bot.send_document(admin_id, message.document.file_id,
                                  caption=admin_msg + f"📎 `{message.document.file_name}`",
                                  reply_markup=admin_reply_keyboard(message.chat.id, ticket_id), parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка: {e}")
    support_tickets[message.chat.id]["status"] = "waiting_reply"

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_reply_"))
def admin_reply_start(call):
    if call.from_user.id not in ADMINS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!"); return
    bot.answer_callback_query(call.id)
    parts = call.data.split("_")
    user_id = int(parts[2])
    ticket_id = int(parts[3])
    msg = bot.send_message(call.message.chat.id,
                           f"💬 *Ответ на тикет #{ticket_id}*\n\nВведите ответ:",
                           parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_admin_reply, user_id, ticket_id)

def process_admin_reply(message, user_id, ticket_id):
    try:
        bot.send_message(user_id,
            f"💬 *Поддержка | Тикет #{ticket_id}*\n\n{message.text}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n📩 Чтобы ответить — напишите в этот чат.",
            parse_mode="Markdown", reply_markup=support_reply_keyboard(ticket_id))
        support_tickets[user_id] = {"ticket_id": ticket_id, "status": "waiting_user_reply", "user_id": user_id}
        bot.send_message(message.chat.id, f"✅ *Ответ отправлен!* Тикет #{ticket_id}", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "❌ *Ошибка!* Пользователь заблокировал бота.", parse_mode="Markdown")

@bot.message_handler(
    func=lambda m: m.chat.id in support_tickets and support_tickets[m.chat.id].get("status") == "waiting_user_reply",
    content_types=['text', 'photo', 'document'])
def handle_user_reply(message):
    ticket_data = support_tickets[message.chat.id]
    ticket_id = ticket_data["ticket_id"]
    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.chat.id}"
    support_tickets[message.chat.id]["status"] = "waiting_reply"
    bot.send_message(message.chat.id, f"✅ *Ответ отправлен!* Тикет #{ticket_id}", parse_mode="Markdown")
    admin_msg = (f"📩 *ОТВЕТ | Тикет #{ticket_id}*\n━━━━━━━━━━━━━━━━━━\n"
                 f"👤 {username} | 🆔 `{message.chat.id}`\n━━━━━━━━━━━━━━━━━━\n")
    for admin_id in ADMINS:
        try:
            if message.content_type == 'text':
                bot.send_message(admin_id, admin_msg + f"💬 {message.text}",
                                 reply_markup=admin_reply_keyboard(message.chat.id, ticket_id), parse_mode="Markdown")
            elif message.content_type == 'photo':
                bot.send_photo(admin_id, message.photo[-1].file_id, caption=admin_msg + "📸 Фото",
                               reply_markup=admin_reply_keyboard(message.chat.id, ticket_id), parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_close_"))
def admin_close_ticket(call):
    if call.from_user.id not in ADMINS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!"); return
    parts = call.data.split("_")
    user_id = int(parts[2])
    ticket_id = int(parts[3])
    if user_id in support_tickets: del support_tickets[user_id]
    try:
        bot.send_message(user_id, f"🔒 *Тикет #{ticket_id} закрыт*\n\nСпасибо за обращение!", parse_mode="Markdown")
    except: pass
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, f"✅ Тикет #{ticket_id} закрыт!")
    bot.send_message(call.message.chat.id, f"✅ *Тикет #{ticket_id} закрыт!*", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("user_close_"))
def user_close_ticket(call):
    ticket_id = int(call.data.split("_")[2])
    if call.message.chat.id in support_tickets: del support_tickets[call.message.chat.id]
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, "✅ Тикет закрыт!")
    bot.send_message(call.message.chat.id, f"🔒 *Тикет #{ticket_id} закрыт*\n\nСпасибо за обращение!", parse_mode="Markdown")

# ========== ИГРА МИНЫ ==========

@bot.message_handler(func=lambda m: m.text == "Мины")
def mines_menu(message):
    bot.send_message(message.chat.id, "🎯 Выберите размер поля:", reply_markup=mode_select())

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
def select_mode(call):
    mode = call.data[5:]
    rows, cols = MODES[mode]["rows"], MODES[mode]["cols"]
    temp_mode[call.message.chat.id] = (rows, cols)
    bot.edit_message_text(
        f"📏 Выбрано поле {rows}×{cols}\n"
        f"Выберите количество мин:",
        call.message.chat.id, call.message.message_id,
        reply_markup=mines_select(rows, cols)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("mines_"))
def select_mines(call):
    mines = int(call.data[6:])
    temp_mines[call.message.chat.id] = mines
    bot.edit_message_text(
        f"💣 Выбрано мин: {mines}\n"
        f"Выберите ставку:",
        call.message.chat.id, call.message.message_id,
        reply_markup=bet_select(mines)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("bet_"))
def start_game(call):
    _, bet, mines = call.data.split("_")
    bet = int(bet)
    mines = int(mines)
    user_id = call.message.chat.id
    
    ud = get_or_create_user(user_id)
    
    if ud["balance"] < bet:
        bot.answer_callback_query(call.id, f"❌ Недостаточно звёзд! Ваш баланс: {ud['balance']} ⭐", show_alert=True)
        return
    
    if user_id not in temp_mode:
        bot.answer_callback_query(call.id, "❌ Сначала выберите режим!", show_alert=True)
        return
    
    rows, cols = temp_mode[user_id]
    ud["balance"] -= bet
    ud["bet"] = bet
    ud["total_games"] += 1
    ud["mines_games"] += 1
    
    games[user_id] = MinesweeperGame(rows, cols, mines, bet)
    
    bot.edit_message_text(
        f"🎮 Игра началась!\n"
        f"📏 Поле: {rows}×{cols}\n"
        f"💣 Мин: {mines}\n"
        f"💰 Ставка: {bet} ⭐\n"
        f"💵 Баланс: {ud['balance']} ⭐\n\n"
        f"Нажимай на клетки!",
        user_id, call.message.message_id,
        reply_markup=game_board(games[user_id])
    )

@bot.callback_query_handler(func=lambda call: call.data == "cash_out")
def cash_out(call):
    user_id = call.message.chat.id
    game = games.get(user_id)
    
    if not game or game.game_over:
        bot.answer_callback_query(call.id, "Нет активной игры!", show_alert=True)
        return
    
    if game.revealed_count == 0:
        bot.answer_callback_query(call.id, "Откройте хотя бы одну клетку!", show_alert=True)
        return
    
    profit = game._calculate_profit()
    ud = get_or_create_user(user_id)
    ud["balance"] += profit
    game.game_over = True
    
    bot.edit_message_text(
        f"💵 Вы забрали выигрыш: +{profit} ⭐\n"
        f"💰 Ваш баланс: {ud['balance']} ⭐\n"
        f"📦 Открыто клеток: {game.revealed_count}/{game.safe_cells}",
        user_id, call.message.message_id,
        reply_markup=game_board(game)
    )
    bot.answer_callback_query(call.id, f"✅ +{profit} ⭐")

@bot.callback_query_handler(func=lambda call: call.data == "new_game")
def new_game(call):
    user_id = call.message.chat.id
    temp_mode.pop(user_id, None)
    temp_mines.pop(user_id, None)
    bot.edit_message_text(
        "🎯 Выберите размер поля:",
        user_id, call.message.message_id,
        reply_markup=mode_select()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("cell_"))
def on_cell(call):
    user_id = call.message.chat.id
    game = games.get(user_id)
    
    if not game or game.game_over:
        bot.answer_callback_query(call.id, "Начни новую игру!", show_alert=True)
        return
    
    _, r, c = call.data.split("_")
    profit = game.open_cell(int(r), int(c))
    ud = get_or_create_user(user_id)
    
    if game.win:
        total_win = game.bet * 3
        ud["balance"] += total_win
        bot.edit_message_text(
            f"🎉 Победа! Вы открыли все безопасные клетки!\n"
            f"💰 Выигрыш: +{total_win} ⭐\n"
            f"💰 Баланс: {ud['balance']} ⭐",
            user_id, call.message.message_id,
            reply_markup=game_board(game)
        )
    elif game.game_over:
        bot.edit_message_text(
            f"💥 Вы подорвался на мине!\n"
            f"❌ Потеряно: {game.bet} ⭐\n"
            f"💰 Баланс: {ud['balance']} ⭐",
            user_id, call.message.message_id,
            reply_markup=game_board(game)
        )
    else:
        current_profit = game._calculate_profit()
        bot.edit_message_text(
            f"🎮 Игра продолжается\n"
            f"📦 Открыто: {game.revealed_count}/{game.safe_cells}\n"
            f"💵 Можно забрать: {current_profit} ⭐",
            user_id, call.message.message_id,
            reply_markup=game_board(game)
        )
    bot.answer_callback_query(call.id)

# ========== АДМИН-ПАНЕЛЬ ==========

banned_users = set()

def is_user_banned(user_id):
    return user_id in banned_users

def admin_panel_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🚫 Заблокировать пользователя", callback_data="admin_ban"),
        InlineKeyboardButton("✅ Разблокировать пользователя", callback_data="admin_unban"),
        InlineKeyboardButton("📢 Рассылка всем пользователям", callback_data="admin_broadcast"),
        InlineKeyboardButton("💬 Написать пользователю", callback_data="admin_message"),
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")
    )
    return markup

def admin_back_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="admin_back"))
    return markup

@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.from_user.id not in ADMINS:
        bot.send_message(message.chat.id, "❌ У вас нет доступа к админ-панели!")
        return
    
    bot.send_message(
        message.chat.id,
        "🔐 *Админ-панель*\n\nВыберите действие:",
        reply_markup=admin_panel_keyboard(),
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == "!admin")
def admin_text_command(message):
    admin_command(message)

admin_states = {}

@bot.callback_query_handler(func=lambda call: call.data == "admin_ban")
def admin_ban_start(call):
    if call.from_user.id not in ADMINS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!"); return
    bot.answer_callback_query(call.id)
    admin_states[call.from_user.id] = {"action": "ban", "step": "waiting_id"}
    msg = bot.send_message(call.message.chat.id,
        "🚫 *Блокировка пользователя*\n\nВведите ID пользователя для блокировки:\n_(или перешлите сообщение от пользователя)_",
        reply_markup=admin_back_keyboard(), parse_mode="Markdown")
    admin_states[call.from_user.id]["msg_id"] = msg.message_id

@bot.callback_query_handler(func=lambda call: call.data == "admin_unban")
def admin_unban_start(call):
    if call.from_user.id not in ADMINS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!"); return
    bot.answer_callback_query(call.id)
    admin_states[call.from_user.id] = {"action": "unban", "step": "waiting_id"}
    msg = bot.send_message(call.message.chat.id,
        "✅ *Разблокировка пользователя*\n\nВведите ID пользователя для разблокировки:",
        reply_markup=admin_back_keyboard(), parse_mode="Markdown")
    admin_states[call.from_user.id]["msg_id"] = msg.message_id

@bot.message_handler(func=lambda m: m.from_user.id in ADMINS and 
                     m.from_user.id in admin_states and 
                     admin_states[m.from_user.id].get("step") == "waiting_id")
def process_admin_user_id(message):
    admin_id = message.from_user.id
    state = admin_states[admin_id]
    action = state["action"]
    
    user_id = None
    if message.forward_from:
        user_id = message.forward_from.id
    elif message.text:
        try:
            user_id = int(message.text.strip())
        except:
            pass
    
    if not user_id:
        msg = bot.send_message(message.chat.id,
            "❌ Не удалось определить ID пользователя!\nВведите числовой ID или перешлите сообщение от пользователя:",
            reply_markup=admin_back_keyboard())
        admin_states[admin_id]["msg_id"] = msg.message_id
        return
    
    if action == "ban":
        if user_id in ADMINS:
            bot.send_message(message.chat.id, "❌ *Невозможно заблокировать администратора!*",
                reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
        elif user_id in banned_users:
            bot.send_message(message.chat.id, f"⚠️ *Пользователь `{user_id}` уже заблокирован!*",
                reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
        else:
            banned_users.add(user_id)
            bot.send_message(message.chat.id, f"✅ *Пользователь `{user_id}` заблокирован!*",
                reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
            try:
                bot.send_message(user_id, "🚫 *Ваш аккаунт заблокирован администратором.*\n\nДля разблокировки обратитесь в поддержку.", parse_mode="Markdown")
            except: pass
    elif action == "unban":
        if user_id in banned_users:
            banned_users.remove(user_id)
            bot.send_message(message.chat.id, f"✅ *Пользователь `{user_id}` разблокирован!*",
                reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
            try:
                bot.send_message(user_id, "✅ *Ваш аккаунт разблокирован!*\n\nТеперь вы снова можете пользоваться ботом.", parse_mode="Markdown")
            except: pass
        else:
            bot.send_message(message.chat.id, f"⚠️ *Пользователь `{user_id}` не заблокирован!*",
                reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
    
    del admin_states[admin_id]

@bot.message_handler(func=lambda m: is_user_banned(m.from_user.id))
def blocked_user_handler(message):
    bot.send_message(message.chat.id, "🚫 *Ваш аккаунт заблокирован.*\n\nДля разблокировки обратитесь в поддержку.", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast_start(call):
    if call.from_user.id not in ADMINS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!"); return
    bot.answer_callback_query(call.id)
    admin_states[call.from_user.id] = {"action": "broadcast", "step": "waiting_message"}
    msg = bot.send_message(call.message.chat.id,
        "📢 *Рассылка всем пользователям*\n\nОтправьте сообщение для рассылки (текст, фото, видео или документ):",
        reply_markup=admin_back_keyboard(), parse_mode="Markdown")
    admin_states[call.from_user.id]["msg_id"] = msg.message_id

@bot.message_handler(func=lambda m: m.from_user.id in ADMINS and 
                     m.from_user.id in admin_states and 
                     admin_states[m.from_user.id].get("action") == "broadcast" and
                     admin_states[m.from_user.id].get("step") == "waiting_message",
                     content_types=['text', 'photo', 'video', 'document'])
def process_broadcast_message(message):
    admin_id = message.from_user.id
    all_users = list(user_data.keys())
    success_count = 0
    fail_count = 0
    
    bot.send_message(message.chat.id, f"📢 *Начинаю рассылку...*\n\n👥 Всего пользователей: *{len(all_users)}*", parse_mode="Markdown")
    
    for user_id in all_users:
        if user_id in banned_users:
            continue
        try:
            if message.content_type == 'text':
                bot.send_message(user_id, f"📢 *Рассылка*\n\n{message.text}", parse_mode="Markdown")
            elif message.content_type == 'photo':
                bot.send_photo(user_id, message.photo[-1].file_id,
                    caption=f"📢 *Рассылка*\n\n{message.caption or ''}", parse_mode="Markdown")
            elif message.content_type == 'video':
                bot.send_video(user_id, message.video.file_id,
                    caption=f"📢 *Рассылка*\n\n{message.caption or ''}", parse_mode="Markdown")
            elif message.content_type == 'document':
                bot.send_document(user_id, message.document.file_id,
                    caption=f"📢 *Рассылка*\n\n{message.caption or ''}", parse_mode="Markdown")
            success_count += 1
        except:
            fail_count += 1
    
    bot.send_message(message.chat.id,
        f"✅ *Рассылка завершена!*\n\n📨 Успешно отправлено: *{success_count}*\n❌ Ошибок: *{fail_count}*",
        reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
    del admin_states[admin_id]

@bot.callback_query_handler(func=lambda call: call.data == "admin_message")
def admin_message_start(call):
    if call.from_user.id not in ADMINS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!"); return
    bot.answer_callback_query(call.id)
    admin_states[call.from_user.id] = {"action": "message", "step": "waiting_id"}
    msg = bot.send_message(call.message.chat.id,
        "💬 *Написать пользователю*\n\nВведите ID пользователя:\n_(или перешлите сообщение от пользователя)_",
        reply_markup=admin_back_keyboard(), parse_mode="Markdown")
    admin_states[call.from_user.id]["msg_id"] = msg.message_id

@bot.message_handler(func=lambda m: m.from_user.id in ADMINS and 
                     m.from_user.id in admin_states and 
                     admin_states[m.from_user.id].get("action") == "message" and
                     admin_states[m.from_user.id].get("step") == "waiting_id")
def process_message_user_id(message):
    admin_id = message.from_user.id
    state = admin_states[admin_id]
    user_id = None
    if message.forward_from:
        user_id = message.forward_from.id
    elif message.text:
        try: user_id = int(message.text.strip())
        except: pass
    
    if not user_id:
        msg = bot.send_message(message.chat.id,
            "❌ Не удалось определить ID пользователя!\nВведите числовой ID или перешлите сообщение от пользователя:",
            reply_markup=admin_back_keyboard())
        admin_states[admin_id]["msg_id"] = msg.message_id
        return
    
    state["target_user_id"] = user_id
    state["step"] = "waiting_message"
    admin_states[admin_id] = state
    
    user_info = user_data.get(user_id, {})
    reg_date = user_info.get("reg_date", "неизвестно")
    bought_stars = user_info.get("bought_stars", 0)
    is_banned = "🚫 Да" if user_id in banned_users else "✅ Нет"
    
    msg = bot.send_message(message.chat.id,
        f"💬 *Написать пользователю*\n\n"
        f"🆔 ID: `{user_id}`\n📅 Регистрация: {reg_date}\n"
        f"🚫 Заблокирован: {is_banned}\n⭐️ Куплено Stars: {bought_stars}\n\n"
        f"Отправьте сообщение для пользователя:",
        reply_markup=admin_back_keyboard(), parse_mode="Markdown")
    admin_states[admin_id]["msg_id"] = msg.message_id

@bot.message_handler(func=lambda m: m.from_user.id in ADMINS and 
                     m.from_user.id in admin_states and 
                     admin_states[m.from_user.id].get("action") == "message" and
                     admin_states[m.from_user.id].get("step") == "waiting_message",
                     content_types=['text', 'photo', 'video', 'document'])
def process_admin_user_message(message):
    admin_id = message.from_user.id
    state = admin_states[admin_id]
    user_id = state["target_user_id"]
    
    try:
        if message.content_type == 'text':
            bot.send_message(user_id, f"💬 *Сообщение от администратора*\n\n{message.text}", parse_mode="Markdown")
        elif message.content_type == 'photo':
            bot.send_photo(user_id, message.photo[-1].file_id,
                caption=f"💬 *Сообщение от администратора*\n\n{message.caption or ''}", parse_mode="Markdown")
        elif message.content_type == 'video':
            bot.send_video(user_id, message.video.file_id,
                caption=f"💬 *Сообщение от администратора*\n\n{message.caption or ''}", parse_mode="Markdown")
        elif message.content_type == 'document':
            bot.send_document(user_id, message.document.file_id,
                caption=f"💬 *Сообщение от администратора*\n\n{message.caption or ''}", parse_mode="Markdown")
        bot.send_message(message.chat.id, f"✅ *Сообщение отправлено пользователю `{user_id}`!*",
            reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id,
            f"❌ *Ошибка отправки сообщения!*\n\nВозможно, пользователь заблокировал бота.\nОшибка: {str(e)[:100]}",
            reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
    del admin_states[admin_id]

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats(call):
    if call.from_user.id not in ADMINS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!"); return
    bot.answer_callback_query(call.id)
    
    total_users = len(user_data)
    total_stars_bought = sum(ud.get("bought_stars", 0) for ud in user_data.values())
    total_games = sum(ud.get("total_games", 0) for ud in user_data.values())
    banned_count = len(banned_users)
    
    top_users = sorted(
        [(uid, ud.get("bought_stars", 0)) for uid, ud in user_data.items()],
        key=lambda x: x[1], reverse=True
    )[:5]
    
    top_text = "".join([f"{i}. `{uid}` — *{stars} ⭐*\n" for i, (uid, stars) in enumerate(top_users, 1) if stars > 0])
    if not top_text: top_text = "Пока нет данных"
    
    stats_text = (
        f"📊 *СТАТИСТИКА БОТА*\n\n"
        f"👥 *Пользователи:*\n├ Всего: *{total_users}*\n├ Заблокировано: *{banned_count}*\n\n"
        f"💰 *Продажи:*\n└ ⭐️ Stars: *{total_stars_bought}* шт\n\n"
        f"🎮 *Игр сыграно:* *{total_games}*\n"
        f"📦 *Заказов:* *{order_counter - 1}*\n\n"
        f"🏆 *Топ-5 по Stars:*\n{top_text}"
    )
    
    bot.send_message(call.message.chat.id, stats_text,
        reply_markup=admin_panel_keyboard(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_back")
def admin_back(call):
    if call.from_user.id not in ADMINS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!"); return
    bot.answer_callback_query(call.id)
    if call.from_user.id in admin_states: del admin_states[call.from_user.id]
    try:
        bot.edit_message_text("🔐 *Админ-панель*\n\nВыберите действие:",
            call.message.chat.id, call.message.message_id,
            reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
    except:
        bot.send_message(call.message.chat.id, "🔐 *Админ-панель*\n\nВыберите действие:",
            reply_markup=admin_panel_keyboard(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_close")
def admin_close(call):
    if call.from_user.id not in ADMINS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!"); return
    bot.answer_callback_query(call.id)
    if call.from_user.id in admin_states: del admin_states[call.from_user.id]
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    bot.send_message(call.message.chat.id, "✅ Админ-панель закрыта.", reply_markup=main_menu())

# ========== ЗАПУСК ==========

if __name__ == "__main__":
    print("✅ Бот запущен!")
    bot.remove_webhook()
    bot.infinity_polling()
