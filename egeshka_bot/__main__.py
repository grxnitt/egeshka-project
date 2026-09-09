import asyncio
from .bot import run
from .config import Settings

if __name__ == "__main__":
    asyncio.run(run(Settings()))
