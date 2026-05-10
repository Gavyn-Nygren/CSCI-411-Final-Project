from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Response, status

from .database import get_connection


SESSION_COOKIE = "cleanops_session"
SESSION_HOURS = 8
COOKIE_SECURE = False

USERNAME_RE = re.compile(r"^[A-Za-z0-9]{3,50}$")
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,128}$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def validate_username(username: str) -> str:
    if not isinstance(username, str) or not USERNAME_RE.fullmatch(username):
        raise HTTPException(status_code=400, detail="Username must be 3-50 alphanumeric characters.")
    return username


def validate_password(password: str) -> str:
    if not isinstance(password, str) or not PASSWORD_RE.match(password):
        raise HTTPException(
            status_code=400,
            detail="Password must be 8-128 characters and include uppercase, lowercase, number, and special character.",
        )
    return password


def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))


def verify_password(password: str, password_hash: bytes) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash)
    except ValueError:
        return False


def create_session(response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    expires_at = utc_now() + timedelta(hours=SESSION_HOURS)
    with get_connection() as db:
        db.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, iso(expires_at)),
        )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        max_age=SESSION_HOURS * 3600,
    )


def clear_session(response: Response, token: str | None) -> None:
    if token:
        with get_connection() as db:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))
    response.delete_cookie(SESSION_COOKIE)


def current_user(token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    with get_connection() as db:
        row = db.execute(
            """
            SELECT users.id, users.username, sessions.expires_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= utc_now():
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
        return {"id": row["id"], "username": row["username"]}


def require_user(user: dict = Depends(current_user)) -> dict:
    return user
