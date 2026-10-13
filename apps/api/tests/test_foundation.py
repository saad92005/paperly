import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.config import Settings
from app.db import get_session
from app.main import create_app
from app.providers.stubs import StubEmbeddings
from app.repos import profiles as profiles_repo

KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())
USER_ID = uuid.uuid4()


def make_token(key: Any = KEY, **overrides: Any) -> str:
    claims = {
        "sub": str(USER_ID),
        "aud": "authenticated",
        "email": "a@example.com",
        "exp": int(time.time()) + 600,
        **overrides,
    }
    return jwt.encode(claims, key, algorithm="ES256")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> httpx.AsyncClient:
    app = create_app(Settings(_env_file=None, database_url="", supabase_url="http://sb.test"))  # pyright: ignore[reportCallIssue]
    app.state.jwt_test_key = KEY.public_key()
    store: dict[str, Any] = {}

    async def fake_get_or_create(_s: Any, user_id: uuid.UUID) -> dict[str, Any]:
        return store.setdefault(
            str(user_id),
            {
                "id": user_id,
                "display_name": None,
                "locale": "en",
                "explain_level": "student",
                "plan": "free",
                "is_admin": False,
                "created_at": datetime.now(UTC),
            },
        )

    async def fake_update(_s: Any, user_id: uuid.UUID, fields: dict[str, Any]) -> dict[str, Any]:
        row = await fake_get_or_create(_s, user_id)
        row.update(fields)
        return row

    async def no_session() -> AsyncIterator[None]:
        yield None

    monkeypatch.setattr(profiles_repo, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(profiles_repo, "update", fake_update)
    app.dependency_overrides[get_session] = no_session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_health_without_db_is_degraded(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "degraded",
        "version": "0.1.0",
        "db": "unconfigured",
        "worker": "off",
    }
    assert r.headers["x-request-id"].startswith("req_")


async def test_request_id_is_propagated(client: httpx.AsyncClient) -> None:
    r = await client.get("/health", headers={"X-Request-ID": "req_abc"})
    assert r.headers["x-request-id"] == "req_abc"


async def test_unknown_route_uses_error_shape(client: httpx.AsyncClient) -> None:
    r = await client.get("/nope", headers={"X-Request-ID": "req_x"})
    assert r.status_code == 404
    assert r.json()["error"] == {
        "code": "not_found",
        "message": "Not Found",
        "details": {},
        "request_id": "req_x",
    }


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": f"Bearer {make_token(OTHER_KEY)}"},
        {"Authorization": f"Bearer {make_token(exp=int(time.time()) - 10)}"},
        {"Authorization": f"Bearer {make_token(aud='anon')}"},
    ],
)
async def test_me_rejects_bad_auth(client: httpx.AsyncClient, headers: dict[str, str]) -> None:
    r = await client.get("/v1/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_me_returns_profile(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/me", headers={"Authorization": f"Bearer {make_token()}"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(USER_ID)
    assert body["email"] == "a@example.com"
    assert body["explain_level"] == "student"


async def test_patch_me_validates_and_updates(client: httpx.AsyncClient) -> None:
    auth = {"Authorization": f"Bearer {make_token()}"}
    bad = await client.patch("/v1/me", json={"explain_level": "genius"}, headers=auth)
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "validation_error"
    ok = await client.patch(
        "/v1/me", json={"explain_level": "expert", "display_name": "S"}, headers=auth
    )
    assert ok.status_code == 200
    assert ok.json()["explain_level"] == "expert"


async def test_stub_embeddings_are_normalised_and_deterministic() -> None:
    emb = StubEmbeddings(384)
    a, b = await emb.embed(["hello", "hello"], kind="doc")
    assert a == b and len(a) == 384
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6
