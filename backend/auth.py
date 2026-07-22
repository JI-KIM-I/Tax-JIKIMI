from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from db import serialize_doc, users

security = HTTPBearer(auto_error=False)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_HOURS = 24


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)

    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    token = credentials.credentials

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    if not user_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    try:
        user = users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 사용자 정보입니다.")

    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    user = serialize_doc(user)
    user.pop("password_hash", None)
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    if credentials is None:
        return None

    try:
        return get_current_user(credentials)
    except Exception:
        return None
