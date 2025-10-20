import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import random

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8118589093:AAHnOTdlaA6Zxm4uGCChgrM1GRal8QwDru4"
ADMINS = [5077703938,]
MIN_ORDER = 7.0

BRANDS = [
    "JACK IN THE BOX 🍔",
    "PANDA EXPRESS 🥡",
    "PIZZA HUT 🍕",
    "INSOMNIA COOKIES 🍪",
    "DOMINOS 🍕",
    "PAPA JOHNS 🍕",
    "OLIVE GARDEN 🍝",
    "CHIPOTLE 🌯",
    "CHILLIS 🌶️",
    "JERSEY MIKES 🥪",
    "CUSTOM ORDER 🍽️"
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

USER_STATE = {}
ORDERS = {}  # order_id -> order details
CLAIMED = {}  # order_id -> admin_id

def generate_payment_word():
    return random.choice(["apple", "banana", "cherry", "dragon", "elephant"])

def brands_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    for b in BRANDS:
        kb.add(InlineKeyboardButton(b, callback_data=f"brand|{b}"))
    return kb

def delivery_pickup_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Delivery", callback_data="delivery"))
    kb.add(InlineKeyboardButton("Pickup", callback_data="pickup"))
    return kb

def payment_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("CashApp", callback_data="pay|CASHAPP"))
    kb.add(InlineKeyboardButton("Apple Pay", callback_data="pay|APPLEPAY"))
    return kb

def order_status_kb(order_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Received", callback_data=f"status|{order_id}|Received"),
        InlineKeyboardButton("Placed", callback_data=f"status|{order_id}|Placed")
    )
    kb.add(
        InlineKeyboardButton("On the way!", callback_data=f"status|{order_id}|On the way!"),
        InlineKeyboardButton("Delivered/Ready", callback_data=f"status|{order_id}|Delivered")
    )
    kb.add(
        InlineKeyboardButton("Cancelled", callback_data=f"status|{order_id}|Cancelled"),
        InlineKeyboardButton("Add Comment", callback_data=f"comment|{order_id}")
    )
    return kb

def admin_panel_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    for oid, order in ORDERS.items():
        claimed = "✅" if oid in CLAIMED else ""
        kb.add(InlineKeyboardButton(f"Order {oid} - {order['brand']} {claimed}", callback_data=f"admin_order|{oid}"))
    return kb

def is_admin(user_id):
    return user_id in ADMINS

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    menu_text = (
        "Welcome to KeioEats! Here's our menu:\n\n"
        "$7 for $25\n$10 for $35\n$15 for $50\n$25 for $70\n$35 for $90\n$50 for $120\n$75 for $160\n$90 for $200\n$100 for $220\n\n"
        "Use /order to start an order."
    )
    await message.answer(menu_text)

@dp.message_handler(commands=["help"])
async def help_cmd(message: types.Message):
    text = "/order - Start an order\n/help - Show this help\n/ping - Ping admin for order\n"
    if is_admin(message.from_user.id):
        text += "/admin - Open admin panel (update orders, claim, comment)"
    await message.answer(text)

@dp.message_handler(commands=["ping"])
async def ping_admin(message: types.Message):
    # Notify admins to claim new order
    await message.answer("Ping sent to admins.")
    for a in ADMINS:
        try:
            await bot.send_message(a, f"Ping from {message.from_user.full_name} ({message.from_user.id}) to claim an order.")
        except:
            pass

@dp.message_handler(commands=["order"])
async def order_cmd(message: types.Message):
    await message.answer("Choose a brand:", reply_markup=brands_kb())

