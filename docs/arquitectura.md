# Arquitectura — Legado Arbitral (CABM)

> Documento técnico de referencia: cómo se organiza el sistema, cómo viaja una
> petición entre capas y dónde va cada tipo de cambio. Complementa
> [`dominio.md`](dominio.md) (reglas de negocio) y
> [`specs/v2_seguridad_auditoria.md`](specs/v2_seguridad_auditoria.md)
> (especificación de seguridad y operación).

## 1. Contexto

Aplicación web **server-side** para la tesorería de un colegio de árbitros:
padrón, programación de partidos, designación de ternas, liquidación de
honorarios y viáticos, cuenta corriente y cierres contables mensuales.

| Atributo | Decisión |
|---|---|
| Estilo | Monolito modular, renderizado en servidor (Jinja2) |
| Usuarios | 1 tesorero (administrador) + N árbitros con portal de solo lectura |
| Escala | Una sola instancia; SQLite en desarrollo, PostgreSQL en producción |
| Zona horaria | Formularios en ART (UTC-3 fijo); persistencia en UTC |
| Dinero | `Decimal` + `Numeric(12,2)`, nunca `float` |
| Historial | Inmutable: correcciones por movimientos de ajuste, no por edición |

## 2. Vista de capas

```
┌──────────────────────────────────────────────────────────────────────┐
│ Navegador (formularios HTML + Bootstrap, sin SPA ni API pública)     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTP (cookie cabm_session firmada)
┌───────────────────────────────▼──────────────────────────────────────┐
│ app/main.py — FastAPI                                                │
│  • SessionMiddleware (cookie HttpOnly, SameSite=Lax, 8 h)            │
│  • app.state.limiter = LimitadorLogin()                              │
│  • handlers: NoAutenticado→303 · AccesoDenegado→403 ·                │
│              CambioPasswordRequerido→303                             │
├──────────────────────────────────────────────────────────────────────┤
│ app/routes/*.py — capa de presentación                               │
│  • parsea formularios (Form/Query)                                   │
│  • dependencias: get_db (sesión SQLAlchemy) + guardas de rol         │
│  • llama UN servicio, hace commit/rollback                           │
│  • responde: RedirectResponse 303 · TemplateResponse 200/400/403     │
├──────────────────────────────────────────────────────────────────────┤
│ app/services/*.py — lógica de negocio                                │
│  • valida reglas del dominio y lanza excepciones de negocio          │
│  • escribe vía ORM y hace SOLO flush() (nunca commit/rollback)       │
│  • devuelve modelos/DTOs; no conoce Request, sesión HTTP ni HTML     │
├──────────────────────────────────────────────────────────────────────┤
│ app/models/*.py — SQLAlchemy 2.1 declarativo tipado                  │
│  • Mapped/mapped_column, TimestampMixin, naming convention           │
│  • enums portables: VARCHAR(20) + CHECK explícito                    │
│  • relaciones y FK con ondelete explícito                            │
├──────────────────────────────────────────────────────────────────────┤
│ app/database.py — engine + SessionLocal + Base + get_db              │
│  • SQLite dev / PostgreSQL prod (DATABASE_URL)                       │
│  • PRAGMA foreign_keys=ON por event listener en SQLite               │
├──────────────────────────────────────────────────────────────────────┤
│ Alembic (esquema)              │  Jinja2 (app/templates/)             │
│  • única vía de cambio         │  • filtros fecha_local/moneda/      │
│  • batch_alter_table SQLite    │    periodo_local                    │
└────────────────────────────────┴─────────────────────────────────────┘
```

### Responsabilidades por archivo

| Archivo | Rol |
|---|---|
| `app/main.py` | Crea `FastAPI`, registra middleware, routers y handlers de error |
| `app/database.py` | `engine`, `SessionLocal`, `Base`, `get_db()` y `PRAGMA foreign_keys` |
| `app/seguridad.py` | scrypt, constantes de sesión, guardas y `usuario_actual()` |
| `app/limiter.py` | `LimitadorLogin` en memoria (ventana y bloqueo por `(IP, email)`) |
| `app/templating.py` | `Jinja2Templates` con rutas absolutas y filtros de formato |
| `app/tiempo.py` | Conversión ART ⇄ UTC (`combinar`, `a_local`, `formatear`) |
| `app/periodos.py` | Normalización `AAAA-MM` y `periodo_de()` en ART |
| `app/formato.py` | `formatear_moneda()` (formato argentino, único punto) |
| `app/routes/*.py` | Orquestación HTTP + transacción |
| `app/services/*.py` | Reglas de negocio y escritura |
| `app/models/*.py` | Esquema y enums del dominio |
| `app/seeds/*.py` | Datos oficiales y cuentas demo idempotentes |
| `alembic/versions/*` | Migraciones del esquema |

## 3. Ciclo de vida de una petición

Ejemplo: el tesorero liquida un partido.

