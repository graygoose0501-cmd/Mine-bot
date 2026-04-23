import asyncio
import random
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Конфигурация режимов
MODES = {
    "3x3": {"rows": 3, "cols": 3},
    "5x5": {"rows": 5, "cols": 5},
    "10x10": {"rows": 10, "cols": 10},
}

# Начальный баланс звёзд
START_BALANCE = 5

# База данных игроков (в памяти)
players: dict[int, dict] = {}

def get_player(user_id: int) -> dict:
    if user_id not in players:
        players[user_id] = {"balance": START_BALANCE, "bet": 1}
    return players[user_id]

# ─── Логика игры ───────────────────────────────────────────

class MinesweeperGame:
    def __init__(self, rows, cols, mines, bet):
        self.rows = rows
        self.cols = cols
        self.mines_count = mines
        self.bet = bet
        self.board    = [[0]*cols for _ in range(rows)]
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
        """Открывает только одну клетку (без авто-открытия соседних)"""
        if self.revealed[r][c] or self.game_over:
            return 0
        
        self.revealed[r][c] = True
        
        if self.board[r][c] == -1:
            self.game_over = True
            return 0  # проигрыш
        
        self.revealed_count += 1
        self._check_win()
        
        return self._calculate_profit()

    def _calculate_profit(self):
        """Расчёт прибыли в зависимости от прогресса"""
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
        return "✅"  # все безопасные клетки - одинаковый значок

# ─── Клавиатуры ────────────────────────────────────────────

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💣 Мины")],
            [KeyboardButton(text="💰 Баланс")],
        ],
        resize_keyboard=True
    )

def mode_select():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="3×3", callback_data="mode_3x3")],
        [InlineKeyboardButton(text="5×5", callback_data="mode_5x5")],
        [InlineKeyboardButton(text="10×10", callback_data="mode_10x10")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")],
    ])

