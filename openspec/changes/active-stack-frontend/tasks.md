# Tasks

## 1. Línea base y cimientos de la interfaz (Fase 1)

- [x] 1.1 Ejecutar `& C:\Python314\python.exe -m pytest -q` y registrar la línea base de 401 tests verdes antes de tocar templates; verificar que el comando termina con código 0.
- [x] 1.2 Crear `tests/test_interfaz_web.py` en RED con estos casos: `GET /static/css/app.css` y `GET /static/js/app.js` responden 200; `base.html` declara `lang="es"`, viewport y referencias a Tailwind, HTMX y Alpine; la navegación del tesorero y del árbitro muestra solo sus secciones; verificar que los casos nuevos fallan antes de implementar.
- [x] 1.3 Montar `StaticFiles` en `/static` sobre `app/static/` en `app/main.py` y crear `app/static/css/app.css` y `app/static/js/app.js`; verificar que los casos de activos de `tests/test_interfaz_web.py` pasan.
- [x] 1.4 Reescribir `app/templates/base.html` con Tailwind Play CDN (versión fijada y `preflight: false` durante la convivencia), HTMX y Alpine con `defer`; mantener Bootstrap cargado para los templates aún no migrados y verificar `tests/test_interfaz_web.py` y la suite completa.
- [x] 1.5 Implementar la navegación responsive por rol con Alpine (`x-data`, `aria-expanded`, `aria-controls`, cierre con `Escape`) en `base.html`; verificar los escenarios de navegación de `tests/test_interfaz_web.py`.
- [x] 1.6 Estilizar `.nav-link` y `.nav-link.active` en `app/static/css/app.css` sin agregar clases Tailwind al ancla y verificar que los asserts de `class="nav-link active"` en `tests/test_designaciones_routes.py`, `tests/test_partidos_routes.py` y `tests/test_tesoreria_routes.py` siguen pasando.
- [x] 1.7 Actualizar `docs/arquitectura.md` §2 (capa de presentación, `app/static/`) y §6 (Frontend) con el estado de la fase; verificar que el documento menciona `/static`, Tailwind, HTMX y Alpine y que `& C:\Python314\python.exe -m pytest -q` sigue verde.

## 2. Componentes: íconos, modales y toasts (Fase 2)

- [x] 2.1 Crear `tests/test_ui_componentes.py` en RED con: los templates migrados no contienen `data-bs-`, los modales emiten `role="dialog"` y `aria-modal="true"`, y los íconos decorativos usan `aria-hidden="true"`; verificar que falla antes de implementar.
- [x] 2.2 Crear `app/templates/componentes/iconos.html` con el macro `icono(nombre, clase, titulo)` y reemplazar los íconos de `arbitros/index.html` y `partidos/index.html`; verificar los casos de íconos de `tests/test_ui_componentes.py`.
- [x] 2.3 Crear `app/templates/componentes/modal.html` con `<dialog>` nativo controlado por Alpine (apertura con `showModal`, cierre con `close`, `Escape`, foco devuelto al disparador y `prefers-reduced-motion`) y migrar el modal de alta de `arbitros/index.html`; verificar `tests/test_ui_componentes.py` y `tests/test_arbitros_routes.py`.
- [x] 2.4 Migrar el modal de `partidos/index.html` al componente y reemplazar el script `new bootstrap.Modal(...).show()` por el atributo declarativo de reapertura; verificar `tests/test_ui_componentes.py` y `tests/test_partidos_routes.py`.
- [x] 2.5 Crear `app/templates/componentes/toasts.html` y el store Alpine en `app/static/js/app.js` (máximo 3, duración 5 s/8 s, pausa al enfocar, `role="status"`/`role="alert"`); verificar los casos de toasts de `tests/test_ui_componentes.py`.
- [x] 2.6 Documentar la capa de componentes (`componentes/`, `partials/`, store de toasts) en `docs/arquitectura.md` §6; verificar que el inventario coincide con los archivos creados.
- [x] 2.7 Ejecutar la suite completa y verificar que los 401 tests existentes y `tests/test_ui_componentes.py` pasan sin modificar tests previos.

