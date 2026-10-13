import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=settings.access_token_days)
    return jwt.encode({"sub": user_id, "exp": exp}, settings.secret_key, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    if creds is None:
        raise unauthorized
    try:
        payload = jwt.decode(creds.credentials, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise unauthorized from None
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise unauthorized
    return user


# -- signed file links ------------------------------------------------------
# <audio> tags and download links cannot send an Authorization header, so
# files are served through short-lived links that carry their own signature.

def _sign(body: bytes) -> str:
    mac = hmac.new(settings.secret_key.encode(), body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def file_token(rel_path: str, filename: str | None = None) -> str:
    body = json.dumps({"p": rel_path, "n": filename,
                       "e": int(time.time()) + settings.file_link_minutes * 60}).encode()
    return base64.urlsafe_b64encode(body).decode().rstrip("=") + "." + _sign(body)


def read_file_token(token: str) -> dict:
    try:
        b64, sig = token.split(".")
        body = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
        if not hmac.compare_digest(sig, _sign(body)):
            raise ValueError("bad signature")
        data = json.loads(body)
        if data["e"] < time.time():
            raise ValueError("expired")
        return data
    except Exception:  # noqa: BLE001 - any malformed token is just "not found"
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link has expired.") from None
