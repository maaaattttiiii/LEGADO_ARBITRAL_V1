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
│ Navegador (formularios HTML + Tailwind/HTMX/Alpine, sin Bootstrap    │
│ ni SPA ni API pública)                                               │
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
| `app/main.py` | Crea `FastAPI`, monta `/static`, registra middleware, routers y handlers de error |
| `app/database.py` | `engine`, `SessionLocal`, `Base`, `get_db()` y `PRAGMA foreign_keys` |
| `app/seguridad.py` | scrypt, constantes de sesión, guardas y `usuario_actual()` |
| `app/limiter.py` | `LimitadorLogin` en memoria (ventana y bloqueo por `(IP, email)`) |
| `app/templating.py` | `Jinja2Templates` con rutas absolutas y filtros de formato |
| `app/static/` | CSS y JS propios (`css/app.css`, `js/app.js`) servidos por `StaticFiles` en `/static` |
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
- Con `HX-Request: true`, `app/presentacion.py` decide entre fragmento,
  `HX-Redirect` y `HX-Trigger`; sin la cabecera el contrato histórico no cambia.

### Contrato HTMX (Fase 3)

`app/presentacion.py` concentra el despacho de representación, sin lógica de
negocio:

- `es_htmx(request)`: compara `HX-Request` con `"true"` sin distinguir
  mayúsculas.
- `respuesta_o_fragmento(...)`: sin la cabecera renderiza la página completa;
  con la cabecera renderiza el parcial y agrega `HX-Trigger` / `HX-Redirect`.
- `redireccion_htmx(destino)`: `204` sin cuerpo con `HX-Redirect`.
- `toast(tipo, mensaje, duracion=None)`: JSON ASCII para `HX-Trigger`.

Toda respuesta que depende de la cabecera declara `Vary: HX-Request`.

| Situación | Sin `HX-Request` | Con `HX-Request: true` |
|---|---|---|
| Login exitoso | `303` al inicio del rol o al `next` interno | `204` + `HX-Redirect` |
| Login inválido | `401` con `login.html` completo | `401` fragmento + `HX-Trigger` de error |
| Rate limit | `429` + `Retry-After` con página completa | `429` + `Retry-After` + fragmento + `HX-Trigger` |
| Cambio de clave requerido | `303 /cambiar-password` | `204` + `HX-Redirect /cambiar-password` |
| Sin sesión (`NoAutenticado`) | `303 /login?next=<ruta>` | `204` + `HX-Redirect /login?next=<ruta>` |
| Rol incorrecto (`AccesoDenegado`) | `403` + `403.html` | `403` fragmento + `HX-Trigger` de error |
| Cambio de clave exitoso | `303` al inicio del rol | `204` + `HX-Redirect` |
| Error de cambio de clave | `400` con página completa | `400` fragmento + `HX-Trigger` de error |

Los parciales viven en `app/templates/partials/` y son la única fuente de
markup: las páginas completas los incluyen (`{% include %}`) y la rama HTMX
los renderiza directamente. Los fragmentos no contienen `<!doctype>`, `<html>`,
`<head>` ni `<body>`.

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

Estado final del change `active-stack-frontend` (Fase 6 completada; Bootstrap
retirado):

- **Jinja2** con herencia desde `base.html`; navbar condicionada por rol.
- **Active Stack**: Tailwind CSS 3.4 vía Play CDN con versión fijada
  (`cdn.tailwindcss.com/3.4.17`) y **preflight habilitado** (reset de Tailwind,
  sin clases Bootstrap de respaldo); HTMX 2.0.4 y Alpine.js 3.14.8 con `defer`.
  Desde la Fase 3, login y cambio de clave usan el contrato de fragmentos
  descripto en §3; desde la Fase 4 lo hacen también los formularios CRUD de
  árbitros, partidos, canchas, torneos y tarifas; desde la Fase 5, las acciones
  de tesorería (liquidar, cobrar, ajustar, cerrar, cierre en lote y reabrir).
  Sin `HX-Request` el comportamiento HTTP no cambia (303 en alta exitosa y 400
  con página completa ante error).
