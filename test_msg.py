import os
import asyncio
from dotenv import load_dotenv
import telegram

# Загружаем переменные окружения из файла text.env
load_dotenv('.env')
TOKEN = os.getenv('TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

bot = telegram.Bot(token=TOKEN)

async def main():
    await bot.send_message(chat_id=CHAT_ID, text="Валера член")

if __name__ == '__main__':
    asyncio.run(main())