```
POST /tesoreria/liquidar/42
  │
  ├─ SessionMiddleware ──► valida/deserializa cookie cabm_session
  ├─ Depends(get_db) ────► abre Session SQLAlchemy (autoflush=False)
  ├─ Depends(requiere_tesorero)
  │     ├─ usuario_actual(): revalida usuario en DB (activo, rol)
  │     ├─ sin sesión → NoAutenticado → handler 303 /login?next=…
  │     ├─ rol ≠ TESORERO → AccesoDenegado → handler 403
  │     └─ debe_cambiar_password → CambioPasswordRequerido → 303
  ├─ ruta: liquidar_partido(db, partido_id, usuario_id=usuario.id)
  │     ├─ services/liquidacion.py: valida (período abierto, tarifa,
  │     │   viático, idempotencia) y agrega movimientos
  │     └─ flush() (sin commit: la transacción es de la ruta)
  ├─ ruta: db.commit()  (o db.rollback() si el servicio lanza)
  └─ RedirectResponse 303 /tesoreria?periodo=…&ok=…
```

Reglas de la capa HTTP:

- **Una ruta = orquestación**: parsear → servicio → `commit`/`rollback` →
  redirigir (303) o renderizar.
- Errores de validación de negocio (`ValueError` del dominio) se muestran en el
  formulario con **400** y mensaje; nunca un 500 ni un `422` crudo.
- Las mutaciones exitosas siempre redirigen (patrón PRG) para evitar doble envío.
- La ruta toma `usuario` de `Depends(requiere_tesorero)`; **jamás** de un campo
  del formulario (RN-49).

### Matriz de errores

| Situación | Excepción | Respuesta |
|---|---|---|
| Sin sesión válida | `NoAutenticado` | `303 /login?next=<ruta>` |
| Rol incorrecto | `AccesoDenegado` | `403` + `403.html` |
| Clave inicial sin cambiar | `CambioPasswordRequerido` | `303 /cambiar-password` |
| Login inválido | — | `401` con mensaje genérico |
| Par IP/email bloqueado | — | `429` + `Retry-After` |
| Período cerrado | `PeriodoCerrado` | `400` en el formulario |
| Datos inválidos | `ValueError` de dominio | `400` con mensaje |

## 4. Autenticación, sesión y autorización

- **Password**: `hash_password()` usa scrypt de la stdlib con sal aleatoria en
  el formato `scrypt$n$r$p$sal$hash`; `verificar_password()` compara en tiempo
  constante. Nunca se loguea ni se guarda en claro.
- **Sesión**: cookie `cabm_session` firmada con `CABM_SECRET_KEY` (HMAC de
  Starlette). `HttpOnly`, `SameSite=Lax`, `max_age` 8 h; `Secure` cuando
  `CABM_HTTPS_ONLY=1`.
- **Contenido de la cookie**: `usuario_id`, `rol`, `nombre`, `arbitro_id` y
  `debe_cambiar_password`. Nada sensible.
- **Revalidación**: `usuario_actual()` consulta la base en cada request; si el
  usuario fue desactivado, la sesión se limpia (RN-46).
- **Guardas**: dependencias de router (`APIRouter(dependencies=[...])`), no
  chequeos manuales dentro de cada endpoint.
- **Aislamiento del portal**: el `arbitro_id` sale siempre del usuario
  autenticado; nunca de la URL (RN-45).
- **Rate limiting**: `LimitadorLogin` cuenta fallos por `(IP, email)` en
  memoria (`app.state.limiter`). 5 fallos / 15 min → bloqueo 15 min. Es estado
  de proceso: una sola instancia (deuda conocida).

```
login ──► limitador ──(bloqueado)──► 429 + Retry-After
             │
             └─► autenticar() ──(ok)──► session.clear() + datos + redirect
                          └─(fallo)──► registrar fallo + 401
```

## 5. Modelo de datos (resumen)

```
Arbitro 1───* Usuario              (un árbitro = una cuenta de portal)
Arbitro 1───* Designacion
Cancha  1───* Partido
Torneo  1───* Partido
Partido 1───* Designacion
Partido 1───* MovimientoCuentaCorriente   (vía Designacion)
Designacion 1───* MovimientoCuentaCorriente
Tarifa (categoría de torneo, rol, escalafón, vigencia)
PrecioCombustible (vigencia)
CierrePeriodo (AAAA-MM único; reabierto_en NULL = cerrado)
AuditoriaPeriodo (append-only: CIERRE / REAPERTURA)
```

Decisiones estructurales:

- **Snapshot financiero**: `Designacion.honorario` se congela al designar o
  liquidar; cambiar aranceles después no altera movimientos.
- **Saldo calculado**: `SUM(CREDITO) − SUM(DEBITO)`; no existe columna saldo.
- **Idempotencia**: `UNIQUE(designacion_id, concepto)` impide duplicar
  honorarios, retenciones o viáticos.
- **Enums portables**: `columna_enum()` genera `VARCHAR(20)` y
  `check_enum()` declara el `CHECK` en la tabla. Prohibido `native_enum` y
  `create_constraint=True` (Alembic duplica el CHECK).