## 3. Contrato HTMX, login y guardas (Fase 3)

- [x] 3.1 Crear `tests/test_presentacion.py` en RED para `es_htmx()`, `respuesta_o_fragmento()`, `toast()`, `Vary: HX-Request` y la ausencia de `<html>`/`<head>`/`<body>` en fragmentos; verificar que falla antes de implementar.
- [x] 3.2 Implementar `app/presentacion.py` con `es_htmx`, `respuesta_o_fragmento`, `redireccion_htmx` y `toast`, sin lógica de negocio; verificar `tests/test_presentacion.py`.
- [x] 3.3 Crear `tests/test_htmx_auth.py` en RED con: login sin header conserva 303/401/429 y `Retry-After`; login con `HX-Request` devuelve `HX-Redirect` o fragmento; guarda sin sesión devuelve `HX-Redirect`; verificar que falla antes de implementar.
- [x] 3.4 Migrar `login.html` a HTMX (`hx-post`, objetivo del panel, toast de error) manteniendo el formulario clásico; verificar `tests/test_htmx_auth.py`, `tests/test_auth.py` y `tests/test_login_limiter.py`.
- [x] 3.5 Migrar `cambiar_password.html` a HTMX y verificar `tests/test_htmx_auth.py` y `tests/test_password.py`.
- [x] 3.6 Hacer HX-aware los handlers de `app/main.py` (`NoAutenticado`, `CambioPasswordRequerido`, `AccesoDenegado`) y verificar las guardas de `tests/test_htmx_auth.py` y `tests/test_auth.py`.
- [x] 3.7 Actualizar `docs/arquitectura.md` (ciclo de request y §6) con la matriz de respuesta sin/con `HX-Request`; verificar que la matriz coincide con `app/presentacion.py`.
- [x] 3.8 Ejecutar la suite completa y verificar que los 401 tests existentes y los nuevos de la fase pasan.

## 4. Formularios CRUD con HTMX (Fase 4)

- [x] 4.1 Crear `tests/test_htmx_crud.py` en RED, parametrizado por árbitros, partidos, canchas, torneos y tarifas: sin `HX-Request` conserva 303/400; con `HX-Request` devuelve 200 con fragmento y `HX-Trigger`; verificar que falla antes de implementar.
- [x] 4.2 Extraer `app/templates/partials/arbitros/listado.html`, hacer que `arbitros/index.html` lo incluya y agregar la rama HTMX a `app/routes/arbitros.py`; verificar `tests/test_htmx_crud.py` y `tests/test_arbitros_routes.py`.
- [x] 4.3 Extraer `app/templates/partials/partidos/listado.html` y agregar la rama HTMX a `app/routes/partidos.py`; verificar `tests/test_htmx_crud.py` y `tests/test_partidos_routes.py`.
- [x] 4.4 Extraer los parciales de canchas, torneos y tarifas y agregar la rama HTMX a sus rutas; verificar `tests/test_htmx_crud.py`, `tests/test_canchas_routes.py`, `tests/test_torneos_routes.py` y `tests/test_tarifas_routes.py`.
- [x] 4.5 Agregar `hx-disabled-elt` a los formularios, cerrar el modal en éxito y emitir el toast con `HX-Trigger`; verificar los casos de doble envío y de error con reapertura del modal en `tests/test_htmx_crud.py`.
- [x] 4.6 Documentar en `docs/arquitectura.md` §6 el mapa de parciales y las regiones (`#listado-arbitros`, etc.); verificar que los `id` documentados existen en los templates.
- [x] 4.7 Ejecutar la suite completa y verificar que los 401 tests existentes y `tests/test_htmx_crud.py` pasan, sin cambios en los tests previos.

## 5. Tesorería y liquidaciones con HTMX (Fase 5)

