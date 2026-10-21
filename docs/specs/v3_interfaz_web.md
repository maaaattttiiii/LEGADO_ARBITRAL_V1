# V3.0 — Interfaz web: Active Stack, HTMX y accesibilidad

> Entrega `active-stack-frontend`. Reemplaza Bootstrap 5 por Tailwind CSS,
> incorpora HTMX y Alpine.js con mejora progresiva y cierra la deuda de
> accesibilidad de la capa de presentación. **No modifica reglas de negocio ni
> el esquema de datos.**

## 1. Contexto y alcance

La V2.0 dejó el dominio financiero, la seguridad y la operación completos, pero
la interfaz seguía dependiendo de Bootstrap 5.3.3 (CSS, JS e iconos) para
modales, tablas y utilidades. La convivencia con Tailwind permitió migrar por
fases sin romper el contrato HTTP histórico.

Esta entrega cubre:

- retiro total de Bootstrap y `bootstrap-icons` del layout y de los templates;
- migración de todos los formularios, listados, modales y notificaciones a
  Tailwind + componentes propios;
- actualizaciones parciales con HTMX (fragmentos y swaps fuera de banda);
- modales nativos `<dialog>` y toasts accesibles;
- criterios de accesibilidad verificados por tests;
- operación sin JavaScript (mejora progresiva).

Fuera de alcance: build local de Tailwind (standalone CLI/PostCSS), CSP, SRI,
tests E2E de navegador y cambios de negocio.

## 2. Fases de implementación

| Fase | Entrega | Tests |
|---|---|---|
| 1 | Layout base con Tailwind, HTMX y Alpine; activos en `/static`; navegación por rol | `test_interfaz_web.py` |
| 2 | Componentes `iconos.html`, `modal.html` y `toasts.html`; migración de árbitros y partidos | `test_ui_componentes.py` |
| 3 | Contrato de fragmentos, login y guardas HX-aware | `test_presentacion.py`, `test_htmx_auth.py` |
| 4 | CRUD con HTMX y regiones `#listado-<recurso>` | `test_htmx_crud.py` |
| 5 | Tesorería: liquidar, cobrar, ajustar, cerrar y reabrir con swaps OOB | `test_htmx_tesoreria.py` |
| 6 | Retiro de Bootstrap, preflight de Tailwind, accesibilidad y documentación | `test_accesibilidad_ui.py` |

## 3. Contrato de la entrega

### 3.1 Activos y layout

- `base.html` es el único layout: `lang="es"`, viewport, título por página,
  Tailwind 3.4.17 (Play CDN, versión fijada, preflight habilitado), HTMX 2.0.4,
  Alpine 3.14.8 y `/static/js/app.js`, todos con `defer` cuando corresponde.
- `app/static/css/app.css` y `app/static/js/app.js` se sirven desde `/static`.
- Sin Bootstrap CSS/JS ni iconos de Bootstrap en ningún template.

### 3.2 Navegación

- Solo muestra las secciones del rol (`TESORERO` o `ARBITRO`).
- El enlace activo emite exactamente `class="nav-link active"` y
  `aria-current="page"`; las reglas viven en `app.css`.
- Colapsa con Alpine (`aria-expanded`, `aria-controls`, cierre con `Escape`) y
  conserva los enlaces sin JavaScript mediante `<noscript>`.

### 3.3 Formularios y fragmentos

- Todo formulario conserva `method` y `action`; con HTMX agrega `hx-post`,
  `hx-target`, `hx-swap` y `hx-disabled-elt`.
- Sin `HX-Request`: 303 tras éxito y 400 con página completa ante validación.
- Con `HX-Request: true`: fragmento sin `<html>`/`<head>`/`<body>` o
  `HX-Redirect`; se conservan 400/401/403/429 y `Retry-After`.
- La página completa y el fragmento reutilizan el mismo parcial.
- Los eventos viajan en `HX-Trigger` y las redirecciones en `HX-Redirect`.

### 3.4 Modales y notificaciones

- Modales nativos `<dialog>` con `role="dialog"`, `aria-modal="true"`,
  `aria-labelledby`, `showModal()`, cierre con `Escape`/`close()` y retorno del
  foco al disparador.
- `data-abrir-modal="true"` reabre el modal cuando el servidor devuelve un
  formulario inválido.
- Toasts: máximo 3, 5 s de éxito y 8 s de error, pausa al enfocar o apuntar,
  cierre manual; error con `role="alert"`/`aria-live="assertive"`.

### 3.5 Accesibilidad y carga

- Foco visible en todos los controles (`:focus-visible`, `--cabm-foco`).
- Orden de tabulación natural; sin `tabindex` positivos.
- Durante una petición HTMX, la región afectada expone `aria-busy="true"`; al
  terminar se limpia. El estado se anuncia en `#cabm-estado-htmx`
  (`role="status"`, `aria-live="polite"`).
- Íconos decorativos con `aria-hidden="true"`; significativos con
  `role="img"` + `<title>`/`aria-label`.
- Estados (partido, saldo, toast) siempre con texto además del color.
- `prefers-reduced-motion: reduce` desactiva animaciones y transiciones.

## 4. Requisitos no funcionales

| ID | Requisito | Verificación |
|---|---|---|
| **RNF-UI-1** | Layout único, activos propios en `/static`, sin Bootstrap | `test_interfaz_web.py` |
| **RNF-UI-2** | Navegación por rol, responsive y enlace activo con literal estable | `test_interfaz_web.py`, `test_accesibilidad_ui.py`, rutas |
| **RNF-UI-3** | Operación completa sin JavaScript; misma semántica HTTP | `test_htmx_*`, `test_presentacion.py` |
| **RNF-UI-4** | HTMX actualiza solo la región afectada sin duplicar efectos | `test_htmx_crud.py`, `test_htmx_tesoreria.py` |
| **RNF-UI-5** | Fragmentos mínimos, `Vary: HX-Request`, `HX-Trigger`/`HX-Redirect` | `test_presentacion.py`, `test_htmx_*` |
| **RNF-UI-6** | Modales accesibles con foco contenido y movimiento reducido | `test_ui_componentes.py`, `test_accesibilidad_ui.py` |
| **RNF-UI-7** | Toasts con rol, duración, apilado y pausa correctos | `test_ui_componentes.py` |
| **RNF-UI-8** | Teclado, foco visible, `aria-busy`, íconos y estados no solo por color | `test_accesibilidad_ui.py` |

## 5. Criterios de aceptación

1. Ningún template contiene `bootstrap`, `bootstrap-icons`, `data-bs-` ni
   `new bootstrap.Modal`.
2. El layout renderizado no referencia Bootstrap y declara Tailwind, HTMX y
   Alpine versionados.
3. Las tres anclas activas (`/partidos`, `/designaciones`, `/tesoreria`) emiten
   el literal `class="nav-link active"`.
4. `docs/arquitectura.md` §6 y `CHANGES.md` describen el estado final.
5. `openspec validate active-stack-frontend --strict` y
   `openspec validate --specs` pasan.
6. La suite completa queda verde: **543 tests**.

## 6. Deuda técnica

| Prioridad | Tema | Nota |
|---|---|---|
| Media | Build local de Tailwind | Play CDN compila en el navegador: peso, FOUC y dependencia de red |
| Media | CSP y SRI | Requiere el build local para fijar hashes estables |
| Baja | Tests E2E de navegador | La suite verifica markup renderizado y activos, no interacción real |