- **Auditoría**: `usuario_id` nullable con FK `ON DELETE RESTRICT` en
  movimientos y cierres; `auditoria_periodo` es append-only.
- **Naming convention** en `Base.metadata`: permite a Alembic nombrar y
  revertir constraints.

## 6. Frontend

- **Jinja2** con herencia desde `base.html`; navbar condicionada por rol.
- Filtros globales: `fecha_local` (UTC→ART), `moneda` (formato argentino) y
  `periodo_local` (fecha→`AAAA-MM` contable). Las plantillas **no** formatean
  a mano.
- Formularios HTML clásicos con `POST` y redirect 303; modales de Bootstrap
  para altas rápidas. Sin JavaScript de negocio: la verdad está en el servidor.
- Mensajes de resultado vía query string (`?ok=`, `?error=`) y re-render 400.

## 7. Migraciones (Alembic)

Cadena vigente:

```
aab622ffc2bc  usuarios y autenticación
      │
c1d2e3f4a5b6  clave inicial obligatoria
      │
d2e3f4a5b6c7  auditoría de operaciones
      │
d3e4f5a6b7c8  reapertura y auditoría de períodos   ← head
```

Proceso:

1. Cambiar el modelo.
2. `alembic revision --autogenerate -m "descripcion"` (revisar el archivo).
3. `& C:\Python314\python.exe -m alembic upgrade head`.
4. `& C:\Python314\python.exe -m alembic check` → *"No new upgrade operations detected"*.

Notas:

- En SQLite los cambios de columna/FK usan `batch_alter_table` (recrea la tabla).
- `Base.metadata.create_all()` solo está permitido en tests.
- Los datos oficiales se cargan con el seed idempotente, nunca en migraciones.

## 8. Despliegue

| Pieza | Detalle |
|---|---|
| Imagen | `python:3.14-slim`, usuario sin privilegios `cabm` |
| Arranque | `alembic upgrade head` y luego `uvicorn app.main:app` |
| Salud | `HEALTHCHECK` contra `/login` (público) |
| Compose | `db` PostgreSQL 17 con `pg_isready`; `app` espera `service_healthy` |
| Config | `.env` (`DATABASE_URL`, `CABM_SECRET_KEY`, `CABM_HTTPS_ONLY`, `CABM_PORT`) |
| Backup | Procedimiento y variables en [`despliegue.md`](despliegue.md) |

`CABM_SECRET_KEY` es obligatoria en producción: sin ella se genera un secreto
efímero por proceso y las sesiones se invalidan al reiniciar.

## 9. Estrategia de tests

- **pytest + httpx/TestClient**, base SQLite en memoria con
  `Base.metadata.create_all()`; cada test parte de un esquema limpio.
- `tests/conftest.py` provee:
  - `db_session` (sesión directa para servicios),
  - `tesorero` y `client` (cliente ya autenticado),
  - `client_anonimo` (sin cookie),
  - fixture autouse que reinicia `LimitadorLogin` entre tests.
- Cobertura por capas: modelos y cálculo (unitarios), servicios (reglas),
  rutas (status, redirects, HTML), deploy (contenido de Docker/compose).
- **TDD estricto** en cambios de negocio: test que falla → mínimo código →
  triangulación → refactor.

## 10. ADR (decisiones registradas)

| ADR | Decisión | Motivo |
|---|---|---|
| ADR-01 | Dinero con `Decimal`/`Numeric` | Exactitud contable |
| ADR-02 | Saldo calculado, no persistido | Evita desincronización |
| ADR-03 | Honorario congelado por designación | Historial inmutable |
| ADR-04 | ART⇄UTC en una capa (`tiempo.py`) | Evitar corrimientos de día |
| ADR-05 | Render server-side con Jinja2 | Simplicidad operativa |
| ADR-06 | Sesión en cookie firmada | Sin store de sesiones |
| ADR-07 | Enums `VARCHAR` + `CHECK` | Portabilidad SQLite/PostgreSQL |
| ADR-08 | Servicios con `flush()`, commit en la ruta | Transacción única por request |
| ADR-09 | Auditoría append-only | Trazabilidad de cierres/reaperturas |
| ADR-10 | Rate limiter en memoria | Simplicidad; deuda para multi-instancia |

## 11. Checklist para agregar una funcionalidad

1. Identificar la regla de negocio y su governance (`AGENTS.md` §7).
2. Escribir/actualizar la spec en `docs/specs/` si cambia un contrato.
3. Test RED en la capa correcta (servicio si es lógica, ruta si es HTTP).
4. Implementar en `app/services/` (sin `commit`); la ruta solo orquesta.
5. Si hay esquema: modelo → migración → `upgrade head` → `alembic check`.
6. Template con filtros existentes; mensajes de error en 400.
7. Actualizar `docs/dominio.md`, `docs/specs/`, `CHANGES.md` y, si cambió una
   capa, este documento.
8. Suite completa en verde antes de commitear.
