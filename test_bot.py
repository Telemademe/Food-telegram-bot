import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8118589093:AAEe4Gt8a6EKnBikz3pIoJvfvCgoOvTNWz8"
ADMINS = [8159298411, 5077703938]

CASHAPP_CASHTAG = "$keiobnmakesbandz"
APPLE_PAY_INSTRUCTIONS = "Pay via Apple Pay to phone/email on request."
MIN_ORDER = 8.0

INITIAL_BRANDS = [
    "BUFFALO WILD WINGS",
    "PANDA EXPRESS",
    "JACK IN THE BOX",
    "PIZZA HUT",
    "INSOMIA",
    "PANERA BREAD",
    "DOMINOS",
    "PAPA JOHNS",
    "slicelife.com"
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
DB_PATH = "bot.db"
USER_STATE = {}

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS brands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                available INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                brand TEXT,
                price REAL,
                payment_method TEXT,
                note TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        for b in INITIAL_BRANDS:
            await db.execute("INSERT OR IGNORE INTO brands (name, available) VALUES (?, 1)", (b,))
        await db.commit()

async def get_available_brands():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT name FROM brands WHERE available=1 ORDER BY name")
        rows = await cur.fetchall()
        return [r[0] for r in rows]

async def set_brand_availability(brand, available: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE brands SET available=? WHERE name=?", (1 if available else 0, brand))
        await db.commit()

async def get_all_brands():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT name, available FROM brands ORDER BY name")
        return await cur.fetchall()

async def save_order(user_id, username, brand, price, payment_method, note=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO orders (user_id, username, brand, price, payment_method, note) VALUES (?,?,?,?,?,?)",
            (user_id, username, brand, price, payment_method, note)
        )
        await db.commit()

async def get_recent_orders(limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, user_id, username, brand, price, payment_method, note, timestamp FROM orders ORDER BY id DESC LIMIT ?", (limit,))
        return await cur.fetchall()

def admin_check(user_id):
    return user_id in ADMINS

def brands_kb(brands):
    kb = InlineKeyboardMarkup(row_width=1)
    for b in brands:
        kb.add(InlineKeyboardButton(b, callback_data=f"brand|{b}"))
    return kb

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer("Welcome! Use /order to start a food order, or /help for commands.")

@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    await message.answer(
        "/order - Start an order\n"
        "/admin - Admin panel (admins only)\n"
        "/brands - Show available brands"
    )

@dp.message_handler(commands=["brands"])
async def cmd_brands(message: types.Message):
    brands = await get_available_brands()
    if not brands:
        await message.answer("No brands are currently available. Please check back later.")
        return
    await message.answer("Available brands:", reply_markup=brands_kb(brands))

@dp.message_handler(commands=["order"])
async def cmd_order(message: types.Message):
    brands = await get_available_brands()
    if not brands:
        await message.answer("No brands are currently available. Admins have disabled all brands.")
        return
    await message.answer("Choose a brand:", reply_markup=brands_kb(brands))

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("brand|"))
async def on_brand_click(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    brand = callback.data.split("|", 1)[1]
    USER_STATE[user_id] = {"brand": brand}
    await callback.message.answer(f"You chose *{brand}*.\nPlease enter your cart total (USD). Minimum is ${MIN_ORDER:.2f}.", parse_mode="Markdown")
    await callback.answer()

@dp.message_handler(lambda m: m.from_user.id in USER_STATE and "brand" in USER_STATE[m.from_user.id] and (not USER_STATE[m.from_user.id].get("price")))
async def on_price_enter(message: types.Message):
    user_id = message.from_user.id
    txt = message.text.strip().replace("$","")
    try:
        price = float(txt)
    except:
        await message.answer("Please enter a valid numeric price, e.g. 12.50")
        return
    if price < MIN_ORDER:
        await message.answer(f"Minimum order is ${MIN_ORDER:.2f}. Enter a new amount.")
        return
    USER_STATE[user_id]["price"] = price

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("CashApp", callback_data="pay|CASHAPP"))
    kb.add(InlineKeyboardButton("Apple Pay", callback_data="pay|APPLEPAY"))
    await message.answer(f"Order: *{USER_STATE[user_id]['brand']}* — *${price:.2f}*\nChoose a payment method:", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("pay|"))
async def on_payment_choice(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in USER_STATE or "brand" not in USER_STATE[user_id] or "price" not in USER_STATE[user_id]:
        await callback.answer("Start an order first with /order.", show_alert=True)
        return
    method = callback.data.split("|",1)[1]
    state = USER_STATE[user_id]
    brand = state["brand"]
    price = state["price"]

    username = callback.from_user.username or f"{callback.from_user.full_name}"
    await save_order(user_id, username, brand, price, method, note="awaiting_payment")

    admins_msg = f"New order:\nUser: {username} ({user_id})\nBrand: {brand}\nPrice: ${price:.2f}\nPayment: {method}"
    for a in ADMINS:
        try:
            await bot.send_message(a, admins_msg)
        except Exception as e:
            logging.warning(f"Failed to notify admin {a}: {e}")

    if method == "CASHAPP":
        pay_text = f"Send ${price:.2f} via CashApp to {CASHAPP_CASHTAG}."
    else:
        pay_text = f"{APPLE_PAY_INSTRUCTIONS}\nSend ${price:.2f}."

    await callback.message.answer(f"Your order is recorded and awaiting payment.\n{pay_text}")
    await callback.answer()
    USER_STATE.pop(user_id, None)

@dp.message_handler(commands=["admin"])
async def cmd_admin(message: types.Message):
    if not admin_check(message.from_user.id):
        await message.answer("You are not an admin.")
        return

    brands = await get_all_brands()
    kb = InlineKeyboardMarkup(row_width=1)
    for name, available in brands:
        mark = "✅" if available else "❌"
        kb.add(InlineKeyboardButton(f"{mark} {name}", callback_data=f"admin_toggle|{name}"))
    kb.add(InlineKeyboardButton("View recent orders", callback_data="admin_orders"))
    kb.add(InlineKeyboardButton("Export orders (.txt)", callback_data="admin_export"))
    await message.answer("Admin panel:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("admin_toggle|"))
async def admin_toggle(callback: types.CallbackQuery):
    if not admin_check(callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    brand = callback.data.split("|",1)[1]
    all_br = await get_all_brands()
    cur = {b[0]: b[1] for b in all_br}
    new_state = 0 if cur.get(brand,1)==1 else 1
    await set_brand_availability(brand, bool(new_state))
    await callback.answer(f"{brand} is now {'available' if new_state==1 else 'unavailable'}.", show_alert=True)
    await cmd_admin(callback.message)

@dp.callback_query_handler(lambda c: c.data == "admin_orders")
async def admin_orders(callback: types.CallbackQuery):
    if not admin_check(callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    orders = await get_recent_orders(50)
    if not orders:
        await callback.message.answer("No recent orders.")
    else:
        parts = []
        for o in orders:
            oid, uid, uname, brand, price, pay, note, ts = o
            parts.append(f"#{oid} {ts}\nUser: {uname} ({uid})\nBrand: {brand}\n${price:.2f} — {pay}\nNote: {note}")
        text = "\n\n".join(parts)
        for chunk_start in range(0, len(text), 3500):
            await callback.message.answer(text[chunk_start:chunk_start+3500])
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "admin_export")
async def admin_export(callback: types.CallbackQuery):
    if not admin_check(callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    orders = await get_recent_orders(1000)
    lines = []
    for o in reversed(orders):
        oid, uid, uname, brand, price, pay, note, ts = o
        lines.append(f"{uid}\t{uname}\t{brand}\t${price:.2f}\t{pay}\t{ts}")
    content = "\n".join(lines) if lines else "No orders."
    path = "users_and_orders.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    await bot.send_document(callback.from_user.id, types.InputFile(path))
    await callback.answer("Export complete.")

async def on_startup(dp):
    await init_db()
    logging.info("Bot started.")

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)
