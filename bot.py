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

MODES = {
    "3x3":   {"rows": 3,  "cols": 3,  "mines": 2},
    "5x5":   {"rows": 5,  "cols": 5,  "mines": 5},
    "10x10": {"rows": 10, "cols": 10, "mines": 15},
}

# ─── Логика игры ───────────────────────────────────────────

class MinesweeperGame:
    def __init__(self, rows, cols, mines):
        self.rows = rows
        self.cols = cols
        self.mines_count = mines
        self.board    = [[0]*cols for _ in range(rows)]
        self.revealed = [[False]*cols for _ in range(rows)]
        self.game_over = False
        self.win = False
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
            return
        self.revealed[r][c] = True
        if self.board[r][c] == -1:
            self.game_over = True
            return
        if self.board[r][c] == 0:
            for dr in (-1,0,1):
                for dc in (-1,0,1):
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < self.rows and 0 <= nc < self.cols:
                        self.open_cell(nr, nc)
        self._check_win()

    def _check_win(self):
        for r in range(self.rows):
            for c in range(self.cols):
                if self.board[r][c] != -1 and not self.revealed[r][c]:
                    return
        self.win = True
        self.game_over = True

    def cell_symbol(self, r, c):
        if not self.revealed[r][c]:
            return "⬜"
        if self.board[r][c] == -1:
            return "💣"  # мина
        return "✅"  # безопасная открытая ячейка

# ─── Клавиатуры ────────────────────────────────────────────

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="💣 Мины")]],
        resize_keyboard=True
    )

def mode_select():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="3×3 (легко)",    callback_data="mode_3x3")],
        [InlineKeyboardButton(text="5×5 (средне)",   callback_data="mode_5x5")],
        [InlineKeyboardButton(text="10×10 (сложно)", callback_data="mode_10x10")],
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
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ─── Бот ───────────────────────────────────────────────────

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
games: dict[int, MinesweeperGame] = {}

@dp.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.answer("Привет! Выбери игру 👇", reply_markup=main_menu())

@dp.message(F.text == "💣 Мины")
async def minesweeper_menu(msg: Message):
    await msg.answer("Выбери размер поля:", reply_markup=mode_select())

@dp.callback_query(F.data.startswith("mode_"))
async def start_game(call: CallbackQuery):
    cfg = MODES[call.data[5:]]
    games[call.from_user.id] = MinesweeperGame(**cfg)
    await call.message.edit_text("Нажимай на клетки! ⬜", reply_markup=game_board(games[call.from_user.id]))

@dp.callback_query(F.data == "new_game")
async def new_game(call: CallbackQuery):
    await call.message.edit_text("Выбери размер поля:", reply_markup=mode_select())

@dp.callback_query(F.data.startswith("cell_"))
async def on_cell(call: CallbackQuery):
    game = games.get(call.from_user.id)
    if not game or game.game_over:
        await call.answer("Начни новую игру!")
        return
    _, r, c = call.data.split("_")
    game.open_cell(int(r), int(c))
    if game.win:
        await call.message.edit_text("🎉 Победа!", reply_markup=game_board(game))
    elif game.game_over:
        await call.message.edit_text("💥 Ты подорвался!", reply_markup=game_board(game))
    else:
        await call.message.edit_reply_markup(reply_markup=game_board(game))
    await call.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
