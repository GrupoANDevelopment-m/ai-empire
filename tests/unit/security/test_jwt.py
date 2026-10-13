"""Test JWT authentication."""
import time
import pytest
import jwt
from empire.security.auth import create_token, verify_token, JWTError


def test_create_token_returns_string():
    """create_token should return a string token."""
    token = create_token(user_id="user-1", tenant_id="t-1", role="user", secret="a" * 32)
    assert isinstance(token, str)
    assert len(token) > 50


def test_verify_token_valid():
    """verify_token should accept a valid token."""
    secret = "a" * 32
    token = create_token(user_id="user-1", tenant_id="t-1", role="user", secret=secret)
    payload = verify_token(token, secret=secret)
    assert payload["sub"] == "user-1"
    assert payload["tenant_id"] == "t-1"
    assert payload["role"] == "user"


def test_verify_token_expired():
    """verify_token should reject expired tokens."""
    secret = "a" * 32
    payload = {
        "sub": "user-1",
        "tenant_id": "t-1",
        "role": "user",
        "iat": int(time.time()) - 7200,
        "exp": int(time.time()) - 3600,
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    with pytest.raises(JWTError):
        verify_token(token, secret=secret)


def test_verify_token_wrong_secret():
    """verify_token should reject tokens signed with a different secret."""
    token = create_token(user_id="u", tenant_id="t", role="user", secret="a" * 32)
    with pytest.raises(JWTError):
        verify_token(token, secret="b" * 32)


def test_create_token_rejects_short_secret():
    """create_token should reject secrets < 32 bytes."""
    with pytest.raises(ValueError):
        create_token(user_id="u", tenant_id="t", role="user", secret="short")


def test_token_payload_includes_required_claims():
    """Token payload should include all required claims."""
    token = create_token(user_id="u-1", tenant_id="t-1", role="admin", secret="a" * 32)
    payload = verify_token(token, secret="a" * 32)
    for claim in ["sub", "tenant_id", "role", "iat", "exp"]:
        assert claim in payload
