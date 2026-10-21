# Spec V2.0 — Seguridad, auditoría y operación

| Campo | Valor |
|---|---|
| Versión | 2.0 |
| Estado | **Implementado y verificado** (2026-10-21) |
| Alcance | 5 entregas: clave inicial, rate limiting, auditoría, Docker/PostgreSQL, reaperturas y cierres en lote |
| Dominios | Seguridad (CRÍTICO), Tesorería (CRÍTICO), Despliegue (MEDIO) |
| Tests | 75 nuevos (suite total 401) |
| Migraciones | `c1d2e3f4a5b6`, `d2e3f4a5b6c7`, `d3e4f5a6b7c8` |

> Esta spec documenta el contrato de las cinco tareas de V2.0. Se mantiene como
> referencia de aceptación: cualquier cambio futuro en estas áreas debe
> actualizarla y mantener sus escenarios en verde.

## 1. Contexto y objetivos

V1.0 entregó el circuito financiero completo pero sin autenticación ni
trazabilidad: cualquiera con acceso a la red podía operar, las cuentas no
tenían clave obligatoria y los cierres eran irreversibles. V2.0 agrega:

1. **Identidad**: cuentas con clave inicial que debe cambiarse antes de operar.
2. **Protección del login**: límite de intentos por IP + email.
3. **Trazabilidad**: quién ejecutó cada movimiento y cada cierre.
4. **Operación**: imagen Docker y PostgreSQL para producción.
5. **Corrección controlada**: reapertura auditada y cierre masivo de períodos.

### No objetivos

- Multi-tenant, SSO, 2FA o recuperación de clave por email.
- API pública/JSON: la aplicación sigue siendo server-side.
- Rate limiting distribuido (una instancia; deuda documentada).
- Edición o borrado de movimientos históricos.

## 2. F1 — Cambio de clave inicial obligatorio

### Requisitos

| ID | Requisito |
|---|---|
| RF-1.1 | `Usuario.debe_cambiar_password` (Boolean, default `false`) marca cuentas con clave provisoria. |
| RF-1.2 | Toda cuenta creada por el seed nace con la marca activa. Las cuentas preexistentes cuya clave siga siendo la default se marcan al re-sembrar (idempotente). |
| RF-1.3 | Con la marca activa, cualquier ruta protegida redirige a `/cambiar-password` (`CambioPasswordRequerido` → 303). El login también redirige allí. |
| RF-1.4 | `GET /cambiar-password` muestra el formulario (actual, nueva, repetir). `POST` valida: actual correcta, nueva ≥ 8 caracteres, nueva ≠ actual y coincidencia con la repetición. |
| RF-1.5 | Al guardar: `hash_password()` sobre la nueva, se limpia la marca en la base **y** en la sesión, y se redirige con mensaje de éxito. |
| RF-1.6 | El hash y las claves nunca se registran en logs ni se devuelven en la respuesta. |

### Escenarios

```gherkin
Escenario: primera sesión redirige al cambio
  Dado un usuario con debe_cambiar_password = true
  Cuando inicia sesión con su clave provisoria
  Entonces recibe 303 a /cambiar-password
  Y cualquier otra ruta protegida también redirige allí

Escenario: cambio exitoso
  Dado el usuario autenticado con la marca activa
  Cuando envía actual correcta, nueva de 8+ caracteres y repetición igual
  Entonces la marca queda en false en la base y en la sesión
  Y puede acceder al panel de su rol

Escenario: validaciones
  Cuando la actual no coincide → 400 con mensaje
  Cuando la nueva tiene menos de 8 caracteres → 400
  Cuando la nueva repite la actual → 400
  Cuando la repetición no coincide → 400
  Y en ningún caso se modifica la clave
```

### Contrato HTTP

| Método | Ruta | Éxito | Error |
|---|---|---|---|
| GET | `/cambiar-password` | 200 formulario | 303 si no hay sesión |
| POST | `/cambiar-password` | 303 al panel | 400 re-render con mensaje |

### Datos

`usuario.debe_cambiar_password BOOLEAN NOT NULL DEFAULT false` (migración
`c1d2e3f4a5b6`). El seed usa `verificar_password()` contra la clave default
para decidir si marca una cuenta existente.

### Verificación

`tests/test_password.py` (15). Reglas RN-47 y RN-42; regla dura 40.

## 3. F2 — Rate limiting del login

### Requisitos

| ID | Requisito |
|---|---|
| RF-2.1 | Contar fallos por par `(IP, email)` normalizado, en ventana deslizante de 15 minutos. |
| RF-2.2 | Alcanzados **5 fallos**, el par queda bloqueado 15 minutos: `POST /login` responde **429** con `Retry-After` en segundos. |
| RF-2.3 | El bloqueo se consulta **antes** de verificar credenciales: ni siquiera la clave correcta pasa mientras dure. |
| RF-2.4 | Un login exitoso limpia el contador del par. |
| RF-2.5 | El estado vive en `app.state.limiter` (memoria del proceso). No se persiste. |
| RF-2.6 | La IP se obtiene del request; a igual email desde otra IP, el conteo es independiente. |

