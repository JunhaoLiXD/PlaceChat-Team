"""Local ES256 signatures and a mocked JWKS transport; no Supabase/network calls."""

import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from time import time
from typing import Annotated, Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.pool import StaticPool

from app.core import auth
from app.core.auth_models import AdminUser
from app.core.config import Settings
from app.core.db import Base, get_db
from app.main import create_app
from app.modules.rooms import admin_service
from app.modules.rooms.models import Room

SUPABASE_URL = "https://test-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
USER_ID = str(uuid4())


@pytest.fixture
def private_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def jwks_transport(
    monkeypatch: pytest.MonkeyPatch, private_key: ec.EllipticCurvePrivateKey
) -> Mock:
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key()))
    jwk.update(kid="test-key", alg="ES256", use="sig")
    transport = Mock(
        side_effect=lambda *args, **kwargs: io.BytesIO(json.dumps({"keys": [jwk]}).encode())
    )
    monkeypatch.setattr("jwt.jwks_client.urllib.request.urlopen", transport)
    monkeypatch.setattr(
        "jwt.jwks_client.urllib.request.build_opener", lambda *args: Mock(open=transport)
    )
    monkeypatch.setattr(
        "socket.create_connection",
        Mock(side_effect=AssertionError("Network forbidden in auth tests")),
    )
    return transport


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch, jwks_transport: Mock) -> Iterator[TestClient]:
    auth.get_jwks_client.cache_clear()
    monkeypatch.setattr(
        auth, "get_settings", lambda: Settings(_env_file=None, supabase_url=SUPABASE_URL)
    )
    app = create_app()

    @app.get("/_test/session")
    def session(
        current: Annotated[auth.Session, Depends(auth.get_current_session)],
    ) -> auth.Session:
        return current

    with TestClient(app) as client:
        yield client
    auth.get_jwks_client.cache_clear()


def claims(**overrides: Any) -> dict[str, Any]:
    return {
        "sub": USER_ID,
        "exp": int(time()) + 300,
        "aud": "authenticated",
        "iss": ISSUER,
        "is_anonymous": True,
        **overrides,
    }


def encode(private_key: ec.EllipticCurvePrivateKey, payload: dict[str, Any]) -> str:
    # Sign raw JSON so malformed claim types are tested even when jwt.encode rejects them.
    return jwt.api_jws.PyJWS().encode(
        json.dumps(payload).encode(), private_key, algorithm="ES256", headers={"kid": "test-key"}
    )


def assert_unauthenticated(client: TestClient, token: str) -> None:
    response = client.get("/_test/session", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "UNAUTHENTICATED", "message": auth.Unauthenticated.message}
    }


@pytest.mark.parametrize("is_anonymous", [True, False])
def test_valid_identity(
    auth_client: TestClient, private_key: ec.EllipticCurvePrivateKey, is_anonymous: bool
) -> None:
    token = encode(private_key, claims(is_anonymous=is_anonymous))
    response = auth_client.get("/_test/session", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"id": USER_ID, "is_anonymous": is_anonymous}


@pytest.mark.parametrize(
    "header", [None, "", "Basic abc", "Bearer", "Bearer abc extra", "Bearer nonsense"]
)
def test_missing_or_malformed_authorization(auth_client: TestClient, header: str | None) -> None:
    response = auth_client.get(
        "/_test/session", headers={"Authorization": header} if header is not None else {}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("claim", ["sub", "exp", "aud", "iss", "is_anonymous"])
def test_missing_claim(
    auth_client: TestClient, private_key: ec.EllipticCurvePrivateKey, claim: str
) -> None:
    payload = claims()
    del payload[claim]
    assert_unauthenticated(auth_client, encode(private_key, payload))


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time()) - 60},
        {"exp": str(int(time()) + 300)},
        {"exp": True},
        {"exp": None},
        {"aud": "anon"},
        {"aud": ["authenticated"]},
        {"aud": 123},
        {"iss": "https://other-project.supabase.co/auth/v1"},
        {"iss": 123},
        {"sub": 123},
        {"sub": ""},
        {"sub": "   "},
        {"is_anonymous": "true"},
        {"is_anonymous": 1},
        {"is_anonymous": None},
    ],
)
def test_invalid_claims(
    auth_client: TestClient, private_key: ec.EllipticCurvePrivateKey, overrides: dict[str, Any]
) -> None:
    assert_unauthenticated(auth_client, encode(private_key, claims(**overrides)))


