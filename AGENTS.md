# AGENTS.md — Sistema de Gestión Colegio de Árbitros (CABM)

> Reglas **específicas de este proyecto**. No repite las instrucciones globales del stack.

## 1. Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.14 |
| Web | FastAPI + Jinja2 (server-side rendering) + `python-multipart` |
| ORM | SQLAlchemy 2.1 — estilo declarativo tipado (`Mapped` / `mapped_column`) |
| Migraciones | Alembic |
| Config | `pydantic-settings` (`.env`) |
| DB dev | SQLite (`sqlite:///./cabm.db`) |
| DB prod | PostgreSQL (`psycopg[binary]`) |
| Tests | pytest + httpx |

## 2. Estructura

```
LegadoArbitral/            # raíz del repositorio
├── app/
│   ├── main.py              # instancia FastAPI + SessionMiddleware + handlers 303/403
│   ├── templating.py        # Jinja2Templates (rutas absolutas)
│   ├── seguridad.py         # scrypt, sesión, requiere_tesorero / requiere_arbitro
│   ├── database.py          # engine, SessionLocal, Base, get_db
│   ├── models/
│   │   ├── base.py          # Base + TimestampMixin
│   │   ├── enums.py         # enums del dominio
│   │   ├── arbitro.py       # Arbitro
│   │   ├── usuario.py       # Usuario (email, password_hash, rol, arbitro_id, activo)
│   │   ├── cancha.py        # Cancha
│   │   ├── torneo.py        # CategoriaTorneo, Torneo
│   │   ├── partido.py       # Partido
│   │   ├── designacion.py   # Designacion
│   │   ├── tarifa.py        # Tarifa (aranceles con vigencia)
│   │   ├── precio_combustible.py  # PrecioCombustible (Nafta Infinia, vigencias)
│   │   ├── movimiento.py    # MovimientoCuentaCorriente + calcular_saldo()
│   │   └── cierre_periodo.py  # CierrePeriodo (bloqueo de meses cerrados)
│   ├── services/            # lógica de negocio (tarifas, viáticos, liquidación)
│   │   ├── arbitros.py      # crear_arbitro() + validaciones del padrón
│   │   ├── partidos.py      # crear_partido(), filtrar_partidos()
│   │   ├── designaciones.py # asignar_terna(), admite_cuarto()
│   │   ├── tarifas.py       # crear_tarifa(), resolver_tarifa()
│   │   ├── viaticos.py      # crear_precio_combustible(), resolver_precio_combustible(), calcular_viatico()
│   │   ├── liquidacion.py   # liquidar_partido(), registrar_cobro(), ResultadoLiquidacion
│   │   ├── tesoreria.py     # saldos(), saldo_de(), movimientos_de_arbitro(), crear_ajuste()
│   │   ├── canchas.py       # ABM de canchas (baja lógica)
│   │   ├── torneos.py       # ABM de torneos (baja lógica)
│   │   ├── cierres.py       # cerrar_periodo(), validar_abierto(), periodos_cerrados()
│   │   ├── validaciones.py  # helpers de parseo de formularios
│   │   ├── usuarios.py      # crear_usuario(), autenticar()
│   │   └── exportacion.py   # liquidacion_mensual(), liquidacion_csv(), liquidacion_pdf()
│   ├── formato.py           # formatear_moneda() (formato argentino)
│   ├── periodos.py          # normalizar_periodo(), periodo_de() (ART)
│   ├── tiempo.py            # ART (UTC-3) <-> UTC
│   ├── routes/
│   │   ├── arbitros.py      # GET/POST /arbitros
│   │   ├── partidos.py      # GET/POST /partidos
│   │   ├── designaciones.py # GET/POST /designaciones
│   │   ├── canchas.py       # ABM /canchas
│   │   ├── torneos.py       # ABM /torneos
│   │   ├── tarifas.py       # alta de aranceles /tarifas
│   │   ├── tesoreria.py     # panel, detalle, liquidar, ajuste, cobro, exportar, cierre
│   │   ├── auth.py          # GET/POST /login, POST /logout
│   │   └── portal.py        # /mis-partidos y /mi-cuenta (rol ARBITRO)
│   ├── templates/
│   │   ├── base.html        # layout + navbar según rol
│   │   ├── login.html       # formulario de ingreso
│   │   ├── 403.html         # acceso denegado
│   │   ├── portal/
│   │   │   ├── mis_partidos.html  # designaciones del árbitro
│   │   │   └── mi_cuenta.html     # movimientos y saldo del árbitro
│   │   ├── arbitros/
│   │   │   └── index.html   # listado + modal de alta
│   │   ├── partidos/
│   │   │   └── index.html   # listado con filtros + modal de alta
│   │   ├── designaciones/
│   │   │   └── index.html   # partidos pendientes + terna + modal por partido
│   │   └── tesoreria/
│   │       ├── index.html   # saldos + partidos a liquidar + modal de ajuste
│   │       └── arbitro.html # detalle de movimientos de una cuenta
│   └── seeds/
│       ├── datos_iniciales.py  # planilla oficial (litros, precio, categorías)
│       └── usuarios.py         # tesorero + cuentas de árbitros
├── docs/dominio.md          # fuente de verdad del dominio
├── tests/
│   ├── conftest.py          # client autenticado como tesorero + client_anonimo
│   ├── test_auth.py         # login, guardas y aislamiento por usuario
│   └── ...
├── alembic.ini
├── alembic/
│   └── versions/            # migraciones (única vía para cambiar el esquema)
├── pytest.ini
└── requirements.txt
```

