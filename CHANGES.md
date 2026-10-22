# CHANGES — Legado Arbitral (CABM)

> Índice operativo de entregas del sistema de gestión del Colegio de Árbitros
> de Bahía Blanca. Resume **qué ya está implementado**, con qué tests se
> verifica y qué queda pendiente.
>
> Última actualización: **2026-10-21** · Versión de producto: **V3.0**
> Suite: **665 tests verdes** · Migración Alembic head: `d3e4f5a6b7c8`

## 1. Estado actual

| Dimensión | Estado |
|---|---|
| Dominio financiero (padrón, partidos, designaciones, aranceles, viáticos) | ✅ V1.0 |
| Tesorería (liquidación, cuenta corriente, ajustes, cobros, exportación) | ✅ V1.0 |
| Períodos contables (cierre, reapertura auditada, cierre en lote) | ✅ V1.0 / V2.0 |
| Autenticación, roles y portal del árbitro | ✅ V2.0 |
| Seguridad (clave inicial obligatoria, rate limiting) | ✅ V2.0 |
| Auditoría de operaciones sensibles | ✅ V2.0 |
| Despliegue Docker + PostgreSQL | ✅ V2.0 |
| Tests automatizados | ✅ 665 |
| Interfaz web (Tailwind + HTMX + Alpine, accesible, sin Bootstrap) | ✅ V3.0 |
| Documentación viva (dominio, arquitectura, specs, openspec, despliegue) | ✅ |

### 1.1 Estructura documental

| Documento | Contenido | Se actualiza cuando |
|---|---|---|
| `docs/dominio.md` | RN-01..RN-50, entidades, flujos y estados (fuente canónica del dominio) | cambia una regla de negocio |
| `openspec/specs/<capacidad>/spec.md` | Specs vivas por capacidad, con `Ref:` a cada RN y a F1..F5 (12 capacidades) | cambia una RN o un contrato; validar con `openspec validate --specs` |
| `docs/specs/<version>.md` | Contrato y criterios de aceptación de una entrega | se planifica una entrega |
| `docs/arquitectura.md` | Capas, ciclo de request, modelo de datos, migraciones y deploy | cambia una capa, el esquema o un contrato HTTP |
| `docs/despliegue.md` | Docker, PostgreSQL, variables de entorno y backups | cambia el despliegue |
| `AGENTS.md` | Stack, reglas duras (1-44) y governance (§7) | cambia una regla del proyecto |
| `CHANGES.md` | Historial de entregas, suite de tests y deuda técnica | se cierra un cambio |

Precedencia: si `openspec/specs/` y `docs/dominio.md` se contradicen, gana
`docs/dominio.md` y la spec se corrige. Las specs de `openspec/` son el reflejo
ejecutable del dominio, no una segunda fuente de verdad.

## 2. Historial de entregas

### V1.0 — Dominio financiero y tesorería

Base funcional del sistema: carga de datos y circuito completo del dinero,
sin autenticación (acceso directo al panel).

| Capacidad | Implementación | Detalle |
|---|---|---|
| Padrón de árbitros | `services/arbitros.py`, `/arbitros` | Escalafón, localidad, `tiene_auto`, baja lógica |
| Canchas y torneos | `services/canchas.py`, `services/torneos.py` | ABM con baja lógica (RN-36) |
| Partidos | `services/partidos.py`, `/partidos` | Fecha/hora ART→UTC, categoría, modalidad de pago |
| Designaciones / ternas | `services/designaciones.py` | Terna completa, roles, conflicto de 2 h, U11 y CUARTO |
| Aranceles | `services/tarifas.py`, `/tarifas` | Vigencias inmutables por (categoría, rol, escalafón) |
| Viáticos | `services/viaticos.py` | Litros fijos × precio del combustible del día del partido |
| Liquidación | `services/liquidacion.py` | Honorario congelado, retención 10%, viático, idempotencia |
| Cuenta corriente | `services/tesoreria.py`, `/tesoreria` | Saldo calculado, ajustes manuales, cobro diferido y mora |
| Exportación mensual | `services/exportacion.py` | CSV (`;`, BOM) y PDF A4 apaisado |
| Cierres de período | `services/cierres.py` | Bloqueo de altas/liquidaciones/cobros/ajustes |
| Datos oficiales y seed | `app/seeds/` | Planilla oficial + usuarios demo, idempotente |