- **Activos propios**: `app/static/css/app.css` y `app/static/js/app.js`,
  servidos desde `/static` por `StaticFiles` montado en `app/main.py`. El CSS
  conserva únicamente navegación por rol, modales nativos, toasts, foco visible
  y los alias semánticos `.text-success`/`.text-danger`/`.text-body-secondary`.
- **Navegación responsive** con Alpine (`x-data`, `aria-expanded`,
  `aria-controls`, cierre con `Escape`); el submenú "Datos"
  (Canchas/Torneos/Tarifas) usa el mismo estado. Sin JavaScript, el layout
  conserva los enlaces mediante el fallback `<noscript>`. La marca enlaza a
  `/` para no duplicar el enlace activo de la sección.
- **Sin Bootstrap**: no se cargan CSS, JS ni `bootstrap-icons`; todos los
  templates usan utilidades Tailwind y los componentes propios. Los íconos son
  SVG inline del macro `icono()`.
- **Capa de componentes** (`app/templates/componentes/`), sin lógica de
  negocio y reutilizable por los templates:
  - `iconos.html`: macro `icono(nombre, clase="", titulo=None)` con SVG inline
    (`stroke="currentColor"`). Los decorativos llevan `aria-hidden="true"` y
    los significativos `role="img"` + `<title>`.
  - `modal.html`: macro `modal(id, titulo_id, titulo, abrir=false, ancho="lg")`
    que emite un `<dialog>` nativo con `role="dialog"` y `aria-modal="true"`.
    Se abre con `showModal()`, cierra con `close()`/`Escape` (`@cancel`), enfoca
    el primer campo y devuelve el foco al disparador. `data-abrir-modal="true"`
    reabre el modal de forma declarativa cuando el servidor re-renderiza un
    formulario con error (sin `new bootstrap.Modal`). La página completa de
    canchas y torneos también conserva `form` y `editar_error_id`, por lo que
    el modal reabre con los valores aun sin HTMX.
  - `toasts.html`: macro `toasts()` incluido en `base.html`; contenedor
    `aria-live="polite"`, notificaciones `role="status"`, región asertiva
    `role="alert"` para errores y botón "Cerrar notificación".
- **Stores de Alpine** en `app/static/js/app.js` (`alpine:init`):
  - `modales`: `abrir(id)` publica `cabm:abrir-modal` con `window.dispatchEvent`;
    cada `<dialog>` escucha el evento. `cerrar(id)` publica
    `cabm:cerrar-modal`. No hay puente hacia Bootstrap.
  - `toasts`: cola con máximo 3, duración 5 s (8 s para errores), pausa al
    recibir puntero o foco (`pausar`/`reanudar`), `quitar` y escucha de
    `cabm:toast`.
- **Estado de carga HTMX**: `app.js` escucha `htmx:beforeRequest`,
  `htmx:afterRequest`, `htmx:responseError`, `htmx:sendError`,
  `htmx:abort`, etc.; marca `aria-busy="true"` en el target, lo retira al
  terminar y anuncia “Cargando…” en `#cabm-estado-htmx`
  (`role="status"`, `aria-live="polite"`, `.cabm-solo-lectores`).
- **`app/templates/partials/`** contiene los fragmentos HTMX:
  - `auth/login_panel.html` y `auth/cambiar_password_panel.html`, incluidos por
    `login.html` y `cambiar_password.html`. Los formularios conservan
    `method`/`action` y agregan `hx-post`, `hx-target` y `hx-disabled-elt`
    (mejora progresiva).
  - `errors/403_panel.html`, compartido por `403.html` y por la respuesta HTMX
    de las guardas.
  - Los parciales de listados de la Fase 4 (ver mapa abajo) y los de
    tesorería de la Fase 5 (`cuentas.html`, `partidos_a_liquidar.html`,
    `cobros.html`, `cierres.html`, `modal_ajuste.html` y
    `actualizacion.html`).
