"""FastAPI starter: JWT auth + per-user CRUD on SQLite, fully documented."""
from __future__ import annotations
import logging
from typing import List, Optional
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from .config import settings
from . import db as database
from .security import (create_token, decode_token, hash_password, verify_password)

logger = logging.getLogger("fastapi_starter")
DEFAULT_SECRET = "dev-secret-change-me"


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


class ItemUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    done: Optional[bool] = None


class ItemOut(BaseModel):
    id: int
    title: str
    done: bool


def create_app(db_path: Optional[str] = None) -> FastAPI:
    if settings.secret_key == DEFAULT_SECRET:
        logger.warning(
            "SECRET_KEY is the insecure default — set the SECRET_KEY env var before deploying; "
            "tokens signed with the default secret are trivially forgeable.")
    conn = database.connect(db_path or settings.database_url)
    database.migrate(conn)
    app = FastAPI(title="FastAPI Starter", version="1.1.0",
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
        email = str(user.email).strip().lower()   # normalize so casing can't fork accounts
        existing = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        with database.cursor(conn) as cur:
            cur.execute("INSERT INTO users (email, password) VALUES (?, ?)",
                        (email, hash_password(user.password)))
            uid = cur.lastrowid
        return {"id": uid, "email": email}

    @app.post("/auth/login", response_model=Token)
    def login(form: OAuth2PasswordRequestForm = Depends()):
        email = form.username.strip().lower()
        row = conn.execute("SELECT id, password FROM users WHERE email = ?",
                           (email,)).fetchone()
        if not row or not verify_password(form.password, row["password"]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad credentials")
        return {"access_token": create_token(str(row["id"]), settings.secret_key,
                                              settings.token_ttl)}

    @app.get("/me", response_model=UserOut)
    def me(user: dict = Depends(get_current_user)):
        return user

    @app.get("/items", response_model=List[ItemOut])
    def list_items(user: dict = Depends(get_current_user),
                   limit: int = 50, offset: int = 0, done: Optional[bool] = None):
        if limit < 1 or limit > 200:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "limit must be 1..200")
        if offset < 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "offset must be >= 0")
        sql = "SELECT id, title, done FROM items WHERE user_id = ?"
        params: list = [user["id"]]
        if done is not None:
            sql += " AND done = ?"
            params.append(int(done))
        sql += " ORDER BY id LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = conn.execute(sql, params).fetchall()
        return [{"id": r["id"], "title": r["title"], "done": bool(r["done"])} for r in rows]

    @app.post("/items", response_model=ItemOut, status_code=201)
    def create_item(item: ItemIn, user: dict = Depends(get_current_user)):
        with database.cursor(conn) as cur:
            cur.execute("INSERT INTO items (user_id, title) VALUES (?, ?)",
                        (user["id"], item.title))
            iid = cur.lastrowid
        return {"id": iid, "title": item.title, "done": False}

    @app.patch("/items/{item_id}", response_model=ItemOut)
    def update_item(item_id: int, update: Optional[ItemUpdate] = None,
                    user: dict = Depends(get_current_user)):
        row = conn.execute("SELECT id, title, done FROM items WHERE id = ? AND user_id = ?",
                           (item_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
        title, done = row["title"], bool(row["done"])
        if update is None or (update.title is None and update.done is None):
            done = not done                       # empty PATCH toggles done (back-compat)
        else:
            if update.title is not None:
                title = update.title
            if update.done is not None:
                done = update.done
        with database.cursor(conn) as cur:
            cur.execute("UPDATE items SET title = ?, done = ? WHERE id = ?",
                        (title, int(done), item_id))
        return {"id": row["id"], "title": title, "done": done}

    @app.delete("/items/{item_id}", status_code=204)
    def delete_item(item_id: int, user: dict = Depends(get_current_user)):
        with database.cursor(conn) as cur:
            cur.execute("DELETE FROM items WHERE id = ? AND user_id = ?", (item_id, user["id"]))
            if cur.rowcount == 0:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
        return None

    return app


app = create_app()