### Escenarios

```gherkin
Escenario: bloqueo tras cinco fallos
  Dado 4 intentos fallidos para (IP, email)
  Cuando falla el quinto
  Entonces la respuesta es 429 con Retry-After
  Y el siguiente intento con clave correcta también es 429

Escenario: éxito limpia el contador
  Dado 3 fallos previos
  Cuando ingresa con la clave correcta
  Entonces recibe 303
  Y el contador vuelve a cero

Escenario: ventana expirada
  Dado un bloqueo vencido
  Cuando reintenta
  Entonces las credenciales se evalúan normalmente
```

### Contrato HTTP

`POST /login` → 303 (éxito) · 401 (credenciales) · **429** + `Retry-After`
(bloqueado). Sin cambios de esquema.

### Verificación

`tests/test_login_limiter.py` (9), con fixture autouse que reinicia el
limitador. RN-48, regla dura 41. Deuda: estado no compartido entre instancias.

## 4. F3 — Auditoría de operaciones sensibles

### Requisitos

| ID | Requisito |
|---|---|
| RF-3.1 | `MovimientoCuentaCorriente.usuario_id` y `CierrePeriodo.usuario_id` (nullable, FK `usuario.id`, `ON DELETE RESTRICT`). |
| RF-3.2 | Los servicios de escritura aceptan `usuario_id=None` y lo persisten en cada movimiento: liquidación (honorario, retención, viático), reintegro por mora, ajuste manual y cierre de período. |
| RF-3.3 | Las rutas obtienen el usuario de `Depends(requiere_tesorero)`; nunca de un campo del formulario. |
| RF-3.4 | El detalle de cuenta (`/tesoreria/arbitro/{id}`) muestra la columna **Registró**. |
| RF-3.5 | La auditoría es compatible con datos históricos: los movimientos previos quedan con `usuario_id = NULL`. |
| RF-3.6 | La FK `RESTRICT` impide borrar usuarios con operaciones registradas. |

### Escenarios

```gherkin
Escenario: liquidación auditada
  Dado un tesorero autenticado
  Cuando liquida un partido
  Entonces todos los movimientos creados guardan su usuario_id
  Y el detalle muestra quién los registró

Escenario: cierre auditado
  Cuando cierra un período
  Entonces CierrePeriodo.usuario_id identifica al tesorero

Escenario: datos históricos
  Dado un movimiento con usuario_id NULL
  Cuando se consulta la cuenta
  Entonces la columna muestra "—" sin errores
```

### Verificación

`tests/test_auditoria.py` (7). Migración `d2e3f4a5b6c7`. RN-49, regla dura 42.

## 5. F4 — Docker y PostgreSQL

### Requisitos

| ID | Requisito |
|---|---|
| RF-4.1 | `Dockerfile` sobre `python:3.14-slim`, instala `requirements.txt`, ejecuta como usuario sin privilegios `cabm`. |
| RF-4.2 | El contenedor ejecuta `alembic upgrade head` antes de `uvicorn`; la app escucha en `0.0.0.0`. |
| RF-4.3 | `HEALTHCHECK` contra `/login` (ruta pública) para el orquestador. |
| RF-4.4 | `docker-compose.yml`: servicio `db` PostgreSQL 17 con `pg_isready`; `app` depende de `service_healthy`. |
| RF-4.5 | Variables: `DATABASE_URL` (obligatoria, `postgresql+psycopg://…`), `CABM_SECRET_KEY` (obligatoria), `CABM_HTTPS_ONLY` (default 1), `CABM_PORT`. |
| RF-4.6 | `.env.example` documenta todas las variables; `.dockerignore` excluye tests, base local y entornos. |
| RF-4.7 | `docs/despliegue.md` describe arranque, migraciones, backups y rotación del secreto. |

### Escenarios

```gherkin
Escenario: arranque limpio
  Dado un volumen PostgreSQL vacío
  Cuando se levanta docker compose
  Entonces Alembic aplica todas las migraciones
  Y /login responde 200 cuando el healthcheck pasa

Escenario: configuración incompleta
  Cuando falta DATABASE_URL o CABM_SECRET_KEY
  Entonces compose falla explícitamente antes de arrancar la app
```

### Verificación

`tests/test_deploy.py` (4): contenido del Dockerfile, healthcheck, compose y
variables. Validación manual con `docker compose config`.

## 6. F5 — Reapertura de período y cierres en lote

### Requisitos

