from fastapi import FastAPI,Depends,HTTPException,Form,status, UploadFile, File,Path,Body
from database import get_connection
from model import create_model
from schemas import UserCreate,UserOut,Token
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from auth import hash_password,verify_password, create_access_token,decode_jwt_token
import os
import uuid

app = FastAPI()


origins = [
    "http://localhost:4200"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # or ["*"] to allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await create_model()



@app.post("/register", response_model=UserOut)
async def register(user: UserCreate):
    conn = await get_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        exists = await conn.fetchrow("SELECT * FROM pdf_login WHERE email = $1", user.email)
        if exists:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_pw = hash_password(user.password)
        result = await conn.fetchrow("""
            INSERT INTO pdf_login(name, email, password)
            VALUES ($1, $2, $3)
            RETURNING id, name, email
        """, user.name, user.email, hashed_pw)

        return dict(result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await conn.close()





@app.post("/login", response_model=Token)
async def login(email: str = Form(...), password: str = Form(...)):
    conn = await get_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        user = await conn.fetchrow("SELECT * FROM pdf_login WHERE email = $1", email)
        if not user:
            raise HTTPException(status_code=400, detail="Invalid credentials")

        if not verify_password(password, user["password"]):
            raise HTTPException(status_code=400, detail="Invalid credentials")

        token_data = {"sub": str(user["id"])}
        access_token = create_access_token(data=token_data)

        return {"access_token": access_token, "token_type": "bearer"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await conn.close()




UPLOAD_DIR = "pdf_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Upload PDF route
@app.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    token_data: dict = Depends(decode_jwt_token)
):
    conn = await get_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        # Validate PDF type
        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")

        # Create unique filename
        unique_filename = f"{uuid.uuid4()}_{file.filename}"
        save_path = os.path.join(UPLOAD_DIR, unique_filename)

        # Save file to disk
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Insert metadata into DB
        await conn.execute("""
            INSERT INTO pdf_files (user_id, filename, filepath)
            VALUES ($1, $2, $3)
        """, int(token_data["sub"]), file.filename, save_path)

        return {"message": "PDF uploaded and stored successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await conn.close()






@app.get("/my-pdfs")
async def get_user_pdfs(token: dict = Depends(decode_jwt_token)):
    conn = await get_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        user_id = int(token["sub"])
        rows = await conn.fetch("""
            SELECT id, filename, upload_time
            FROM pdf_files
            WHERE user_id = $1
            ORDER BY upload_time DESC
        """, user_id)
        return [dict(row) for row in rows]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await conn.close()






@app.get("/download-pdf/{pdf_id}")
async def download_pdf(pdf_id: int, token: dict = Depends(decode_jwt_token)):
    conn = await get_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        # Check if the file exists and belongs to the user
        result = await conn.fetchrow("""
            SELECT filename, filepath
            FROM pdf_files
            WHERE id = $1 AND user_id = $2
        """, pdf_id, int(token["sub"]))

        if not result:
            raise HTTPException(status_code=404, detail="File not found or access denied")

        filepath = result["filepath"]
        filename = result["filename"]

        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="File missing on server")

        return FileResponse(path=filepath,filename=filename,media_type='application/pdf')

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await conn.close()

@app.post("/pdfs/{pdf_id}/comments")
async def add_comment(
    pdf_id: int = Path(...),
    comment: str = Body(...),
    token: dict = Depends(decode_jwt_token)
):
    conn = await get_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        # Check if the PDF exists and belongs to the user
        exists = await conn.fetchval("SELECT 1 FROM pdf_files WHERE id = $1", pdf_id)
        if not exists:
            raise HTTPException(status_code=404, detail="PDF not found")

        # Insert comment
        await conn.execute("""
            INSERT INTO pdf_comments (pdf_id, user_id, comment)
            VALUES ($1, $2, $3)
        """, pdf_id, int(token["sub"]), comment)

        return {"message": "Comment added successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await conn.close()


@app.get("/pdfs/{pdf_id}/comments_all")
async def get_comments(pdf_id: int = Path(...)):
    conn = await get_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        rows = await conn.fetch("""
            SELECT c.comment, c.commented_at, u.name AS author
            FROM pdf_comments c
            JOIN pdf_login u ON u.id = c.user_id
            WHERE c.pdf_id = $1
            ORDER BY c.commented_at ASC
        """, pdf_id)

        return [dict(row) for row in rows]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await conn.close()


@app.post("/share-pdf/{pdf_id}")
async def share_pdf(pdf_id: int, token: dict = Depends(decode_jwt_token)):
    conn = await get_connection()
    try:
        # Ensure the PDF belongs to the current user
        exists = await conn.fetchval("SELECT 1 FROM pdf_files WHERE id = $1 AND user_id = $2", pdf_id, int(token["sub"]))
        if not exists:
            raise HTTPException(status_code=404, detail="PDF not found or unauthorized")

        share_token = str(uuid.uuid4())

        await conn.execute("""
            INSERT INTO pdf_shares (pdf_id, share_token)
            VALUES ($1, $2)
        """, pdf_id, share_token)

        share_link = f"http://localhost:8000/public-view/{share_token}"
        return {"share_link": share_link}

    finally:
        await conn.close()



@app.get("/public-view/{share_token}")
async def view_shared_pdf(share_token: str):
    conn = await get_connection()
    try:
        result = await conn.fetchrow("""
            SELECT f.filename, f.filepath
            FROM pdf_shares s
            JOIN pdf_files f ON f.id = s.pdf_id
            WHERE s.share_token = $1
        """, share_token)

        if not result:
            raise HTTPException(status_code=404, detail="Invalid or expired link")

        filepath = result["filepath"]
        filename = result["filename"]

        return FileResponse(
            path=filepath,
            media_type="application/pdf",
            filename=filename,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )

    finally:
        await conn.close()





@app.get("/view-pdf/{pdf_id}")
async def view_pdf(pdf_id: int, token: dict = Depends(decode_jwt_token)):
    conn = await get_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        # Ensure the file exists and belongs to the user
        result = await conn.fetchrow("""
            SELECT filename, filepath
            FROM pdf_files
            WHERE id = $1 AND user_id = $2
        """, pdf_id, int(token["sub"]))

        if not result:
            raise HTTPException(status_code=404, detail="File not found or access denied")

        filepath = result["filepath"]
        filename = result["filename"]

        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="File missing on server")

        # Stream in-browser (no "Content-Disposition: attachment")
        return FileResponse(
            path=filepath,
            media_type='application/pdf',
            filename=filename,
            headers={"Content-Disposition": f'inline; filename="{filename}"'}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await conn.close()
