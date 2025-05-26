from database import get_connection

create_table='''
CREATE TABLE IF NOT EXISTS pdf_login(
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL
)'''

create_table2='''CREATE TABLE IF NOT EXISTS pdf_files (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES pdf_login(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''

create_table3='''CREATE TABLE IF NOT EXISTS pdf_comments (
    id SERIAL PRIMARY KEY,
    pdf_id INT NOT NULL REFERENCES pdf_files(id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES pdf_login(id) ON DELETE CASCADE,
    comment TEXT NOT NULL,
    commented_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''

create_table4='''CREATE TABLE IF NOT EXISTS pdf_shares (
    id SERIAL PRIMARY KEY,
    pdf_id INT NOT NULL REFERENCES pdf_files(id) ON DELETE CASCADE,
    share_token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''

async def create_model():
    conn=await get_connection()
    try:
        await conn.execute(create_table)
        await conn.execute(create_table2)
        await conn.execute(create_table3)
        await conn.execute(create_table4)
    except Exception as e:
        return {"error": str(e)}
    finally:
       await conn.close()