| ID | Requisito |
|---|---|
| RF-5.1 | `cierre_periodo.reabierto_en` (tz-aware, nullable). `NULL` = cierre vigente; con fecha = período habilitado de nuevo. |
| RF-5.2 | `reabrir_periodo()` exige un cierre **vigente** y un **motivo ≥ 10 caracteres**; si no está cerrado o ya fue reabierto → error sin escrituras. |
| RF-5.3 | La reapertura marca `reabierto_en` y agrega una fila `REAPERTURA` en `auditoria_periodo` con período, motivo, usuario y fecha. |
| RF-5.4 | Con el período reabierto, `validar_abierto()` deja pasar altas, designaciones, liquidaciones, cobros y ajustes. |
| RF-5.5 | Un nuevo cierre reactiva la **misma** fila de `CierrePeriodo` (una por período), limpia `reabierto_en` y audita `CIERRE`. |
| RF-5.6 | `cerrar_periodos()` acepta varios períodos en texto (coma, punto y coma o espacios) o lista; valida **todos** antes de escribir y cierra en una transacción. |
| RF-5.7 | Período inválido, lista vacía, repetidos o alguno ya cerrado → error y **cero** cambios (atomicidad). |
| RF-5.8 | `auditoria_periodo` es append-only y se muestra en el panel (últimos 10 registros). |
| RF-5.9 | Solo el tesorero accede a `POST /tesoreria/reapertura` y `POST /tesoreria/cierres-lote`. |

### Escenarios

```gherkin
Escenario: reabrir un mes cerrado
  Dado el período 2026-03 cerrado
  Cuando el tesorero lo reabre con un motivo de 10+ caracteres
  Entonces reabierto_en queda seteado
  Y se audita REAPERTURA con motivo y usuario
  Y se puede crear un partido de marzo

Escenario: reaperturas inválidas
  Cuando el período está abierto → 400
  Cuando ya fue reabierto → 400
  Cuando el motivo tiene menos de 10 caracteres → 400
  Y no se escribe nada

Escenario: ciclo cierre → reapertura → cierre
  Dado un período reabierto
  Cuando se lo cierra otra vez
  Entonces la fila de CierrePeriodo es la misma
  Y el historial es [CIERRE, REAPERTURA, CIERRE]

Escenario: cierre en lote atómico
  Dado 2026-01 y 2026-02 abiertos
  Cuando se cierran juntos
  Entonces ambos quedan cerrados y auditados

  Dado 2026-01 cerrado y 2026-02 abierto
  Cuando se intenta cerrar [2026-01, 2026-02]
  Entonces falla con PeriodoYaCerrado
  Y 2026-02 sigue abierto
```

### Contrato HTTP

| Método | Ruta | Campos | Éxito | Error |
|---|---|---|---|---|
| POST | `/tesoreria/reapertura` | `periodo`, `motivo` | 303 con aviso | 400 re-render |
| POST | `/tesoreria/cierres-lote` | `periodos` | 303 con aviso | 400/aviso según caso |

### Datos

| Cambio | Migración |
|---|---|
| `cierre_periodo.reabierto_en` | `d3e4f5a6b7c8` |
| `auditoria_periodo` (id, periodo, accion, motivo, usuario_id, timestamps, checks) | `d3e4f5a6b7c8` |

Índice lógico: un `CierrePeriodo` por `periodo` (constraint único existente);
la auditoría no se modifica ni se borra.

### Verificación

`tests/test_reapertura.py` (22). RN-50, reglas duras 33, 34 y 43.

## 7. Requisitos no funcionales

| ID | Requisito |
|---|---|
| RNF-1 | Suite completa verde (401 tests) antes de cada commit. |
| RNF-2 | `alembic check` sin diferencias respecto de los modelos. |
| RNF-3 | Ninguna respuesta con `500` ante errores de validación esperados. |
| RNF-4 | Sin claves ni tokens en logs, HTML o query strings. |
| RNF-5 | Las migraciones son reversibles (`downgrade` implementado). |
| RNF-6 | Compatibilidad SQLite (dev/tests) y PostgreSQL (prod). |

## 8. Matriz de trazabilidad

| Entrega | Tests | Migración | Docs |
|---|---|---|---|
| F1 Clave inicial | `test_password.py` (15) | `c1d2e3f4a5b6` | RN-47, regla 40 |
| F2 Rate limiting | `test_login_limiter.py` (9) | — | RN-48, regla 41 |
| F3 Auditoría | `test_auditoria.py` (7) | `d2e3f4a5b6c7` | RN-49, regla 42 |
| F4 Docker | `test_deploy.py` (4) | — | `docs/despliegue.md` |
| F5 Reapertura/lote | `test_reapertura.py` (22) | `d3e4f5a6b7c8` | RN-50, regla 43 |

## 9. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación actual |
|---|---|---|
| Limitador en memoria | No protege con varias instancias | Una instancia; deuda priorizada |
| Secreto efímero sin `CABM_SECRET_KEY` | Sesiones inválidas al reiniciar | Variable obligatoria en compose |
| Reapertura mal usada | Alteración operativa del mes | Motivo obligatorio + auditoría append-only |
| Datos históricos sin usuario | Trazabilidad incompleta | `usuario_id` nullable + columna "—" |
| SQLite difiere de PostgreSQL | Sorpresas en prod | Enums portables, `batch_alter_table`, FK explícitas |

## 10. Criterio de aceptación

1. Los 401 tests pasan con `& C:\Python314\python.exe -m pytest -q`.
2. `alembic upgrade head` y `alembic check` limpios.
3. `docker compose config` válido y `/login` responde con la base migrada.
4. Cada entrega tiene su regla en `docs/dominio.md`, su entrada en
   `CHANGES.md` y su fila en la matriz de trazabilidad.