- [x] 5.1 Crear `tests/test_htmx_tesoreria.py` en RED con: liquidar sin header conserva 303 y `?ok=`; con `HX-Request` devuelve fragmento y `HX-Trigger`; doble liquidación no duplica movimientos; cobro, ajuste, cierre y reapertura conservan sus códigos; verificar que falla antes de implementar.
- [x] 5.2 Extraer `partials/tesoreria/cuentas.html`, `partidos_a_liquidar.html`, `cobros.html` y `cierres.html`, incluirlos desde `tesoreria/index.html` y verificar `tests/test_tesoreria_routes.py` sin cambios.
- [x] 5.3 Migrar la acción Liquidar al modal de confirmación Alpine y a HTMX con swap de los parciales de cuentas y partidos; verificar `tests/test_htmx_tesoreria.py` y la idempotencia en `tests/test_liquidacion.py`.
- [x] 5.4 Migrar el registro de cobro y el ajuste manual (modal) a HTMX; verificar `tests/test_htmx_tesoreria.py`, `tests/test_cobros.py` y `tests/test_tesoreria_routes.py`.
- [x] 5.5 Migrar cierre, cierre en lote y reapertura a modales de confirmación y HTMX, conservando el bloqueo por período cerrado; verificar `tests/test_htmx_tesoreria.py`, `tests/test_cierres.py` y `tests/test_reapertura.py`.
- [x] 5.6 Verificar que los enlaces de exportación CSV/PDF siguen siendo descargas de página completa y no usan HTMX; test en `tests/test_htmx_tesoreria.py` y `tests/test_exportacion.py`.
- [x] 5.7 Documentar en `docs/arquitectura.md` §6 las regiones y los swaps OOB de tesorería; verificar que coinciden con los `id` y `hx-swap-oob` implementados.
- [x] 5.8 Ejecutar la suite completa y verificar que los 401 tests existentes y `tests/test_htmx_tesoreria.py` pasan.

## 6. Retiro de Bootstrap, accesibilidad y documentación (Fase 6)

- [x] 6.1 Crear `tests/test_accesibilidad_ui.py` en RED con: foco visible y orden de tabulación en navegación/modales, `aria-busy` durante una petición HTMX, íconos decorativos con `aria-hidden`, íconos significativos con nombre accesible y ausencia de estados comunicados solo por color; verificar que falla antes de implementar.
- [x] 6.2 Ampliar `tests/test_interfaz_web.py` en RED para exigir que ningún template contenga `bootstrap`, `bootstrap-icons`, `data-bs-` ni `new bootstrap.Modal`; verificar que falla antes del retiro.
- [x] 6.3 Reemplazar las clases Bootstrap restantes por Tailwind, migrar los modales e íconos pendientes (canchas, torneos, tarifas, designaciones, tesorería, portal) y eliminar Bootstrap CSS/JS y `bootstrap-icons` de `base.html`; verificar `tests/test_interfaz_web.py` y `tests/test_accesibilidad_ui.py`.
- [x] 6.4 Habilitar el reset (preflight) de Tailwind, retirar la excepción de convivencia y ajustar `app/static/css/app.css`; verificar que todas las páginas renderizan y que `tests/test_interfaz_web.py` pasa.
- [x] 6.5 Ejecutar `& C:\Python314\python.exe -m pytest -q` y verificar que los 401 tests existentes más todos los tests nuevos pasan; registrar el conteo final.
- [x] 6.6 Ejecutar `openspec validate active-stack-frontend --strict` y verificar que pasa; no editar `openspec/specs/` hasta el archive, porque la delta es la fuente del reflejo.
- [x] 6.7 Crear `docs/specs/v3_interfaz_web.md` con el contrato, las fases y los criterios de aceptación de la entrega; verificar que cita `RNF-UI-1` a `RNF-UI-8`.
- [x] 6.8 Actualizar `docs/arquitectura.md` (stack final, `/static`, contrato de fragmentos y deuda de Tailwind CDN) y `CHANGES.md` (entrega, suite final y deuda técnica); verificar que ambos describen el estado real y que `openspec validate --specs` pasa.

## Workflow follow-up

- Archivar el change con `openspec archive active-stack-frontend` una vez satisfecha la revisión humana.
- Verificar que el archive creó `openspec/specs/interfaz-web/spec.md` y que refleja la delta aprobada.
- Abrir un change posterior para el build local de Tailwind (standalone CLI/PostCSS), CSP y SRI; no forma parte de esta entrega.

