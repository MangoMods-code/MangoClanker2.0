import asyncio
import logging

from mangomods_bot.bot import MangoModsBot

from pyfiglet import figlet_format

print(figlet_format("Mango Clanker", font="slant"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

async def main() -> None:
    bot = MangoModsBot()
    await bot.start(bot.config.discord_token)

if __name__ == "__main__":
    asyncio.run(main())