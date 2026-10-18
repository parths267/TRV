"""Registration, sessions, and password reset."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import audit, get_current_user
from app.models import EmailToken, User
from app.security import create_access_token, hash_password, hash_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str


class TokenIn(BaseModel):
    token: str


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=10, max_length=128)


class ProfileIn(BaseModel):
    name: str | None = None
    timezone: str | None = None
    quiet_start: str | None = None
    quiet_end: str | None = None
    telegram_chat_id: str | None = None
    theme: str | None = None


def _issue_token(db: Session, user: User, purpose: str) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(
        EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
    )
    db.commit()
    return raw


def _public_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "plan": user.plan,
        "email_verified": user.email_verified,
        "timezone": user.timezone,
        "quiet_start": user.quiet_start,
        "quiet_end": user.quiet_end,
        "telegram_chat_id": user.telegram_chat_id,
        "theme": user.theme,
    }


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    user = User(email=email, password_hash=hash_password(body.password), name=body.name.strip())
    db.add(user)
    db.commit()
    db.refresh(user)
    token = _issue_token(db, user, "verify")
    audit(db, user.id, "register", email)
    payload = {
        "user": _public_user(user),
        "access_token": create_access_token(user.id, user.role, user.plan),
        "email_delivery": "log" if get_settings().smtp_host is None else "smtp",
    }
    if not get_settings().is_production:
        payload["verification_token"] = token
    return payload


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Username or password is incorrect")
    audit(db, user.id, "login", "")
    return {"user": _public_user(user), "access_token": create_access_token(user.id, user.role, user.plan)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _public_user(user)


@router.patch("/me")
def update_me(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.theme and body.theme not in {"dark", "light"}:
        raise HTTPException(status_code=400, detail="theme must be dark or light")
    for field in ("name", "timezone", "quiet_start", "quiet_end", "telegram_chat_id", "theme"):
        value = getattr(body, field)
        if value is not None:
            setattr(user, field, value)
    db.commit()
    audit(db, user.id, "profile_update", "")
    return _public_user(user)


@router.post("/verify-email")
def verify_email(body: TokenIn, db: Session = Depends(get_db)):
    row = _consume(db, body.token, "verify")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Account missing")
    user.email_verified = True
    db.commit()
    audit(db, user.id, "verify_email", "")
    return {"verified": True}


class ForgotIn(BaseModel):
    email: EmailStr


@router.post("/request-reset")
def request_reset(body: ForgotIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    payload = {"status": "If the account exists, a reset token was created."}
    if user:
        token = _issue_token(db, user, "reset")
        if not get_settings().is_production:
            payload["reset_token"] = token
    return payload


@router.post("/reset-password")
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    row = _consume(db, body.token, "reset")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Account missing")
    user.password_hash = hash_password(body.password)
    db.commit()
    audit(db, user.id, "reset_password", "")
    return {"reset": True}


def _consume(db: Session, token: str, purpose: str) -> EmailToken:
    row = db.scalar(
        select(EmailToken).where(
            EmailToken.token_hash == hash_token(token),
            EmailToken.purpose == purpose,
            EmailToken.used.is_(False),
        )
    )
    if row is None:
        raise HTTPException(status_code=400, detail="Token is invalid or expired")
    expires = row.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token is invalid or expired")
    row.used = True
    db.commit()
    return row