Reglas de negocio: **RN-01 a RN-41** en [`docs/dominio.md`](docs/dominio.md).

### V2.0 — Seguridad, auditoría y operación

| # | Entrega | Commit | Migración | Tests |
|---|---|---|---|---|
| 0 | Autenticación, roles y portal del árbitro | `d3b0872` | `aab622ffc2bc` | `test_auth.py` (27) |
| 1 | Cambio de clave inicial obligatorio | `ea0fc72` | `c1d2e3f4a5b6` | `test_password.py` (15) |
| 2 | Rate limiting de `/login` | `2e15dba` | — | `test_login_limiter.py` (9) |
| 3 | Auditoría de operaciones sensibles | `a8bef7f` | `d2e3f4a5b6c7` | `test_auditoria.py` (7) |
| 4 | Dockerfile + docker-compose (PostgreSQL) | `fdd2e77` | — | `test_deploy.py` (4) |
| 5 | Reapertura de período y cierres en lote | `eacc2eb` | `d3e4f5a6b7c8` | `test_reapertura.py` (22) |

Especificación detallada de estas cinco tareas:
[`docs/specs/v2_seguridad_auditoria.md`](docs/specs/v2_seguridad_auditoria.md).
Reglas de negocio nuevas: **RN-42 a RN-50**.

### V3.0 — Interfaz web: Active Stack y accesibilidad

Change `active-stack-frontend`. Retira Bootstrap 5, migra toda la capa de
presentación a Tailwind CSS y componentes propios, incorpora HTMX/Alpine con
mejora progresiva y formaliza los criterios de accesibilidad. **No cambia
reglas de negocio ni el esquema.**

| # | Entrega | Tests |
|---|---|---|
| 1 | Layout base, activos en `/static`, navegación por rol | `test_interfaz_web.py` (12) |
| 2 | Componentes de íconos, modales nativos y toasts | `test_ui_componentes.py` (18) |
| 3 | Contrato de fragmentos, login y guardas HX-aware | `test_presentacion.py` (17), `test_htmx_auth.py` (16) |
| 4 | CRUD con HTMX por regiones | `test_htmx_crud.py` (40) |
| 5 | Tesorería con swaps OOB | `test_htmx_tesoreria.py` (28) |
| 6 | Retiro de Bootstrap, preflight, accesibilidad y documentación | `test_accesibilidad_ui.py` (11) |
| 7 | Auditoría HTMX: designaciones, ediciones, errores visibles, swap de 4xx y 404 | `test_htmx_auditoria.py` (122) |

La Fase 7 cierra la auditoría integral: incorpora designaciones al contrato
HTMX, reabre el modal del registro correcto en canchas y torneos (también sin
HTMX, conservando los valores), muestra el mensaje de validación dentro de
todos los formularios, habilita el swap de 400/401/403/404/429 en el navegador
y devuelve el listado de la región ante un 404 alcanzable por HTMX, sin alterar
el JSON original cuando no hay `HX-Request`.

Especificación de la entrega:
[`docs/specs/v3_interfaz_web.md`](docs/specs/v3_interfaz_web.md).
Contrato de accesibilidad: **RNF-UI-1 a RNF-UI-8**.

- **RNF-UI-1**: layout único, activos propios en `/static`, sin Bootstrap.
- **RNF-UI-2**: navegación por rol y enlace activo con
  `class="nav-link active"` exacto.
- **RNF-UI-3**: operación completa sin JavaScript.
- **RNF-UI-4**: HTMX actualiza solo la región afectada.
- **RNF-UI-5**: fragmentos mínimos, `Vary: HX-Request`, `HX-Trigger` y
  `HX-Redirect`.
- **RNF-UI-6**: modales accesibles con foco contenido y movimiento reducido.
- **RNF-UI-7**: toasts con rol, duración, apilado y pausa.
- **RNF-UI-8**: teclado, foco visible, `aria-busy`, íconos y estados no
  dependientes del color.

## 3. Suite de tests vigente (665)

