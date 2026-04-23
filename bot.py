import telebot
import os
import random
import datetime
import pytz
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.environ.get("TOKEN")
BOT_USERNAME = "Minesgameess_bot"  # ← замени на юзернейм бота без @

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

# ===== ХРАНИЛИЩЕ ПОЛЬЗОВАТЕЛЕЙ =====
user_data = {}
games = {}
temp_mode = {}
temp_mines = {}
waiting_for_custom_deposit = set()
waiting_for_withdraw_amount = set()

# ===== НАСТРОЙКИ ИГРЫ =====
MODES = {
    "3x3": {"rows": 3, "cols": 3},
    "5x5": {"rows": 5, "cols": 5},
    "10x10": {"rows": 10, "cols": 10},
}

START_BALANCE = 5
MIN_WITHDRAW = 50
# ==============================

# ID кастомных эмодзи
EMOJI_MINES = "5375445874988036618"
EMOJI_PROFILE = "5280781432824802048"
EMOJI_DEPOSIT = "5267500801240092311"
EMOJI_WITHDRAW = "5220064167356025824"
EMOJI_BONUS = "5449800250032143374"
EMOJI_SUPPORT = "5413623448440160154"

def get_or_create_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "reg_date": format_date_only(),
            "balance": START_BALANCE,
            "bet": 1,
            "total_games": 0,
            "mines_games": 0,
            "last_bonus": None,
            "transactions": [],
        }
    return user_data[user_id]

def generate_code():
    return f"#{random.randint(10000, 99999)}"

# ─── Логика игры ───────────────────────────────────────────

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

# ===== МЕНЮ (как у BlackrStars) =====
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    
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

def handle_menu(message):
    t = message.text
    if t == "Мины": mines_menu(message)
    elif t == "Профиль": profile(message)
    elif t == "Пополнить": deposit_menu_handler(message)
    elif t == "Вывести": withdraw_handler(message)
    elif t == "Бонус": daily_bonus(message)
    elif t == "Поддержка": support(message)

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

# ========== START ==========

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    ud = get_or_create_user(user_id)
    
    bot.send_message(
        user_id,
        f"👋 Добро пожаловать в Mines!\n"
        f"💰 Ваш баланс: {ud['balance']} ⭐\n\n"
        f"Выберите действие:",
        reply_markup=main_menu()
    )

# ========== ПРОФИЛЬ ==========

@bot.message_handler(func=lambda m: m.text == "Профиль")
def profile(message):
    user_id = message.chat.id
    ud = get_or_create_user(user_id)
    user = message.from_user
    
    dep_text = "Нет операций"
    wit_text = "Нет операций"
    
    deposits = [t for t in ud['transactions'] if t['type'] == 'deposit']
    if deposits:
        dep_text = "\n".join([f"{t['date']} | {t['amount']} ⭐ | {t['code']}" for t in deposits[-5:]])
    
    withdraws = [t for t in ud['transactions'] if t['type'] == 'withdraw']
    if withdraws:
        wit_text = "\n".join([f"{t['date']} | {t['amount']} ⭐ | {t['code']}" for t in withdraws[-5:]])
    
    bot.send_message(
        user_id,
        f"👤 *Профиль игрока*\n\n"
        f"🆔 ID: `{user.id}`\n"
        f"📅 Дата регистрации: {ud['reg_date']}\n"
        f"💰 Баланс: {ud['balance']} ⭐\n"
        f"🎮 Всего игр: {ud['total_games']}\n"
        f"💣 Игр в мины: {ud['mines_games']}\n\n"
        f"📥 *Пополнения:*\n{dep_text}\n\n"
        f"📤 *Выводы:*\n{wit_text}",
        parse_mode="Markdown"
    )

# ========== ПОПОЛНЕНИЕ ==========

def deposit_menu_handler(message):
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
    code = generate_code()
    ud = get_or_create_user(user_id)
    ud['balance'] += amount
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

def withdraw_handler(message):
    waiting_for_withdraw_amount.add(message.chat.id)
    bot.send_message(
        message.chat.id,
        f"💸 Введите сумму для вывода (минимум {MIN_WITHDRAW} ⭐):\n"
        "Для отмены напишите 'отмена'",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda m: m.chat.id in waiting_for_withdraw_amount and m.text and m.text.isdigit())
def withdraw_amount(message):
    amount = int(message.text)
    user_id = message.chat.id
    ud = get_or_create_user(user_id)
    
    if amount < MIN_WITHDRAW:
        bot.send_message(user_id, f"❌ Минимальная сумма вывода: {MIN_WITHDRAW} ⭐")
        return
    
    if ud['balance'] < amount:
        bot.send_message(user_id, f"❌ Недостаточно звёзд! Ваш баланс: {ud['balance']} ⭐")
        return
    
    code = generate_code()
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
    bot.send_message(message.chat.id, "📞 Поддержка пока не доступна")

# ========== ИГРА МИНЫ ==========

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

# ========== ЗАПУСК ==========

if __name__ == "__main__":
    print("✅ Бот запущен!")
    bot.remove_webhook()
    bot.infinity_polling()
