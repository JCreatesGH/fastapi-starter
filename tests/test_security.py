from app.security import (hash_password, verify_password, create_token, decode_token)


def test_password_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip():
    t = create_token("42", "secret")
    assert decode_token(t, "secret")["sub"] == "42"


def test_token_rejects_tampering():
    t = create_token("42", "secret")
    assert decode_token(t, "other-secret") is None
    assert decode_token(t[:-2] + "xx", "secret") is None


def test_expired_token():
    t = create_token("1", "secret", expires_in=-10)
    assert decode_token(t, "secret") is None
