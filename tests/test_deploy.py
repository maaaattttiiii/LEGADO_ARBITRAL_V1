"""Configuración de despliegue: Dockerfile, Compose y variables de entorno."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _leer(nombre: str) -> str:
    return (RAIZ / nombre).read_text(encoding="utf-8")


def test_dockerfile_migra_antes_de_arrancar():
    texto = _leer("Dockerfile")

    assert "alembic upgrade head" in texto
    assert "uvicorn app.main:app" in texto
    # Las migraciones deben correr antes que el servidor.
    assert texto.index("alembic upgrade head") < texto.index(
        "uvicorn app.main:app"
    )
    assert "USER cabm" in texto
    assert "HEALTHCHECK" in texto


def test_compose_levanta_postgres_y_la_app():
    texto = _leer("docker-compose.yml")

    assert "postgres:17" in texto
    assert "DATABASE_URL: postgresql+psycopg://" in texto
    assert "CABM_SECRET_KEY" in texto
    assert "CABM_HTTPS_ONLY" in texto
    assert "condition: service_healthy" in texto
    assert "cabm_pgdata" in texto


def test_env_de_ejemplo_documenta_las_variables_de_produccion():
    texto = _leer(".env.example")

    for variable in (
        "POSTGRES_PASSWORD",
        "CABM_SECRET_KEY",
        "CABM_HTTPS_ONLY",
    ):
        assert variable in texto
    assert "openssl rand -hex 32" in texto


def test_dockerignore_no_mete_datos_locales_en_la_imagen():
    texto = _leer(".dockerignore")

    assert ".env" in texto.splitlines()
    assert "*.db" in texto
    assert "tests/" in texto
