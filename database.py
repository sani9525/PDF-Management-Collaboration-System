import asyncpg

async def get_connection():
    return await asyncpg.connect(
        host="localhost",
        database="pdf_system",
        user="postgres",
        password="Sani@123",
)