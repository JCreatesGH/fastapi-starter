"""FastAPI starter: JWT auth + per-user CRUD on SQLite, fully documented."""
from __future__ import annotations
from typing import List, Optional
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from .config import settings
from . import db as database
from .security import (create_token, decode_token, hash_password, verify_password)


# ----- schemas -----
class UserIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    id: int
    email: EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ItemOut(BaseModel):
    id: int
    title: str
    done: bool


def create_app(db_path: Optional[str] = None) -> FastAPI:
    conn = database.connect(db_path or settings.database_url)
    database.migrate(conn)
    app = FastAPI(title="FastAPI Starter", version="1.0.0",
                  description="Production-shaped starter: auth, SQLite, OpenAPI, Docker.")
    oauth2 = OAuth2PasswordBearer(tokenUrl="auth/login")

    def get_current_user(token: str = Depends(oauth2)) -> dict:
        data = decode_token(token, settings.secret_key)
        if not data:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
        row = conn.execute("SELECT id, email FROM users WHERE id = ?",
                           (int(data["sub"]),)).fetchone()
        if not row:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
        return dict(row)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/auth/register", response_model=UserOut, status_code=201)
    def register(user: UserIn):
        existing = conn.execute("SELECT 1 FROM users WHERE email = ?", (user.email,)).fetchone()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        with database.cursor(conn) as cur:
            cur.execute("INSERT INTO users (email, password) VALUES (?, ?)",
                        (user.email, hash_password(user.password)))
            uid = cur.lastrowid
        return {"id": uid, "email": user.email}

    @app.post("/auth/login", response_model=Token)
    def login(form: OAuth2PasswordRequestForm = Depends()):
        row = conn.execute("SELECT id, password FROM users WHERE email = ?",
                           (form.username,)).fetchone()
        if not row or not verify_password(form.password, row["password"]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad credentials")
        return {"access_token": create_token(str(row["id"]), settings.secret_key,
                                              settings.token_ttl)}

    @app.get("/me", response_model=UserOut)
    def me(user: dict = Depends(get_current_user)):
        return user

    @app.get("/items", response_model=List[ItemOut])
    def list_items(user: dict = Depends(get_current_user)):
        rows = conn.execute("SELECT id, title, done FROM items WHERE user_id = ? ORDER BY id",
                           (user["id"],)).fetchall()
        return [{"id": r["id"], "title": r["title"], "done": bool(r["done"])} for r in rows]

    @app.post("/items", response_model=ItemOut, status_code=201)
    def create_item(item: ItemIn, user: dict = Depends(get_current_user)):
        with database.cursor(conn) as cur:
            cur.execute("INSERT INTO items (user_id, title) VALUES (?, ?)",
                        (user["id"], item.title))
            iid = cur.lastrowid
        return {"id": iid, "title": item.title, "done": False}

    @app.patch("/items/{item_id}", response_model=ItemOut)
    def toggle_item(item_id: int, user: dict = Depends(get_current_user)):
        row = conn.execute("SELECT id, title, done FROM items WHERE id = ? AND user_id = ?",
                           (item_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
        new_done = 0 if row["done"] else 1
        with database.cursor(conn) as cur:
            cur.execute("UPDATE items SET done = ? WHERE id = ?", (new_done, item_id))
        return {"id": row["id"], "title": row["title"], "done": bool(new_done)}

    @app.delete("/items/{item_id}", status_code=204)
    def delete_item(item_id: int, user: dict = Depends(get_current_user)):
        with database.cursor(conn) as cur:
            cur.execute("DELETE FROM items WHERE id = ? AND user_id = ?", (item_id, user["id"]))
            if cur.rowcount == 0:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
        return None

    return app


app = create_app()