## 3. Convenciones de nombres

- **Dominio de negocio en español**: tablas, columnas y modelos (`Arbitro`, `Partido`, `Designacion`, `MovimientoCuentaCorriente`, `Torneo`, `Cancha`, `CategoriaTorneo`).
- **Infraestructura en inglés** (clases base, mixins, helpers del framework).
- Tablas en **singular** y `snake_case`; claves foráneas `<entidad>_id`.
- Enums en `UPPER_SNAKE_CASE` como valor persistido.

## 4. Reglas duras (no negociables)

1. **Dinero = `Numeric(12,2)` + `Decimal`. Nunca `float`.**
2. `monto` es **siempre positivo**; el signo lo determina `tipo` (`CREDITO` / `DEBITO`). Constraint `monto > 0`.
3. **El saldo NO se persiste.** Se calcula con `calcular_saldo()`: `SUM(CREDITO) - SUM(DEBITO)`.
4. **Snapshot financiero**: `Designacion.honorario` se congela al designar/liquidar. Un cambio futuro en la tabla de aranceles **jamás** altera movimientos pasados.
5. **Idempotencia**: `movimiento_cuenta_corriente` tiene `UNIQUE(designacion_id, concepto)`. Liquidar dos veces el mismo partido no duplica honorarios ni viáticos.
6. **Enums portables**: `columna_enum()` genera `VARCHAR` + un `CHECK` **explícito** declarado en `__table_args__` con `check_enum()`. Nunca `native_enum=True` ni `create_constraint=True` (Alembic duplica el CHECK al copiar la tabla en `CreateTableOp`).
7. **Integridad referencial**: toda FK con `ondelete` explícito. En SQLite el `PRAGMA foreign_keys=ON` se activa por event listener en `database.py` (sin él, las FK se ignoran).
8. **Fechas de negocio `tz-aware` en UTC.** `DateTime(timezone=True)`.
9. **Migraciones con Alembic.** `Base.metadata.create_all()` solo está permitido en tests.
10. **TDD estricto**: test que falla (RED) → código mínimo (GREEN) → triangulación → refactor.
11. `Base.metadata` usa **naming convention** explícita (requisito de Alembic para poder revertir constraints).
12. **Devengado**: el honorario se resuelve con `partido.fecha_hora.date()`, nunca con la fecha de liquidación (RN-11).
13. **Transacciones**: los servicios (`app/services/`) **no** hacen `commit()` ni `rollback()`; solo `flush()`. La transacción pertenece al llamador.
14. **Viático** = `cancha.litros_viatico × precio_litro` con la fecha del partido. Los litros son fijos por localidad según la planilla oficial; **no** se derivan de km ni de un rendimiento. Sin auto, litros 0 o monto 0.00 → **no** se crea movimiento.
15. **Un solo auto por partido**: como máximo una designación elegible con `usa_auto=True`; si hay más → `ViaticoInvalido` antes de cualquier escritura.
16. **Datos oficiales centralizados** en `app/seeds/datos_iniciales.py`. No hardcodear precios, litros ni aranceles en tests o rutas: importar las constantes o sembrar la DB.
17. **Arancel = `(categoría de torneo, escalafón del árbitro)`**. `rol=NULL` en `Tarifa` significa "cualquier rol de campo"; `categoria_arbitro=NULL` significa "cualquier escalafón". `UNICA` es el comodín de Inferiores/Master. `CUARTO` cobra un arancel fijo por rol y **nunca** hereda el de campo.
18. **U11 depende de la cantidad de árbitros** (RN-21): 1 designación elegible → tarifa `U11` ($19.600); 2 designaciones → tarifa `U11_DOBLE` ($31.900) **dividida en partes iguales** ($15.950 c/u); más de 2 → `CantidadDesignacionesInvalida` sin escribir nada. **`asignar_terna()` ya rechaza la tercera** (`CATEGORIA_U11`, `MAX_ARBITROS_U11`) y el panel de designaciones muestra solo dos slots para U11.
19. **Capa de presentación**: las rutas solo orquestan (parsear formulario → servicio → `commit`/`rollback` → render o redirect 303). La lógica vive en `app/services/`. Errores de validación → re-render con `400` y mensaje, nunca un 500 ni un `422` crudo.
20. **`tiene_auto` es del perfil, `usa_auto` es de la designación.** `arbitro.tiene_auto` indica que el árbitro dispone de vehículo (para armar ternas); `designacion.usa_auto` indica que en ese partido usó el auto (y cobra viático). No son intercambiables ni derivados uno del otro.
21. **Zona horaria**: los formularios capturan fecha/hora en **ART (UTC-3, offset fijo)** y se persisten en **UTC**. Toda conversión pasa por `app/tiempo.py` (`combinar`, `a_local`, `formatear`, `inicio_del_dia`); las plantillas usan el filtro `fecha_local`. Nunca comparar fechas de negocio sin normalizar.
22. **Terna**: `asignar_terna()` reemplaza la terna completa. Los roles vacíos se eliminan; una designación **con movimientos** no se puede reemplazar, quitar ni cambiar su `usa_auto` (`DesignacionLiquidada`). **Conflicto horario**: menos de 2 horas de diferencia (`MARGEN_CONFLICTO`), **en la misma cancha o en otra** (un partido ocupa ~1h30 al árbitro aunque no haya traslado); exactamente 2 horas se permite. Se excluyen las `RECHAZADA`. `CUARTO` exige arancel CUARTO vigente para la categoría. Un solo `auto_rol` por partido.
23. **Estados al designar**: el partido pasa de `PROGRAMADO`/`REPROGRAMADO` a `DESIGNADO`; las designaciones creadas desde el panel nacen en `CONFIRMADA` (no `PROPUESTA`).
24. **Tesorería**: el saldo se **calcula** siempre (`saldos()`/`saldo_de()`), nunca se persiste. El filtro `periodo` (`AAAA-MM`) acota la suma a ese mes; un período inválido se informa y se listan todos los saldos. Positivo = a favor del árbitro; negativo = debe a la asociación.
25. **Ajustes manuales**: solo `DESCUENTO`, `ADELANTO`, `PAGO`, `MULTA`, `AJUSTE` (`crear_ajuste()`). `HONORARIO`/`VIATICO`/`RETENCION` se generan únicamente liquidando un partido. El movimiento manual no lleva `designacion_id`.
26. **Retención (RN-30/31)**: 10% sobre el **honorario seco**, nunca sobre el viático. **Contabilidad uniforme**: en `EN_CANCHA` y en `DIFERIDO` se acredita el `HONORARIO` **100%** y se debita `RETENCION` **10%**; el recibo muestra el desglose. Se calcula por designación con `ROUND_HALF_UP`, respeta el honorario congelado y no se aplica retroactivamente.
27. **Modalidad de pago**: es del **partido** (`modalidad_pago`: `EN_CANCHA` por defecto / `DIFERIDO`), no del torneo. `Designacion.honorario` y el movimiento `HONORARIO` guardan siempre el **bruto**.
28. **Mora del diferido (RN-32)**: se detecta al registrar `partido.fecha_cobro` (`registrar_cobro()`). Si `fecha_cobro - fecha_partido > PLAZO_COBRO` (90 días): sin liquidar → se omite la retención; ya liquidado → `CREDITO`/`AJUSTE` por lo retenido, idempotente por `UNIQUE(designacion_id, AJUSTE)`.
29. **ABM de aranceles (RN-35)**: solo se cargan nuevas vigencias; no hay edición ni borrado. El historial de tarifas es inmutable.
30. **ABM de canchas y torneos (RN-36)**: baja **lógica** (`activo=False`), nunca borrado físico.
31. **Exportación mensual (RN-37)**: `GET /tesoreria/exportar?periodo=AAAA-MM&formato=csv|pdf`. Una fila por designación (`HONORARIO`, `RETENCION`, `VIATICO` del período; los ajustes no entran), orden por apellido sin tildes, fila `TOTAL`, `neto = honorario - retención + viático`. CSV: BOM + `;` + decimales con coma. PDF: reportlab, A4 apaisado con membrete. Compartir `formatear_moneda()` de `app/formato.py`; no reimplementar el formato.
32. **Período contable = fecha local (ART, RN-39)**: usar `partido.periodo` (`periodo_de()` en `app/periodos.py`), nunca `fecha_hora.date()` (UTC). Un partido del 31/10 23:00 ART es de octubre.
33. **Cierre de período (RN-38/41)**: `cerrar_periodo()` es único e idempotente (segundo intento → `PeriodoYaCerrado`, sin duplicar). Con el período cerrado, `validar_abierto()` hace fallar `crear_partido()`, `asignar_terna()`, `liquidar_partido()`, `registrar_cobro()` y `crear_ajuste()` con `PeriodoCerrado`. Consultar y exportar sigue permitido; nada se borra ni se reescribe.
34. **Correcciones retroactivas (RN-40)**: nunca se reabre un período cerrado ni se editan movimientos históricos; la corrección es un `AJUSTE` (o descuento/adelanto/pago/multa) en el período **abierto**.
35. **Contraseñas**: siempre `hash_password()` (scrypt con sal) de `app/seguridad.py`. **Prohibido** guardar o loguear contraseñas en claro. `Usuario.email` se normaliza a minúsculas y es único; un `ARBITRO` **exige** `arbitro_id` (CHECK `arbitro_requerido`) y un `TESORERO` no lo lleva.
36. **Sesión (RN-43)**: `SessionMiddleware` con cookie `cabm_session` firmada por `CABM_SECRET_KEY`, `HttpOnly`, `SameSite=Lax`, 8 h. La sesión guarda solo `usuario_id`, `rol`, `nombre` y `arbitro_id`. En producción definir `CABM_SECRET_KEY` y `CABM_HTTPS_ONLY=1`; sin secreto se genera uno efímero por proceso (sirve para dev, invalida sesiones al reiniciar).
37. **Guardas (RN-44)**: `APIRouter(dependencies=[Depends(requiere_tesorero)])` en arbitros, partidos, designaciones, tesorería, canchas, torneos y tarifas; `Depends(requiere_arbitro)` en el portal. Sin sesión → `NoAutenticado` (303 a `/login?next=`); rol incorrecto → `AccesoDenegado` (403). Nunca resolver permisos a mano en la ruta.
38. **Aislamiento del portal (RN-45)**: `/mis-partidos` y `/mi-cuenta` filtran por `usuario.arbitro_id`; **jamás** aceptar un `arbitro_id` por query/URL. El login revalida el usuario contra la base en cada request (`usuario_actual()`), así que desactivarlo corta la sesión (RN-46).
39. **Credenciales iniciales del seed** (desarrollo): `tesorero@cabm.org.ar` / `cabm2026`; cada árbitro sin usuario recibe `<email o legajo>@cabm.org.ar` / `arbitro123`. Cambiarlas antes de producción.
40. **Cambio de clave inicial (RN-47)**: `debe_cambiar_password=True` en toda cuenta sembrada; las guardas redirigen a `/cambiar-password` hasta que la cambie (`CambioPasswordRequerido` → 303). El cambio exige la clave actual, mínimo 8 caracteres y una clave distinta; jamás se loguea. Al guardar se limpia la marca en la base y en la sesión.
41. **Rate limiting del login (RN-48)**: `app/limiter.py` (`LimitadorLogin`) bloquea el par `(IP, email)` 15 minutos tras 5 fallos en 15 minutos. `POST /login` consulta el bloqueo **antes** de autenticar y responde `429` con `Retry-After`; el login exitoso limpia el contador. Es estado en memoria: una sola instancia (con varias, Redis/base).
42. **Auditoría (RN-49)**: los servicios reciben `usuario_id` y lo guardan en cada movimiento (liquidación, retención, viático, reintegro, ajuste) y en `CierrePeriodo`; las rutas lo toman de `Depends(requiere_tesorero)` (nunca de un campo del formulario). Las FK usan `ON DELETE RESTRICT`; la columna es nullable para datos históricos.

