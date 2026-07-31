# -*- coding: utf-8 -*-
"""
MM2 SHOP — Telegram-бот для продажи скинов Murder Mystery 2
aiogram 3.x + SQLite + aiohttp (Render Free Web Service)
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv("8872095546:AAFDfftRhZhhU4R4pz1carnGvtEFmJnSgtg")
ADMIN_ID = int(os.getenv("8822297551", "0"))
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "shop.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан!")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("mm2_shop")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ==================== ТОВАРЫ ====================
SETS = {
    "Celestial Set": 1650, "Alien set": 1450, "Sakura set": 1250,
    "Sun set": 1200, "Snow set": 1100, "Bauble set": 550,
    "Bloom set": 750, "Ocean set": 700, "Xeno set": 650,
    "FlowerWood set": 700, "Corrupt set": 550, "Pearl set": 200,
    "Bat set": 150, "Beach Set": 500, "Borealis set": 150,
    "Ice set": 350, "Candy set": 400, "Spectre set": 150,
    "Blizzard set": 700, "Full Elderwood set": 200,
}

ANCIENTS = {
    "Celestial": 750, "Vampire's Axe": 550, "Harvester": 175,
    "Icepiercer": 150, "Icebreaker": 85, "Icewing": 25,
}

CHROMAS = {
    "Chroma Heart Wand": 1450, "Chroma Watergun": 1150,
    "Chroma Sweet": 900, "Chroma Treat": 900,
    "Chroma Beachy": 950, "Chroma Sands": 950,
    "Chroma Ornament": 750, "Chroma DarkBringer": 100,
    "Chroma LightBringer": 100, "Chroma Luger": 85,
    "Chroma Laser": 80, "Chroma Swirly Gun": 75,
}

GODLIES_ALL = {
    "Constellation": 700, "Turkey": 700, "Alien Beam": 675,
    "DarkShot": 630, "DarkSword": 600, "RayGun": 700,
    "Blossom": 700, "Sakura": 590, "SnowCannon": 500,
    "Sunrise": 575, "Bauble": 400, "Sunset": 500,
    "Soul": 550, "Spirit": 550, "Rainbow Gun": 400,
    "Rainbow": 400, "Flora": 300, "Bloom": 350,
    "Heart Wand": 325, "Ocean": 275, "Waves": 270,
    "IceCream": 400, "XenoKnife": 300, "Xenoshot": 270,
    "FlowerWood Gun": 195, "Flowerwood": 175, "Snow Storm": 350,
    "Beachy": 300, "Sands": 300, "Treat": 250,
    "Sweet": 250, "Borealis": 100, "Australis": 100,
    "Bat": 100, "Pearl": 85, "WaterGun": 250,
    "PearlShine": 85, "Candy": 85, "HeartBlade": 80,
    "Luger": 50, "RedLuger": 50,
}

GODLIES_PER_PAGE = 15
GODLIES_NAMES = list(GODLIES_ALL.keys())
GODLIES_TOTAL_PAGES = (len(GODLIES_NAMES) + GODLIES_PER_PAGE - 1) // GODLIES_PER_PAGE

def get_godlies_page(page: int) -> dict:
    page = max(0, min(page, GODLIES_TOTAL_PAGES - 1))
    start = page * GODLIES_PER_PAGE
    end = start + GODLIES_PER_PAGE
    names = GODLIES_NAMES[start:end]
    return {n: GODLIES_ALL[n] for n in names}

ALL_PRODUCTS: dict = {}
ALL_PRODUCTS.update(SETS)
ALL_PRODUCTS.update(ANCIENTS)
ALL_PRODUCTS.update(CHROMAS)
ALL_PRODUCTS.update(GODLIES_ALL)

# ==================== БАЗА ДАННЫХ ====================
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("DB error: %s\n%s", e, traceback.format_exc())
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS carts (
                user_id INTEGER PRIMARY KEY,
                items TEXT NOT NULL DEFAULT '[]'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                items TEXT NOT NULL,
                total INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY,
                banned_at TEXT NOT NULL
            )
        """)
        conn.commit()
    logger.info("БД инициализирована: %s", DB_PATH)

def is_banned(user_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute("SELECT 1 FROM banned_users WHERE user_id = ?", (user_id,)).fetchone()
        return row is not None

def ban_user(user_id: int):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO banned_users (user_id, banned_at) VALUES (?, ?)",
                     (user_id, datetime.now().isoformat()))