def mines_select(rows, cols):
    """Кнопки выбора количества мин"""
    if rows == 3 and cols == 3:
        options = [2, 3, 4, 5, 6, 7, 8]
    elif rows == 5 and cols == 5:
        options = [3, 5, 7, 10, 12, 15]
    elif rows == 10 and cols == 10:
        options = [5, 10, 15, 20, 25, 30]
    
    mines_options = []
    for i in range(0, len(options), 3):
        row = [
            InlineKeyboardButton(
                text=f"💣 {m}", 
                callback_data=f"mines_{m}"
            ) for m in options[i:i+3]
        ]
        mines_options.append(row)
    
    mines_options.append([
        InlineKeyboardButton(text="🔙 К режимам", callback_data="back_to_modes")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=mines_options)

def bet_select(mines_count):
    """Выбор ставки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ 1", callback_data=f"bet_1_{mines_count}"),
            InlineKeyboardButton(text="⭐ 3", callback_data=f"bet_3_{mines_count}"),
            InlineKeyboardButton(text="⭐ 5", callback_data=f"bet_5_{mines_count}"),
        ],
        [
            InlineKeyboardButton(text="⭐ 10", callback_data=f"bet_10_{mines_count}"),
            InlineKeyboardButton(text="⭐ 25", callback_data=f"bet_25_{mines_count}"),
            InlineKeyboardButton(text="⭐ 50", callback_data=f"bet_50_{mines_count}"),
        ],
        [InlineKeyboardButton(text="🔙 К выбору мин", callback_data="back_to_mines")],
    ])

def game_board(game: MinesweeperGame):
    buttons = []
    for r in range(game.rows):
        row = [
            InlineKeyboardButton(
                text=game.cell_symbol(r, c),
                callback_data=f"cell_{r}_{c}"
            ) for c in range(game.cols)
        ]
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔄 Новая игра", callback_data="new_game")])
    buttons.append([InlineKeyboardButton(text="💵 Забрать выигрыш", callback_data="cash_out")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ─── Бот ───────────────────────────────────────────────────

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
games: dict[int, MinesweeperGame] = {}
temp_mode: dict[int, tuple] = {}
temp_mines: dict[int, int] = {}

@dp.message(CommandStart())
async def cmd_start(msg: Message):
    player = get_player(msg.from_user.id)
    await msg.answer(
        f"🎮 Добро пожаловать в Mines!\n"
        f"💰 Ваш баланс: {player['balance']} ⭐\n"
        f"Выбери игру 👇",
        reply_markup=main_menu()
    )

@dp.message(F.text == "💰 Баланс")
async def show_balance(msg: Message):
    player = get_player(msg.from_user.id)
    await msg.answer(f"💰 Ваш баланс: {player['balance']} ⭐")

@dp.message(F.text == "💣 Мины")
async def minesweeper_menu(msg: Message):
    await msg.answer("🎯 Выберите размер поля:", reply_markup=mode_select())

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery):
    await call.message.edit_text("🎯 Выберите размер поля:", reply_markup=mode_select())

@dp.callback_query(F.data == "back_to_modes")
async def back_to_modes(call: CallbackQuery):
    temp_mode.pop(call.from_user.id, None)
    await call.message.edit_text("🎯 Выберите размер поля:", reply_markup=mode_select())

@dp.callback_query(F.data == "back_to_mines")
async def back_to_mines(call: CallbackQuery):
    temp_mines.pop(call.from_user.id, None)
    if call.from_user.id in temp_mode:
        rows, cols = temp_mode[call.from_user.id]
        await call.message.edit_text(
            f"📏 Поле {rows}×{cols}\nВыберите количество мин:",
            reply_markup=mines_select(rows, cols)
        )

@dp.callback_query(F.data.startswith("mode_"))
async def select_mode(call: CallbackQuery):
    mode = call.data[5:]
    rows, cols = MODES[mode]["rows"], MODES[mode]["cols"]
    temp_mode[call.from_user.id] = (rows, cols)
    await call.message.edit_text(
        f"📏 Выбрано поле {rows}×{cols}\n"
        f"Выберите количество мин:",
        reply_markup=mines_select(rows, cols)
    )

@dp.callback_query(F.data.startswith("mines_"))
async def select_mines(call: CallbackQuery):
    mines = int(call.data[6:])
    temp_mines[call.from_user.id] = mines
    await call.message.edit_text(
        f"💣 Выбрано мин: {mines}\n"
        f"Выберите ставку:",
        reply_markup=bet_select(mines)
    )

@dp.callback_query(F.data.startswith("bet_"))
async def start_game(call: CallbackQuery):
    _, bet, mines = call.data.split("_")
    bet = int(bet)
    mines = int(mines)
    
    player = get_player(call.from_user.id)
    
    if player["balance"] < bet:
        await call.answer(f"❌ Недостаточно звёзд! Ваш баланс: {player['balance']} ⭐", show_alert=True)
        return
    
    if call.from_user.id not in temp_mode:
        await call.answer("❌ Сначала выберите режим!", show_alert=True)
        return
    
    rows, cols = temp_mode[call.from_user.id]
    player["balance"] -= bet
    player["bet"] = bet
    
    games[call.from_user.id] = MinesweeperGame(rows, cols, mines, bet)
    
    await call.message.edit_text(
        f"🎮 Игра началась!\n"
        f"📏 Поле: {rows}×{cols}\n"
        f"💣 Мин: {mines}\n"
        f"💰 Ставка: {bet} ⭐\n"
        f"💵 Баланс: {player['balance']} ⭐\n\n"
        f"Нажимай на клетки!",
        reply_markup=game_board(games[call.from_user.id])
    )

@dp.callback_query(F.data == "cash_out")
async def cash_out(call: CallbackQuery):
    """Забрать текущий выигрыш"""
    game = games.get(call.from_user.id)
    if not game or game.game_over:
        await call.answer("Нет активной игры!", show_alert=True)
        return
    
    if game.revealed_count == 0:
        await call.answer("Откройте хотя бы одну клетку!", show_alert=True)
        return
    
    profit = game._calculate_profit()
    player = get_player(call.from_user.id)
    player["balance"] += profit
    game.game_over = True
    
    await call.message.edit_text(
        f"💵 Вы забрали выигрыш: +{profit} ⭐\n"
        f"💰 Ваш баланс: {player['balance']} ⭐\n"
        f"📦 Открыто клеток: {game.revealed_count}/{game.safe_cells}",
        reply_markup=game_board(game)
    )
    await call.answer(f"✅ +{profit} ⭐")

@dp.callback_query(F.data == "new_game")
async def new_game(call: CallbackQuery):
    temp_mode.pop(call.from_user.id, None)
    temp_mines.pop(call.from_user.id, None)
    await call.message.edit_text("🎯 Выберите размер поля:", reply_markup=mode_select())

@dp.callback_query(F.data.startswith("cell_"))
async def on_cell(call: CallbackQuery):
    game = games.get(call.from_user.id)
    if not game or game.game_over:
        await call.answer("Начни новую игру!", show_alert=True)
        return
    
    _, r, c = call.data.split("_")
    profit = game.open_cell(int(r), int(c))
    player = get_player(call.from_user.id)
    
    if game.win:
        total_win = game.bet * 3
        player["balance"] += total_win
        await call.message.edit_text(
            f"🎉 Победа! Вы открыли все безопасные клетки!\n"
            f"💰 Выигрыш: +{total_win} ⭐\n"
            f"💰 Баланс: {player['balance']} ⭐",
            reply_markup=game_board(game)
        )
    elif game.game_over:
        await call.message.edit_text(
            f"💥 Вы подорвался на мине!\n"
            f"❌ Потеряно: {game.bet} ⭐\n"
            f"💰 Баланс: {player['balance']} ⭐",
            reply_markup=game_board(game)
        )
    else:
        current_profit = game._calculate_profit()
        await call.message.edit_text(
            f"🎮 Игра продолжается\n"
            f"📦 Открыто: {game.revealed_count}/{game.safe_cells}\n"
            f"💵 Можно забрать: {current_profit} ⭐",
            reply_markup=game_board(game)
        )
    await call.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