## 5. Máquinas de estado

**Partido**: `PROGRAMADO` → `DESIGNADO` → `JUGADO` / `SUSPENDIDO` / `REPROGRAMADO`

**Designacion**: `PROPUESTA` → `CONFIRMADA` → `CUMPLIDA` / `AUSENTE`; `PROPUESTA`/`CONFIRMADA` → `RECHAZADA`

**Rol**: `PRINCIPAL`, `ASISTENTE_1`, `ASISTENTE_2`, `CUARTO`

**Categoría de árbitro (escalafón)**: `CAT_A`, `CAT_A1`, `CAT_B`, `PROMOCIONAL`, `UNICA`

> Los enums viven en `app/models/enums.py`. No se declaran strings sueltos en el código.

## 6. Comandos

```powershell
& C:\Python314\python.exe -m pytest -q          # suite completa
& C:\Python314\python.exe -m uvicorn app.main:app --reload
& C:\Python314\python.exe -m alembic upgrade head
& C:\Python314\python.exe -m app.seeds.datos_iniciales   # datos oficiales + usuarios (idempotente)
```

Variables de entorno: `DATABASE_URL`, `CABM_SECRET_KEY` (obligatoria en producción) y `CABM_HTTPS_ONLY=1` detrás de HTTPS.

## 7. Governance

| Dominio | Nivel | Regla |
|---|---|---|
| `MovimientoCuentaCorriente`, saldos, liquidaciones | **CRÍTICO** | No escribir lógica sin spec y tests. Revisión humana antes de migrar. |
| `Usuario`, `seguridad.py`, sesiones y guardas | **CRÍTICO** | No cambiar hashing, cookies ni reglas de acceso sin tests y revisión humana. |
| `Designacion`, `Partido`, tarifas | **ALTO** | Proponer y confirmar antes de cambiar contratos. |
| `Arbitro`, `Torneo`, `Cancha` | **MEDIO** | Implementar con checkpoints. |
| Enums, schemas de lectura, templates | **BAJO** | Autonomía si los tests pasan. |

## 8. Pendientes conocidos

- **Reapertura de período**: no está implementada (el cierre es definitivo); si el negocio la necesita, debe pasar por una decisión explícita con auditoría.
- **Cierre en lote**: hoy se cierra un período por vez.