@dp.callback_query_handler(lambda c: c.data.startswith("brand|"))
async def brand_selected(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    brand = callback.data.split("|")[1]
    USER_STATE[user_id] = {"brand": brand, "payment_word": generate_payment_word()}
    await callback.message.answer(f"You selected: {brand}\nPlease enter your order details (what you want to order).")
    await callback.answer()

@dp.message_handler(lambda m: m.from_user.id in USER_STATE and "details" not in USER_STATE[m.from_user.id])
async def order_details(message: types.Message):
    user_id = message.from_user.id
    USER_STATE[user_id]["details"] = message.text
    await message.answer("Is this a delivery or pickup?", reply_markup=delivery_pickup_kb())

@dp.callback_query_handler(lambda c: c.data in ["delivery","pickup"])
async def delivery_pickup(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    USER_STATE[user_id]["delivery_type"] = callback.data
    if callback.data=="delivery":
        await callback.message.answer("Enter full address: street, state, zip, apt number.\nOnce the order is placed, it’s not the orderee's fault if they make mistakes.")
    else:
        await callback.message.answer("Enter the restaurant address for pickup.")
    await callback.answer()

@dp.message_handler(lambda m: m.from_user.id in USER_STATE and "address" not in USER_STATE[m.from_user.id])
async def get_address(message: types.Message):
    user_id = message.from_user.id
    USER_STATE[user_id]["address"] = message.text
    await message.answer(f"Enter total cart price (minimum ${MIN_ORDER}):")

@dp.message_handler(lambda m: m.from_user.id in USER_STATE and "price" not in USER_STATE[m.from_user.id])
async def get_price(message: types.Message):
    user_id = message.from_user.id
    try:
        price = float(message.text.replace("$",""))
    except:
        await message.answer("Enter valid numeric price.")
        return
    if price < MIN_ORDER:
        await message.answer(f"Minimum order is ${MIN_ORDER}. Enter a new amount.")
        return
    USER_STATE[user_id]["price"] = price
    await message.answer("Choose payment method:", reply_markup=payment_kb())

@dp.callback_query_handler(lambda c: c.data.startswith("pay|"))
async def payment_selected(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    method = callback.data.split("|")[1]
    order = USER_STATE[user_id]
    order_id = str(random.randint(1000,9999))
    ORDERS[order_id] = {
        "user_id": user_id,
        "username": callback.from_user.username or callback.from_user.full_name,
        "brand": order["brand"],
        "details": order["details"],
        "delivery_type": order["delivery_type"],
        "address": order["address"],
        "price": order["price"],
        "payment_method": method,
        "payment_word": order["payment_word"],
        "status": "Received",
        "comments": []
    }
    await callback.message.answer(f"Order recorded! Payment word: {order['payment_word']}")
    await callback.answer()
    USER_STATE.pop(user_id,None)
    # Notify admins
    for a in ADMINS:
        try:
            order_info = f"New order #{order_id}:\nUser: {ORDERS[order_id]['username']}\nBrand: {ORDERS[order_id]['brand']}\nDetails: {ORDERS[order_id]['details']}\nType: {ORDERS[order_id]['delivery_type']}\nAddress: {ORDERS[order_id]['address']}\nPrice: ${ORDERS[order_id]['price']}\nPayment: {ORDERS[order_id]['payment_method']}\nStatus: {ORDERS[order_id]['status']}"
            await bot.send_message(a, order_info, reply_markup=admin_panel_kb())
        except:
            pass

@dp.message_handler(commands=["admin"])
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("You are not an admin.")
        return
    await message.answer("Admin panel - select an order:", reply_markup=admin_panel_kb())

@dp.callback_query_handler(lambda c: c.data.startswith("admin_order|"))
async def admin_order_panel(callback: types.CallbackQuery):
    order_id = callback.data.split("|")[1]
    if order_id not in ORDERS:
        await callback.answer("Order not found.", show_alert=True)
        return
    order = ORDERS[order_id]
    kb = order_status_kb(order_id)
    await callback.message.answer(f"Order {order_id} details:\nUser: {order['username']}\nBrand: {order['brand']}\nDetails: {order['details']}\nType: {order['delivery_type']}\nAddress: {order['address']}\nPrice: ${order['price']}\nPayment: {order['payment_method']}\nStatus: {order['status']}\nComments: {order['comments']}", reply_markup=kb)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("status|"))
async def update_status(callback: types.CallbackQuery):
    order_id,new_status = callback.data.split("|")[1],callback.data.split("|")[2]
    if order_id not in ORDERS:
        await callback.answer("Order not found.", show_alert=True)
        return
    ORDERS[order_id]["status"] = new_status
    user_id = ORDERS[order_id]["user_id"]
    await bot.send_message(user_id,f"Your order #{order_id} status is now: {new_status}")
    await callback.answer(f"Order {order_id} status updated.")

@dp.callback_query_handler(lambda c: c.data.startswith("comment|"))
async def add_comment(callback: types.CallbackQuery):
    order_id = callback.data.split("|")[1]
    USER_STATE[callback.from_user.id] = {"commenting_order": order_id}
    await callback.message.answer("Type your comment for this order:")
    await callback.answer()

@dp.message_handler(lambda m: m.from_user.id in USER_STATE and "commenting_order" in USER_STATE[m.from_user.id])
async def save_comment(message: types.Message):
    user_id = message.from_user.id
    order_id = USER_STATE[user_id]["commenting_order"]
    ORDERS[order_id]["comments"].append(message.text)
    await message.answer(f"Comment added to order {order_id}.")
    USER_STATE.pop(user_id, None)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
