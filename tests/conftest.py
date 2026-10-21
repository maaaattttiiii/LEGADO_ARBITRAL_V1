import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.database  # noqa: F401  (registra el listener de PRAGMA foreign_keys)
from app.database import Base, get_db
from app.models import RolUsuario, Usuario
from app.seguridad import hash_password

CLAVE_TESORERO = "tesorero-secreto-123"


@pytest.fixture(autouse=True)
def _limiter_limpio():
    """Cada test arranca con un limitador de login vacío (aislamiento)."""
    from app.limiter import LimitadorLogin
    from app.main import app

    app.state.limiter = LimitadorLogin()
    yield


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def tesorero(db_session):
    usuario = Usuario(
        email="tesorero@cabm.org.ar",
        password_hash=hash_password(CLAVE_TESORERO),
        rol=RolUsuario.TESORERO,
    )
    db_session.add(usuario)
    db_session.flush()
    return usuario


@pytest.fixture()
def client_anonimo(db_session):
    from app.main import app

    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def client(client_anonimo, tesorero):
    """Cliente autenticado como tesorero (contexto por defecto de la suite)."""
    respuesta = client_anonimo.post(
        "/login",
        data={"email": tesorero.email, "password": CLAVE_TESORERO},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    return client_anonimo