def unban_user(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))

def get_banned_list() -> list:
    with get_db() as conn:
        rows = conn.execute("SELECT user_id, banned_at FROM banned_users ORDER BY banned_at DESC").fetchall()
        return [(r["user_id"], r["banned_at"]) for r in rows]

def get_cart(user_id: int) -> list:
    with get_db() as conn:
        row = conn.execute("SELECT items FROM carts WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            try:
                return json.loads(row["items"])
            except json.JSONDecodeError:
                logger.error("Повреждённая корзина user_id=%s", user_id)
                return []
        return []

def save_cart(user_id: int, items: list):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO carts (user_id, items) VALUES (?, ?)",
                     (user_id, json.dumps(items, ensure_ascii=False)))

def clear_cart(user_id: int):
    save_cart(user_id, [])

def create_order(user_id: int, items: list, total: int, status: str = "pending") -> int:
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO orders (user_id, items, total, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, json.dumps(items, ensure_ascii=False), total, status, datetime.now().isoformat()))
        return cur.lastrowid

def get_pending_orders() -> list:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM orders WHERE status = 'pending' ORDER BY order_id DESC").fetchall()
        return [dict(r) for r in rows]

def set_order_status(order_id: int, status: str) -> bool:
    with get_db() as conn:
        cur = conn.execute("UPDATE orders SET status = ? WHERE order_id = ?", (status, order_id))
        return cur.rowcount > 0

# ==================== КЛАВИАТУРЫ ====================
def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💰 Как оплатить", callback_data="how_to_pay"))
    builder.row(InlineKeyboardButton(text="💎 МАГАЗИН", callback_data="shop"))
    builder.row(InlineKeyboardButton(text="💵 О магазине", callback_data="about"))
    builder.row(InlineKeyboardButton(text="✍️ Поддержка (@NovasHelper)", url="https://t.me/NovasHelper"))
    builder.row(InlineKeyboardButton(text="🛒 КОРЗИНА", callback_data="cart"))
    builder.row(InlineKeyboardButton(text="🌐 Языки", callback_data="languages"),
                InlineKeyboardButton(text="🔗 Рефералы", callback_data="referral"))
    builder.row(InlineKeyboardButton(text="✅ Верификация", callback_data="verify"))
    if user_id == ADMIN_ID:
        builder.row(InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel"))
    return builder.as_markup()

def shop_categories_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏹 СЕТЫ", callback_data="cat_sets"))
    builder.row(InlineKeyboardButton(text="📜 Ancients", callback_data="cat_ancients"))
    builder.row(InlineKeyboardButton(text="🌈 Chromas", callback_data="cat_chromas"))
    builder.row(InlineKeyboardButton(text="🌸 Godlies", callback_data="cat_godlies_0"))
    builder.row(InlineKeyboardButton(text="🏠 В главное", callback_data="main_menu"))
    return builder.as_markup()

def products_kb(products: dict, back_data: str, page: Optional[int] = None,
                total_pages: Optional[int] = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for name, price in products.items():
        safe_name = name.replace(" ", "_")[:40]
        builder.row(InlineKeyboardButton(text=f"{name} — {price}₽", callback_data=f"prod:{safe_name}"))
    if page is not None and total_pages is not None and total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"cat_godlies_{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"cat_godlies_{page + 1}"))
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=back_data))
    builder.row(InlineKeyboardButton(text="🏠 В главное", callback_data="main_menu"))
    return builder.as_markup()

def product_confirm_kb(safe_name: str, back_data: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛒 Добавить в корзину", callback_data=f"addcart:{safe_name}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=back_data))
    builder.row(InlineKeyboardButton(text="🏠 В главное", callback_data="main_menu"))
    return builder.as_markup()