| Área | Archivo(s) | Tests |
|---|---|---|
| Cálculos y modelos | `test_liquidacion.py` (43), `test_tarifas.py` (26), `test_viaticos.py` (22), `test_models.py` (16), `test_cobros.py` (14) | **121** |
| Rutas y UI | `test_designaciones_routes.py` (34), `test_tesoreria_routes.py` (20), `test_partidos_routes.py` (17), `test_arbitros_routes.py` (16), `test_canchas_routes.py` (10), `test_torneos_routes.py` (9), `test_tarifas_routes.py` (6) | **112** |
| Períodos | `test_cierres.py` (23), `test_reapertura.py` (22) | **45** |
| Seguridad y auditoría | `test_auth.py` (27), `test_password.py` (15), `test_login_limiter.py` (9), `test_auditoria.py` (7) | **58** |
| Exportación | `test_exportacion.py` | **14** |
| Datos iniciales | `test_seed.py` | **47** |
| Despliegue | `test_deploy.py` | **4** |
| Interfaz web y accesibilidad | `test_interfaz_web.py` (12), `test_ui_componentes.py` (18), `test_presentacion.py` (17), `test_htmx_auth.py` (16), `test_htmx_crud.py` (40), `test_htmx_tesoreria.py` (28), `test_htmx_auditoria.py` (122), `test_accesibilidad_ui.py` (11) | **264** |
| **Total** | 29 archivos | **665** |

Comando: `& C:\Python314\python.exe -m pytest -q`
(los tests corren contra SQLite en memoria con `Base.metadata.create_all()`;
Alembic es la única vía para cambiar el esquema real).

## 4. Invariantes que ningún cambio puede romper

1. Dinero en `Numeric(12,2)`/`Decimal`; `monto` positivo y signo por `tipo`.
2. El saldo **se calcula**, nunca se persiste.
3. Honorario y viático **congelados** al liquidar (snapshot financiero).
4. Idempotencia por `UNIQUE(designacion_id, concepto)`.
5. Arancel resuelto con la **fecha del partido**, período contable en **ART**.
6. Servicios sin `commit()`/`rollback()`; la transacción es de la ruta.
7. Las FK usan `ondelete` explícito y `PRAGMA foreign_keys=ON` en SQLite.
8. Cierre de período solo se revierte por **reapertura auditada** con motivo.
9. Contraseñas siempre con `hash_password()`; nunca en claro ni en logs.
10. Sin sesión → `303 /login`; rol incorrecto → `403`; validación → `400` con mensaje.

## 5. Deuda técnica y próximos pasos

| Prioridad | Tema | Nota |
|---|---|---|
| Alta | Cierre programado de fin de mes | Hoy es manual (individual o en lote) |
| Alta | Rate limiting distribuido | El estado vive en memoria de una instancia; mover a Redis/DB |
| Media | Backups automatizados de PostgreSQL | Procedimiento manual documentado en `docs/despliegue.md` |
| Media | Build local de Tailwind | Hoy usa Play CDN: peso, FOUC, purge y SRI dependen de la red; migrar a standalone CLI/PostCSS junto con CSP |
| Media | Observabilidad | Logs estructurados y métricas de login/errores |
| Baja | Migración a tipos nativos de PostgreSQL | Hoy los enums son `VARCHAR` + `CHECK` portables |
| Baja | Tests E2E de navegador | La suite actual cubre servicios y rutas vía `httpx` |

## 6. Cómo encarar un cambio nuevo

1. Leer [`docs/dominio.md`](docs/dominio.md) (regla de negocio afectada), su
   spec viva en `openspec/specs/<capacidad>/` y
   [`docs/arquitectura.md`](docs/arquitectura.md) (capa donde va el cambio).
2. Si el cambio toca contratos o dinero, escribir/actualizar la spec en
   `docs/specs/` antes del código.
3. TDD estricto: test que falla → código mínimo → triangulación → refactor.
4. Si hay cambio de esquema: migración Alembic nueva, `alembic upgrade head`
   y `alembic check` limpio.
5. Actualizar esta tabla, la RN en `docs/dominio.md`, su reflejo en
   `openspec/specs/<capacidad>/spec.md` y la spec de la entrega en `docs/specs/`.
6. Respetar el nivel de governance de `AGENTS.md` §7 (CRÍTICO/ALTO/MEDIO/BAJO).

