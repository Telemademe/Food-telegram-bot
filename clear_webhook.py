import asyncio
from aiogram import Bot

async def clear_webhook():
    bot = Bot(token="8118589093:AAE12ZDqSAhuIkRMvrMwI1PtJMIMCdOPREs")
    await bot.delete_webhook()
    await bot.session.close()
    print("Webhook cleared!")

asyncio.run(clear_webhook())