- **Mapa de parciales y regiones (Fase 4)**. La página completa incluye el
  parcial con `{% include %}` y la rama HTMX lo renderiza directamente: una
  sola fuente de markup.

  | Recurso | Parcial del listado | Región (objetivo del swap) | Parcial del formulario | Modal |
  |---|---|---|---|---|
  | Árbitros | `partials/arbitros/listado.html` | `#listado-arbitros` | `partials/arbitros/modal.html` | `#modalAlta` |
  | Partidos | `partials/partidos/listado.html` | `#listado-partidos` | `partials/partidos/modal.html` | `#modalPartido` |
  | Canchas | `partials/canchas/listado.html` | `#listado-canchas` | `partials/canchas/modal.html` y `partials/canchas/modal_editar.html` | `#modalCancha` / `#modalEditar<id>` |
  | Torneos | `partials/torneos/listado.html` | `#listado-torneos` | `partials/torneos/modal.html` y `partials/torneos/modal_editar.html` | `#modalTorneo` / `#modalEditar<id>` |
  | Tarifas | `partials/tarifas/listado.html` | `#listado-tarifas` | `partials/tarifas/modal.html` | `#modalTarifa` |
  | Designaciones | `partials/designaciones/listado.html` | `#listado-designaciones` | `partials/designaciones/modal_terna.html` | `#modalTerna<id>` |

  Los formularios de alta y edición conservan `method="post"`/`action` y suman
  `hx-post`, `hx-target="#listado-<recurso>"`, `hx-swap="outerHTML"` y
  `hx-disabled-elt` (evita el doble envío). En éxito la respuesta es `200` con
  el parcial del listado y `HX-Trigger` con `cabm:toast` (éxito) y
  `cabm:cerrar-modal` (id del modal). En error es `400` con el parcial del
  formulario, `HX-Retarget` al modal, `HX-Reswap: outerHTML`,
  `data-abrir-modal="true"` y `cabm:toast` de error. Cada modal muestra el
  mensaje de validación dentro del cuerpo (`role="alert"`), no solo en el
  toast. `app/static/js/app.js` habilita el swap de `400`, `401`, `403`, `404`
  y `429` en `htmx:beforeSwap` y despacha `cabm:abrir-modal`/`cabm:cerrar-modal`, que
  todos los `<dialog>` escuchan. La terna guarda el auto ya asignado y lo
  refleja al reabrir el modal; si `GET /login` llega con sesión vigente y
  `HX-Request`, responde `204` + `HX-Redirect` en lugar de un `303` que HTMX
  no puede seguir. Un `404` de un recurso alcanzable por HTMX (liquidar un
  partido, editar o dar de baja una cancha/torneo) conserva el `404` y devuelve
  el parcial de la región con `cabm:toast` de error; sin `HX-Request` mantiene
  el JSON `{"detail": ...}` original.
