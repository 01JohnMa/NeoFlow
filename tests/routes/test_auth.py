"""Supabase/GoTrue JWT 验签测试（无需数据库）。"""

import base64
import http.server
import json
import threading
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.dependencies.auth import (
    CurrentUser,
    get_current_user,
    get_optional_user,
    invalidate_profile_cache,
)
from config.settings import settings

JWT_SECRET = "unit-test-jwt-secret-at-least-32-characters-long"
WRONG_SECRET = "another-unit-test-secret-at-least-32-characters"
USER_ID = "22222222-2222-4222-8222-222222222222"
TENANT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _make_token(secret: str = JWT_SECRET, **overrides) -> str:
    payload = {
        "sub": USER_ID,
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    payload.update(overrides)
    return jwt.encode(payload, secret, algorithm="HS256")


def _reencode_payload(token: str, **overrides) -> str:
    """保留原签名，修改 payload（用于构造篡改 token）。"""
    header, payload, signature = token.split(".")
    claims = json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    )
    claims.update(overrides)
    new_payload = (
        base64.urlsafe_b64encode(json.dumps(claims).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{new_payload}.{signature}"


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", JWT_SECRET)
    invalidate_profile_cache(USER_ID)
    yield
    invalidate_profile_cache(USER_ID)


@pytest.fixture
def auth_client(monkeypatch):
    async def fake_get_user_profile(user_id):
        return {
            "id": user_id,
            "tenant_id": TENANT_ID,
            "role": "user",
            "display_name": "测试用户",
            "tenants": {"id": TENANT_ID, "code": "test", "name": "测试租户"},
        }

    monkeypatch.setattr(
        "services.tenant_service.tenant_service.get_user_profile",
        fake_get_user_profile,
    )

    app = FastAPI()

    @app.get("/protected")
    async def protected(user: CurrentUser = Depends(get_current_user)):
        return {
            "user_id": user.user_id,
            "tenant_id": user.tenant_id,
            "role": user.role,
        }

    @app.get("/optional")
    async def optional(user=Depends(get_optional_user)):
        return {"authenticated": user is not None}

    return TestClient(app)


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_passes_and_keeps_current_user_shape(auth_client):
    response = auth_client.get("/protected", headers=_auth_headers(_make_token()))

    assert response.status_code == 200
    assert response.json() == {
        "user_id": USER_ID,
        "tenant_id": TENANT_ID,
        "role": "user",
    }


def test_forged_token_signed_with_other_secret_is_rejected(auth_client):
    response = auth_client.get(
        "/protected", headers=_auth_headers(_make_token(secret=WRONG_SECRET))
    )

    assert response.status_code == 401


def test_unsigned_token_is_rejected(auth_client):
    token = jwt.encode(
        {"sub": USER_ID, "aud": "authenticated", "exp": int(time.time()) + 3600},
        None,
        algorithm="none",
    )

    response = auth_client.get("/protected", headers=_auth_headers(token))

    assert response.status_code == 401


def test_tampered_token_is_rejected(auth_client):
    token = _reencode_payload(_make_token(), sub="99999999-9999-4999-8999-999999999999")

    response = auth_client.get("/protected", headers=_auth_headers(token))

    assert response.status_code == 401


def test_expired_token_is_rejected(auth_client):
    token = _make_token(exp=int(time.time()) - 60)

    response = auth_client.get("/protected", headers=_auth_headers(token))

    assert response.status_code == 401


def test_wrong_audience_is_rejected(auth_client):
    token = _make_token(aud="service_role")

    response = auth_client.get("/protected", headers=_auth_headers(token))

    assert response.status_code == 401


def test_token_without_sub_is_rejected(auth_client):
    token = _make_token(sub=None)

    response = auth_client.get("/protected", headers=_auth_headers(token))

    assert response.status_code == 401


def test_missing_jwt_secret_fails_closed(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "")

    response = auth_client.get("/protected", headers=_auth_headers(_make_token()))

    assert response.status_code == 401


def test_optional_user_ignores_invalid_token(auth_client):
    response = auth_client.get(
        "/optional", headers=_auth_headers(_make_token(secret=WRONG_SECRET))
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": False}


def test_optional_user_accepts_valid_token(auth_client):
    response = auth_client.get("/optional", headers=_auth_headers(_make_token()))

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


# ============ JWKS 非对称验签（Supabase 云项目） ============

JWKS_KID = "test-es256-kid"


def _make_es256_key():
    return ec.generate_private_key(ec.SECP256R1())


def _make_es256_token(private_key, kid=JWKS_KID, **overrides) -> str:
    payload = {
        "sub": USER_ID,
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    payload.update(overrides)
    return jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={"kid": kid},
    )


def _b64url_uint(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()


def _public_jwk(private_key) -> dict:
    numbers = private_key.public_key().public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url_uint(numbers.x),
        "y": _b64url_uint(numbers.y),
        "kid": JWKS_KID,
        "use": "sig",
        "alg": "ES256",
    }


@pytest.fixture
def jwks_server():
    """本地 JWKS HTTP 服务，测试不依赖外网。"""
    private_key = _make_es256_key()
    body = json.dumps({"keys": [_public_jwk(private_key)]}).encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield private_key, f"http://127.0.0.1:{server.server_address[1]}/jwks"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def jwks_env(monkeypatch, jwks_server):
    private_key, jwks_url = jwks_server
    monkeypatch.setattr(settings, "JWKS_URL", jwks_url)
    monkeypatch.setattr("api.dependencies.auth._jwks_client", None)
    yield private_key
    monkeypatch.setattr("api.dependencies.auth._jwks_client", None)


def test_jwks_es256_token_passes(jwks_env, auth_client):
    token = _make_es256_token(jwks_env)

    response = auth_client.get("/protected", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.json()["user_id"] == USER_ID


def test_jwks_forged_es256_token_is_rejected(jwks_env, auth_client):
    token = _make_es256_token(_make_es256_key())

    response = auth_client.get("/protected", headers=_auth_headers(token))

    assert response.status_code == 401


def test_jwks_unknown_kid_is_rejected(jwks_env, auth_client):
    token = _make_es256_token(jwks_env, kid="unknown-kid")

    response = auth_client.get("/protected", headers=_auth_headers(token))

    assert response.status_code == 401


def test_jwks_expired_token_is_rejected(jwks_env, auth_client):
    token = _make_es256_token(jwks_env, exp=int(time.time()) - 60)

    response = auth_client.get("/protected", headers=_auth_headers(token))

    assert response.status_code == 401


def test_es256_without_jwks_url_fails_closed(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "JWKS_URL", "")
    token = _make_es256_token(_make_es256_key())

    response = auth_client.get("/protected", headers=_auth_headers(token))

    assert response.status_code == 401


def test_hs256_still_uses_secret_when_jwks_configured(jwks_env, auth_client):
    response = auth_client.get("/protected", headers=_auth_headers(_make_token()))

    assert response.status_code == 200
