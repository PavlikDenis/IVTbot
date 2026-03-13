import logging
import os
import asyncio
from dotenv import load_dotenv
from bot import start_bot

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    asyncio.run(start_bot(TOKEN))
