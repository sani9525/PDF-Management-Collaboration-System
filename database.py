import os
import asyncpg
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv()

async def get_connection():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL not set")

    parsed = urlparse(url)

    return await asyncpg.connect(
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/"),
        host=parsed.hostname,
        port=parsed.port or 5432
    )
