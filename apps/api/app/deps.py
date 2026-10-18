"""Request dependencies."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

import jwt

from app.db import get_db
from app.models import AuditLog, User
from app.security import decode_access_token


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access is required")
    return user


def audit(db: Session, user_id: str | None, action: str, detail: str = "") -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=detail[:2000]))
    db.commit()