def cart_kb(items: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, _ in enumerate(items):
        builder.row(InlineKeyboardButton(text=f"❌ Удалить {i + 1}", callback_data=f"delcart:{i}"))
    builder.row(InlineKeyboardButton(text="✅ Оформить", callback_data="checkout"))
    builder.row(InlineKeyboardButton(text="🔄 Очистить", callback_data="clear_cart"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    return builder.as_markup()

def admin_panel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Заказы", callback_data="admin_orders"))
    builder.row(InlineKeyboardButton(text="🚫 Забаненные", callback_data="admin_banned"))
    builder.row(InlineKeyboardButton(text="🏠 В главное", callback_data="main_menu"))
    return builder.as_markup()

# ==================== ТЕКСТЫ ====================
WELCOME_TEXT = (
    "👋 <b>ДОБРО ПОЖАЛОВАТЬ В МАГАЗИН</b> 👋\n\n"
    "<b>MM2 SHOP</b> 🛍️\n"
    "ЗДЕСЬ МОЖНО КУПИТЬ КРУТЫЕ СКИНЫ 💎\n"
    "ИЗ ИГРЫ 🩸 <b>MURDER MYSTERY 2</b> 😎"
)

HOW_TO_PAY_TEXT = """💳 <b>Как оплатить заказ?</b>

Принимаем:
💸 USDT (криптовалюта) — через @send
⭐ Telegram Stars — через @PremiumBot

Подробная инструкция — в боте @send или @PremiumBot.
После оплаты свяжитесь с поддержкой @NovasHelper для выдачи."""

ABOUT_TEXT = (
    "💵 <b>О магазине MM2 SHOP</b>\n\n"
    "Продаём скины из Murder Mystery 2.\n"
    "Быстрая выдача, честные цены, поддержка 24/7.\n\n"
    "⭐ Сотни довольных клиентов\n"
    "• Работаем с 2023 года\n"
    "• Гарантия на каждый скин\n\n"
    "Поддержка: @NovasHelper"
)

VERIFY_TEXT = (
    "✅ <b>Верификация</b>\n\n"
    "Перейти к проверенному продавцу:\n\n"
    "👉 @GiftsForFunpay"
)

def resolve_product_name(safe_name: str) -> Optional[str]:
    for name in ALL_PRODUCTS:
        if name.replace(" ", "_")[:40] == safe_name:
            return name
    return None

def find_product_back_data(name: str) -> str:
    if name in SETS:
        return "cat_sets"
    if name in ANCIENTS:
        return "cat_ancients"
    if name in CHROMAS:
        return "cat_chromas"
    if name in GODLIES_ALL:
        try:
            idx = GODLIES_NAMES.index(name)
            page = idx // GODLIES_PER_PAGE
            return f"cat_godlies_{page}"
        except ValueError:
            return "cat_godlies_0"
    return "shop"

# ==================== МИДЛВЕРЫ БАНА ====================
@router.message.middleware()
async def ban_message_middleware(handler, event: Message, data):
    uid = event.from_user.id
    if uid != ADMIN_ID and is_banned(uid):
        try:
            await event.answer("🚫 Вы заблокированы.")
        except Exception as e:
            logger.error("ban_mw message: %s", e)
        return
    return await handler(event, data)

@router.callback_query.middleware()
async def ban_callback_middleware(handler, event: CallbackQuery, data):
    uid = event.from_user.id
    if uid != ADMIN_ID and is_banned(uid):
        try:
            await event.answer("🚫 Вы заблокированы", show_alert=True)
        except Exception as e:
            logger.error("ban_mw callback: %s", e)
        return
    return await handler(event, data)

# ==================== ХЭНДЛЕРЫ ====================
@router.message(Command("start"))
async def cmd_start(message: Message):
    try:
        await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb(message.from_user.id))
    except Exception as e:
        logger.error("cmd_start: %s\n%s", e, traceback.format_exc())

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    try:
        await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_kb(callback.from_user.id))
        await callback.answer()
    except Exception as e:
        logger.error("cb_main_menu: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "how_to_pay")
async def cb_how_to_pay(callback: CallbackQuery):
    try:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🏠 В главное", callback_data="main_menu"))
        await callback.message.edit_text(HOW_TO_PAY_TEXT, reply_markup=builder.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error("cb_how_to_pay: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "about")
async def cb_about(callback: CallbackQuery):
    try:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🏠 В главное", callback_data="main_menu"))
        await callback.message.edit_text(ABOUT_TEXT, reply_markup=builder.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error("cb_about: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "verify")
async def cb_verify(callback: CallbackQuery):
    try:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="Перейти к @GiftsForFunpay", url="https://t.me/GiftsForFunpay"))
        builder.row(InlineKeyboardButton(text="🏠 В главное", callback_data="main_menu"))
        await callback.message.edit_text(VERIFY_TEXT, reply_markup=builder.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error("cb_verify: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "languages")
async def cb_languages(callback: CallbackQuery):
    try:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"))
        builder.row(InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"))
        builder.row(InlineKeyboardButton(text="🇨🇳 中文", callback_data="lang_zh"))
        builder.row(InlineKeyboardButton(text="🏠 В главное", callback_data="main_menu"))
        await callback.message.edit_text("🌐 <b>Выбор языка</b>\n\nПока заглушка.", reply_markup=builder.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error("cb_languages: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data.startswith("lang_"))
async def cb_lang_stub(callback: CallbackQuery):
    await callback.answer("Язык пока не меняется (заглушка)", show_alert=True)

@router.callback_query(F.data == "referral")
async def cb_referral(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        me = await bot.me()
        link = f"https://t.me/{me.username}?start=ref_{user_id}"
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🏠 В главное", callback_data="main_menu"))
        await callback.message.edit_text(
            f"🔗 <b>Ваша реферальная ссылка:</b>\n\n<code>{link}</code>\n\nПока заглушка.",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error("cb_referral: %s\n%s", e, traceback.format_exc())
        await callback.answer()
      @router.callback_query(F.data == "shop")
async def cb_shop(callback: CallbackQuery):
    try:
        await callback.message.edit_text("💎 <b>МАГАЗИН</b>\n\nВыберите категорию:", reply_markup=shop_categories_kb())
        await callback.answer()
    except Exception as e:
        logger.error("cb_shop: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "cat_sets")
async def cb_sets(callback: CallbackQuery):
    try:
        await callback.message.edit_text("🏹 <b>СЕТЫ</b>", reply_markup=products_kb(SETS, "shop"))
        await callback.answer()
    except Exception as e:
        logger.error("cb_sets: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "cat_ancients")
async def cb_ancients(callback: CallbackQuery):
    try:
        await callback.message.edit_text("📜 <b>Ancients</b>", reply_markup=products_kb(ANCIENTS, "shop"))
        await callback.answer()
    except Exception as e:
        logger.error("cb_ancients: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "cat_chromas")
async def cb_chromas(callback: CallbackQuery):
    try:
        await callback.message.edit_text("🌈 <b>Chromas</b>", reply_markup=products_kb(CHROMAS, "shop"))
        await callback.answer()
    except Exception as e:
        logger.error("cb_chromas: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data.startswith("cat_godlies_"))
async def cb_godlies(callback: CallbackQuery):
    try:
        page = int(callback.data.rsplit("_", 1)[-1])
        page = max(0, min(page, GODLIES_TOTAL_PAGES - 1))
        products = get_godlies_page(page)
        await callback.message.edit_text(
            f"🌸 <b>Godlies</b> (стр. {page + 1}/{GODLIES_TOTAL_PAGES})",
            reply_markup=products_kb(products, "shop", page=page, total_pages=GODLIES_TOTAL_PAGES)
        )
        await callback.answer()
    except Exception as e:
        logger.error("cb_godlies: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data.startswith("prod:"))
async def cb_product(callback: CallbackQuery):
    try:
        safe_name = callback.data[5:]
        name = resolve_product_name(safe_name)
        if not name:
            await callback.answer("Товар не найден", show_alert=True)
            return
        price = ALL_PRODUCTS[name]
        text = (
            f"✅ <b>Вы уверены, что хотите выбрать?</b>\n\n"
            f"Название: <b>{name}</b>\n"
            f"Цена: <b>{price} руб</b>\n"
            f"В наличии: <b>1 шт</b>"
        )
        back = find_product_back_data(name)
        await callback.message.edit_text(text, reply_markup=product_confirm_kb(safe_name, back))
        await callback.answer()
    except Exception as e:
        logger.error("cb_product: %s\n%s", e, traceback.format_exc())
        await callback.answer("Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("addcart:"))
async def cb_add_cart(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        safe_name = callback.data[8:]
        name = resolve_product_name(safe_name)
        if not name:
            await callback.answer("Товар не найден", show_alert=True)
            return
        price = ALL_PRODUCTS[name]
        cart = get_cart(user_id)
        if len(cart) >= 25:
            await callback.answer("Корзина полна (макс. 25 товаров)", show_alert=True)
            return
        cart.append({"name": name, "price": price})
        save_cart(user_id, cart)
        await callback.answer(f"✅ {name} добавлен в корзину!", show_alert=True)
    except Exception as e:
        logger.error("cb_add_cart: %s\n%s", e, traceback.format_exc())
        await callback.answer("Ошибка при добавлении", show_alert=True)

@router.callback_query(F.data == "cart")
async def cb_cart(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        cart = get_cart(user_id)
        if not cart:
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(text="🏠 В главное", callback_data="main_menu"))
            await callback.message.edit_text("🛒 <b>Корзина пуста</b>", reply_markup=builder.as_markup())
            await callback.answer()
            return
        lines = []
        total = 0
        for i, item in enumerate(cart, 1):
            lines.append(f"{i}. {item['name']} — {item['price']}₽")
            total += item["price"]
        text = "🛒 <b>Ваша корзина:</b>\n\n" + "\n".join(lines) + f"\n\n<b>Итого: {total}₽</b>"
        await callback.message.edit_text(text, reply_markup=cart_kb(cart))
        await callback.answer()
    except Exception as e:
        logger.error("cb_cart: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data.startswith("delcart:"))
async def cb_del_cart(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        idx = int(callback.data.split(":")[1])
        cart = get_cart(user_id)
        if 0 <= idx < len(cart):
            removed = cart.pop(idx)
            save_cart(user_id, cart)
            await callback.answer(f"Удалено: {removed['name']}")
        else:
            await callback.answer("Ошибка индекса", show_alert=True)
        await cb_cart(callback)
    except Exception as e:
        logger.error("cb_del_cart: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "clear_cart")
async def cb_clear_cart(callback: CallbackQuery):
    try:
        clear_cart(callback.from_user.id)
        await callback.answer("Корзина очищена")
        await cb_cart(callback)
    except Exception as e:
        logger.error("cb_clear_cart: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "checkout")
async def cb_checkout(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        cart = get_cart(user_id)
        if not cart:
            await callback.answer("🛒 Корзина пуста", show_alert=True)
            return
        total = sum(item["price"] for item in cart)
        order_id = create_order(user_id, cart, total, status="pending")
        clear_cart(user_id)
        items_text = "\n".join(f"• {item['name']} — {item['price']}₽" for item in cart)
        user_msg = (
            f"✅ <b>Заказ #{order_id} оформлен!</b>\n\n"
            f"{items_text}\n\n"
            f"<b>Итого: {total}₽</b>\n\n"
            "Оператор свяжется с вами для оплаты и передачи скина.\n"
            "Поддержка: @NovasHelper"
        )
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🏠 В главное", callback_data="main_menu"))
        await callback.message.edit_text(user_msg, reply_markup=builder.as_markup())
        await callback.answer()
        if ADMIN_ID:
            username = callback.from_user.username or "без username"
            admin_text = (
                f"🆕 <b>Новый заказ #{order_id}</b>\n\n"
                f"Пользователь: <code>{user_id}</code> (@{username})\n"
                f"{items_text}\n\n"
                f"<b>Итого: {total}₽</b>\n"
                f"Статус: pending"
            )
            try:
                await bot.send_message(ADMIN_ID, admin_text)
            except Exception as e:
                logger.error("Уведомление админу: %s", e)
    except Exception as e:
        logger.error("cb_checkout: %s\n%s", e, traceback.format_exc())
        await callback.answer("Ошибка оформления", show_alert=True)

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            "👑 <b>Админ-панель</b>\n\n"
            "/orders — активные заказы\n"
            "/done <id> — отметить выполненным\n"
            "/ban <user_id>\n"
            "/unban <user_id>\n"
            "/banned — список банов",
            reply_markup=admin_panel_kb()
        )
        await callback.answer()
    except Exception as e:
        logger.error("cb_admin_panel: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "admin_orders")
async def cb_admin_orders(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        orders = get_pending_orders()
        if not orders:
            text = "📋 Активных заказов нет."
        else:
            lines = []
            for o in orders:
                items = json.loads(o["items"])
                items_short = ", ".join(i["name"] for i in items[:3])
                if len(items) > 3:
                    items_short += "..."
                lines.append(f"#{o['order_id']} | user {o['user_id']} | {o['total']}₽ | {items_short}")
            text = "📋 <b>Активные заказы (pending):</b>\n\n" + "\n".join(lines)
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel"))
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error("cb_admin_orders: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.callback_query(F.data == "admin_banned")
async def cb_admin_banned(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        banned = get_banned_list()
        if not banned:
            text = "🚫 Забаненных нет."
        else:
            lines = [f"• <code>{uid}</code> ({ts})" for uid, ts in banned]
            text = "🚫 <b>Забаненные:</b>\n\n" + "\n".join(lines)
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel"))
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error("cb_admin_banned: %s\n%s", e, traceback.format_exc())
        await callback.answer()

@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        orders = get_pending_orders()
        if not orders:
            await message.answer("Активных заказов нет.")
            return
        lines = []
        for o in orders:
            items = json.loads(o["items"])
            items_text = "\n".join(f"  • {i['name']} — {i['price']}₽" for i in items)
            lines.append(f"<b>#{o['order_id']}</b> | user <code>{o['user_id']}</code> | "
                         f"{o['total']}₽\n{items_text}\n{o['created_at']}")
        await message.answer("📋 <b>Pending заказы:</b>\n\n" + "\n\n".join(lines))
    except Exception as e:
        logger.error("cmd_orders: %s\n%s", e, traceback.format_exc())

@router.message(Command("done"))
async def cmd_done(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    if not command.args or not command.args.strip():
        await message.answer("📌 Использование: <code>/done &lt;order_id&gt;</code>\nПример: <code>/done 12</code>")
        return
    try:
        order_id = int(command.args.strip())
    except ValueError:
        await message.answer("order_id должен быть числом. Пример: /done 12")
        return
    try:
        if set_order_status(order_id, "done"):
            await message.answer(f"✅ Заказ #{order_id} отмечен как выполненный.")
        else:
            await message.answer(f"Заказ #{order_id} не найден.")
    except Exception as e:
        logger.error("cmd_done: %s\n%s", e, traceback.format_exc())
        await message.answer("Ошибка при обновлении заказа.")

@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    if not command.args:
        await message.answer("Использование: /ban &lt;user_id&gt;")
        return
    try:
        uid = int(command.args.strip())
    except ValueError:
        await message.answer("user_id должен быть числом")
        return
    try:
        ban_user(uid)
        await message.answer(f"🚫 Пользователь <code>{uid}</code> забанен.")
    except Exception as e:
        logger.error("cmd_ban: %s\n%s", e, traceback.format_exc())

@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    if not command.args:
        await message.answer("Использование: /unban &lt;user_id&gt;")
        return
    try:
        uid = int(command.args.strip())
    except ValueError:
        await message.answer("user_id должен быть числом")
        return
    try:
        unban_user(uid)
        await message.answer(f"✅ Пользователь <code>{uid}</code> разбанен.")
    except Exception as e:
        logger.error("cmd_unban: %s\n%s", e, traceback.format_exc())

@router.message(Command("banned"))
async def cmd_banned(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        banned = get_banned_list()
        if not banned:
            await message.answer("Забаненных нет.")
            return
        lines = [f"• <code>{uid}</code> — {ts}" for uid, ts in banned]
        await message.answer("🚫 <b>Забаненные:</b>\n\n" + "\n".join(lines))
    except Exception as e:
        logger.error("cmd_banned: %s\n%s", e, traceback.format_exc())

# ==================== НЕИЗВЕСТНАЯ КОМАНДА ====================
@router.message()
async def unknown_message(message: Message):
    try:
        await message.answer("Используй кнопки меню 👇", reply_markup=main_menu_kb(message.from_user.id))
    except Exception as e:
        logger.error("unknown_message: %s\n%s", e, traceback.format_exc())

# ==================== ВЕБ-СЕРВЕР + ЗАПУСК ====================
async def ping_handler(request: web.Request) -> web.Response:
    return web.Response(text="pong", status=200)

async def run_bot_polling():
    init_db()
    logger.info("Старт polling | ADMIN_ID=%s | Godlies pages=%s", ADMIN_ID, GODLIES_TOTAL_PAGES)
    await dp.start_polling(bot, handle_signals=False)

async def on_startup(app: web.Application):
    app["polling_task"] = asyncio.create_task(run_bot_polling())

async def on_shutdown(app: web.Application):
    logger.info("Остановка...")
    task = app.get("polling_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await dp.stop_polling()
    await bot.session.close()

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/ping", ping_handler)
    app.router.add_get("/", ping_handler)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

def main():
    while True:
        try:
            logger.info("=== Запуск aiohttp на 0.0.0.0:%s ===", PORT)
            app = create_app()
            web.run_app(app, host="0.0.0.0", port=PORT, print=None)
        except KeyboardInterrupt:
            logger.info("Остановлено пользователем")
            break
        except Exception as e:
            logger.error("Критическая ошибка, перезапуск через 5 сек:\n%s\n%s", e, traceback.format_exc())
            try:
                asyncio.get_event_loop().run_until_complete(bot.session.close())
            except Exception:
                pass
            import time
            time.sleep(5)

if __name__ == "__main__":
    main()