def test_wrong_signature(auth_client: TestClient) -> None:
    other_key = ec.generate_private_key(ec.SECP256R1())
    assert_unauthenticated(auth_client, encode(other_key, claims()))


@pytest.mark.parametrize("algorithm", ["HS256", "ES384", "none"])
def test_wrong_algorithm_rejected_before_jwks(
    auth_client: TestClient, jwks_transport: Mock, algorithm: str
) -> None:
    key = (
        ec.generate_private_key(ec.SECP384R1())
        if algorithm == "ES384"
        else (None if algorithm == "none" else "local-test-key-only-with-at-least-32-bytes")
    )
    token = jwt.encode(claims(), key, algorithm=algorithm, headers={"kid": "test-key"})
    assert_unauthenticated(auth_client, token)
    jwks_transport.assert_not_called()


def test_unknown_signing_key(
    auth_client: TestClient, private_key: ec.EllipticCurvePrivateKey
) -> None:
    token = jwt.encode(claims(), private_key, algorithm="ES256", headers={"kid": "unknown"})
    assert_unauthenticated(auth_client, token)


def test_jwks_unavailable(
    auth_client: TestClient, private_key: ec.EllipticCurvePrivateKey, jwks_transport: Mock
) -> None:
    from urllib.error import URLError

    jwks_transport.side_effect = URLError("test transport unavailable")
    assert_unauthenticated(auth_client, encode(private_key, claims()))


def test_jwks_cache_and_fixed_url(
    auth_client: TestClient, private_key: ec.EllipticCurvePrivateKey, jwks_transport: Mock
) -> None:
    token = encode(private_key, claims())
    for _ in range(2):
        assert (
            auth_client.get(
                "/_test/session", headers={"Authorization": f"bearer {token}"}
            ).status_code
            == 200
        )
    assert jwks_transport.call_count == 1
    assert (
        jwks_transport.call_args.args[0].full_url == f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    )
    assert auth.get_jwks_client(SUPABASE_URL) is auth.get_jwks_client(SUPABASE_URL)