- **Tesorería y liquidaciones (Fase 5)**. Los cuatro bloques del panel son
  parciales incluidos por `tesoreria/index.html` y renderizados directamente
  por la rama HTMX, con una sola fuente de markup:

  | Región (id estable) | Parcial | Swap normal | Swaps fuera de banda |
  |---|---|---|---|
  | `#cuentas-corrientes` | `partials/tesoreria/cuentas.html` | Ajuste manual | Liquidar, cobrar, cierre y reapertura |
  | `#partidos-a-liquidar` | `partials/tesoreria/partidos_a_liquidar.html` | Liquidar | Cierre y reapertura |
  | `#cobros-diferidos` | `partials/tesoreria/cobros.html` | Registrar cobro | Cierre y reapertura |
  | `#cierres-periodo` | `partials/tesoreria/cierres.html` | Cierre individual, cierre en lote y reapertura | — |

  El fragmento `partials/tesoreria/actualizacion.html` recibe `principal`
  (la región del swap normal) y `regiones`; el resto se emite con
  `hx-swap-oob="true"`. El modal de ajuste vive en
  `partials/tesoreria/modal_ajuste.html` (`#modalAjuste`).
  - **Liquidar**: el botón abre `#modalLiquidar` (modal nativo Alpine) y el
    botón de confirmación dispara `requestSubmit()` sobre el formulario
    clásico. Éxito: `200` con `#partidos-a-liquidar` como principal y
    `#cuentas-corrientes` fuera de banda, más `cabm:toast` de éxito. Error de
    dominio o período cerrado: `400` con el mismo fragmento, `HX-Retarget` y
    `cabm:toast` de error. La idempotencia sigue garantizada por el servicio
    (`UNIQUE(designacion_id, concepto)`).
  - **Cobrar**: `#cobros-diferidos` principal y `#cuentas-corrientes` fuera de
    banda (por el posible reintegro de retención). Error: `400` + toast.
  - **Ajustar**: éxito `200` con `#cuentas-corrientes` y
    `cabm:cerrar-modal` para `#modalAjuste`. Error: `400` con
    `#modalAjuste`, `data-abrir-modal="true"`, `HX-Retarget` y toast.
  - **Cerrar / cerrar en lote / reabrir**: éxito `200` con
    `#cierres-periodo` principal y `#cuentas-corrientes`,
    `#partidos-a-liquidar` y `#cobros-diferidos` fuera de banda. Un cierre
    repetido conserva `200` y emite un toast informativo; los errores de
    validación conservan `400`. Las confirmaciones usan `#modalCierre`,
    `#modalCierreLote` y `#modalReapertura`.
  - Todos los formularios de acción conservan `method`/`action` (funcionan sin
    JavaScript) y agregan `hx-post`, `hx-target`, `hx-swap="outerHTML"` y
    `hx-disabled-elt` para evitar el doble envío. La exportación CSV/PDF sigue
    siendo un enlace de descarga de página completa, sin atributos `hx-*`.
- **Despacho HTMX**: `app/presentacion.py` (`es_htmx`,
  `respuesta_o_fragmento`, `redireccion_htmx`, `toast`). Las rutas de login y
  cambio de clave y los handlers de `NoAutenticado`, `CambioPasswordRequerido`
  y `AccesoDenegado` en `app/main.py` eligen página completa, fragmento o
  `HX-Redirect` según `HX-Request`. La lógica de autenticación, sesión y guardas
  no cambia.
- **`.nav-link` y `.nav-link.active`** se definen en `app.css`, nunca con
  utilidades Tailwind en el ancla: el enlace activo emite exactamente
  `class="nav-link active"` (contrato de la suite histórica).
- Filtros globales: `fecha_local` (UTC→ART), `moneda` (formato argentino) y
  `periodo_local` (fecha→`AAAA-MM` contable). Las plantillas **no** formatean
  a mano.
- Formularios HTML clásicos con `POST` y redirect 303. Login, cambio de clave,
  los formularios CRUD de árbitros, partidos, canchas, torneos y tarifas
  (Fase 4) y las acciones de tesorería (Fase 5) aceptan `HX-Request`; todos los
  modales usan `componentes/modal.html` (`<dialog>` nativo). Sin JavaScript de
  negocio: la verdad está en el servidor.
- Mensajes de resultado vía query string (`?ok=`, `?error=`) y re-render 400.

**Deuda de producción (Tailwind Play CDN)**: compila en el navegador, agrega
peso, provoca FOUC, no hace purge/SRI estable y requiere red. Mitigaciones
actuales: versión fijada, CSS crítico propio y scripts diferidos. El build
local (Tailwind standalone CLI o PostCSS) y la CSP quedan para un change
posterior.

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
