from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.security import TokenError, create_access_token, decode_access_token


def test_create_and_decode_access_token_roundtrip():
    token = create_access_token(user_id=42)

    assert decode_access_token(token) == 42


def test_decode_access_token_rejects_expired_token():
    payload = {
        "sub": "42",
        "iat": datetime.now(timezone.utc) - timedelta(hours=9),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    expired_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    with pytest.raises(TokenError):
        decode_access_token(expired_token)


def test_decode_access_token_rejects_tampered_token():
    token = create_access_token(user_id=42)

    with pytest.raises(TokenError):
        decode_access_token(token + "tampered")


def test_decode_access_token_rejects_wrong_signature():
    payload = {
        "sub": "42",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, "wrong-secret", algorithm=settings.JWT_ALGORITHM)

    with pytest.raises(TokenError):
        decode_access_token(token)