def test_public_routes_stay_public(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import rooms

    monkeypatch.setattr(rooms, "list_rooms", lambda db: [])
    auth_client.app.dependency_overrides[get_db] = lambda: object()
    assert auth_client.get("/health").status_code == 200
    assert auth_client.get("/api/v1/rooms").json() == []


@pytest.fixture
def admin_db() -> Iterator[DbSession]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with DbSession(engine) as db:
        room_id = uuid4()
        db.add(
            Room(
                id=room_id,
                name="Original room",
                description="Test room",
                category="library",
                latitude=29.65,
                longitude=-82.34,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        db.info.update(room_id=room_id, get_db_calls=0)
        yield db
    engine.dispose()


@pytest.fixture
def admin_publish(monkeypatch: pytest.MonkeyPatch) -> Mock:
    publisher = Mock()
    monkeypatch.setattr(admin_service, "publish", publisher)
    return publisher


@pytest.fixture
def admin_auth_client(
    auth_client: TestClient, admin_db: DbSession, admin_publish: Mock
) -> TestClient:
    # Keep both auth dependencies real; only the database and broadcast transport are isolated.
    def isolated_db() -> Iterator[DbSession]:
        admin_db.info["get_db_calls"] += 1
        yield admin_db

    auth_client.app.dependency_overrides[get_db] = isolated_db

    @auth_client.app.get("/_test/admin")
    def admin(current: Annotated[auth.Admin, Depends(auth.require_admin)]) -> auth.Admin:
        return current

    return auth_client


def list_test_admin(db: DbSession) -> None:
    db.add(
        AdminUser(user_id=UUID(USER_ID), display_name="Test admin", created_at=datetime.now(UTC))
    )
    db.commit()


ADMIN_ROOM = {
    "name": "New test room",
    "description": "Admin authorization test",
    "category": "library",
    "latitude": 29.65,
    "longitude": -82.34,
}
ADMIN_OPERATIONS = [
    ("POST", "/api/v1/admin/rooms", ADMIN_ROOM),
    ("PATCH", "/api/v1/admin/rooms/{room_id}", {"name": "Unauthorized edit"}),
    ("POST", "/api/v1/admin/rooms/{room_id}/archive", None),
]


@pytest.mark.parametrize("method,path,payload", ADMIN_OPERATIONS)
@pytest.mark.parametrize(
    "credential",
    ["missing", "malformed", "expired", "signature", "audience", "issuer", "algorithm"],
)
def test_admin_routes_reject_invalid_tokens(
    admin_auth_client: TestClient,
    admin_db: DbSession,
    private_key: ec.EllipticCurvePrivateKey,
    admin_publish: Mock,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    credential: str,
) -> None:
    list_test_admin(admin_db)
    token_claims = claims(is_anonymous=False)
    signing_key = private_key
    if credential == "expired":
        token_claims["exp"] = int(time()) - 60
    elif credential == "signature":
        signing_key = ec.generate_private_key(ec.SECP256R1())
    elif credential == "audience":
        token_claims["aud"] = "anon"
    elif credential == "issuer":
        token_claims["iss"] = "https://other-project.supabase.co/auth/v1"
    token = encode(signing_key, token_claims)
    if credential == "algorithm":
        token = jwt.encode(token_claims, "local-test-key-with-at-least-32-bytes", algorithm="HS256")
    headers = (
        {}
        if credential == "missing"
        else {"Authorization": f"Bearer {'invalid' if credential == 'malformed' else token}"}
    )
    response = admin_auth_client.request(
        method, path.format(room_id=admin_db.info["room_id"]), json=payload, headers=headers
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert admin_db.info["get_db_calls"] == 0
    room = admin_db.get(Room, admin_db.info["room_id"])
    assert (room.name, room.status) == ("Original room", "active")
    admin_publish.assert_not_called()


@pytest.mark.parametrize("method,path,payload", ADMIN_OPERATIONS)
@pytest.mark.parametrize("anonymous,listed", [(True, False), (True, True), (False, False)])
def test_admin_routes_reject_anonymous_and_unlisted_callers(
    admin_auth_client: TestClient,
    admin_db: DbSession,
    private_key: ec.EllipticCurvePrivateKey,
    admin_publish: Mock,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    anonymous: bool,
    listed: bool,
) -> None:
    if listed:
        list_test_admin(admin_db)
    token = encode(private_key, claims(is_anonymous=anonymous, app_metadata={"role": "admin"}))
    response = admin_auth_client.request(
        method,
        path.format(room_id=admin_db.info["room_id"]),
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    room = admin_db.get(Room, admin_db.info["room_id"])
    assert (room.name, room.status) == ("Original room", "active")
    assert admin_db.scalar(select(func.count()).select_from(Room)) == 1
    assert admin_db.scalar(select(func.count()).select_from(AdminUser)) == int(listed)
    admin_publish.assert_not_called()


def test_listed_non_anonymous_admin_can_manage_rooms(
    admin_auth_client: TestClient, admin_db: DbSession, private_key: ec.EllipticCurvePrivateKey
) -> None:
    list_test_admin(admin_db)
    token = encode(private_key, claims(is_anonymous=False))
    headers = {"Authorization": f"Bearer {token}"}
    current = admin_auth_client.get("/_test/admin", headers=headers)
    assert current.status_code == 200
    assert current.json() == {"user_id": USER_ID}
    created = admin_auth_client.post("/api/v1/admin/rooms", json=ADMIN_ROOM, headers=headers)
    assert created.status_code == 201
    room_id = created.json()["id"]
    updated = admin_auth_client.patch(
        f"/api/v1/admin/rooms/{room_id}", json={"name": "Updated test room"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated test room"
    archived = admin_auth_client.post(f"/api/v1/admin/rooms/{room_id}/archive", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    # Each request shares one get_db dependency between authorization and the operation.
    assert admin_db.info["get_db_calls"] == 4


def test_removing_allow_list_entry_revokes_the_same_token(
    admin_auth_client: TestClient, admin_db: DbSession, private_key: ec.EllipticCurvePrivateKey
) -> None:
    list_test_admin(admin_db)
    token = encode(private_key, claims(is_anonymous=False))
    headers = {"Authorization": f"Bearer {token}"}
    assert admin_auth_client.get("/_test/admin", headers=headers).status_code == 200
    admin_db.delete(admin_db.get(AdminUser, UUID(USER_ID)))
    admin_db.commit()
    response = admin_auth_client.get("/_test/admin", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_non_uuid_verified_subject_is_forbidden(
    admin_auth_client: TestClient, private_key: ec.EllipticCurvePrivateKey
) -> None:
    token = encode(private_key, claims(sub="not-a-uuid", is_anonymous=False))
    response = admin_auth_client.get("/_test/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
