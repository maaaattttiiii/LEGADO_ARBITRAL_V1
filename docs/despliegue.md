# Despliegue con Docker

Servicio web (FastAPI) + PostgreSQL 17. El contenedor de la aplicación corre
`alembic upgrade head` antes de levantar `uvicorn`, así que el esquema siempre
queda al día.

## Puesta en marcha

```powershell
Copy-Item .env.example .env
# Editá .env: POSTGRES_PASSWORD, CABM_SECRET_KEY (openssl rand -hex 32) y
# CABM_HTTPS_ONLY (0 para HTTP local, 1 detrás de HTTPS).
docker compose up -d --build
```

La app queda en <http://localhost:8000>. La primera vez, cargá los datos
oficiales y las cuentas iniciales:

```powershell
docker compose exec app python -m app.seeds.datos_iniciales
```

Credenciales iniciales (cambiar en el primer ingreso): `tesorero@cabm.org.ar` /
`cabm2026`. Cada árbitro recibe `<email o legajo>@cabm.org.ar` / `arbitro123`.

## Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `POSTGRES_PASSWORD` | Sí | Clave del usuario de PostgreSQL (Compose la exige). |
| `CABM_SECRET_KEY` | Sí | Firma la cookie de sesión. Generar con `openssl rand -hex 32`. Sin ella se usa una clave efímera por proceso (invalida sesiones al reiniciar). |
| `CABM_HTTPS_ONLY` | No (default 1 en Compose) | `1` marca la cookie como `Secure`: solo detrás de TLS. En pruebas locales por HTTP usar `0`. |
| `DATABASE_URL` | La define Compose | `postgresql+psycopg://usuario:clave@db:5432/base`. |
| `CABM_PORT` | No | Puerto publicado en el host (8000). |

## TLS

`CABM_HTTPS_ONLY=1` no habilita HTTPS por sí solo: asume que hay un proxy
inverso (Caddy, Nginx, Traefik) terminando TLS delante del contenedor. Sin ese
proxy, el navegador no enviará la cookie y el login no persistirá.

## Actualizaciones

```powershell
git pull
docker compose up -d --build
```

Las migraciones corren solas al arrancar. Para auditar el esquema:
`docker compose exec app python -m alembic current`.

## Backup y restauración

```powershell
docker compose exec db pg_dump -U cabm -Fc cabm > cabm-$(Get-Date -Format yyyyMMdd).dump
docker compose exec -T db pg_restore -U cabm -d cabm --clean < cabm-20260101.dump
```

Los datos viven en el volumen `cabm_pgdata`; borrarlo elimina la base.

## Notas de producción

- Cambiar las claves del seed en el primer ingreso (el sistema lo exige con
  `debe_cambiar_password`).
- `LimitadorLogin` es estado en memoria: con más de una instancia hay que
  moverlo a Redis o a la base (RN-48).
- El contenedor corre como usuario `cabm` sin privilegios y expone un
  `HEALTHCHECK` sobre `/login`.
