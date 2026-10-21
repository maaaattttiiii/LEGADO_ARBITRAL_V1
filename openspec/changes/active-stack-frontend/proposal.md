# Proposal

## Why

La capa de presentación está acoplada a Bootstrap 5 por CDN: cada mutación recarga la página completa, los modales dependen del JavaScript de Bootstrap, la navegación no tiene un comportamiento responsive propio y no existe una capa de componentes ni activos estáticos versionados. Migrar al Active Stack (Tailwind CSS + HTMX + Alpine.js) mejora la usabilidad y la accesibilidad sin tocar la lógica de negocio, pero debe preservar el contrato HTTP actual (303/400/401/403/429) y los 401 tests existentes.

## What Changes

- Reemplazar el layout de `app/templates/base.html` por uno basado en Tailwind CSS, HTMX y Alpine.js, con navegación responsive adaptada al rol (`TESORERO` / `ARBITRO`).
- Incorporar activos propios en `app/static/` (CSS y JS) servidos por `StaticFiles` en `/static`.
- Extraer una capa de componentes Jinja (`partials/` y `componentes/`): layout, navegación, modales, toasts e íconos SVG inline.
- Convertir los formularios de login, alta/edición de árbitros, alta de partidos y acciones de liquidación a peticiones HTMX, con respuestas parciales y actualización de regiones sin recarga completa.
- Introducir modales de confirmación y notificaciones flotantes con Alpine.js, con foco atrapado, cierre por `Escape`, `aria-*` y respeto de `prefers-reduced-motion`.
- Mantener **mejora progresiva**: sin JavaScript o sin cabecera `HX-Request`, el sistema conserva exactamente el comportamiento actual (303 tras éxito, 400 con página completa ante validación).
- **BREAKING (interno)**: al finalizar, retirar Bootstrap CSS/JS y `bootstrap-icons` de las plantillas. No hay cambio de contrato HTTP ni de datos.
- Actualizar `docs/arquitectura.md` (capa de presentación y ciclo de request), `CHANGES.md` y el reflejo en `openspec/specs/interfaz-web/` al archivar.

## Capabilities

### New Capabilities

- `interfaz-web`: define el layout base, los activos de interfaz, la navegación por rol, el contrato de mejora progresiva, los formularios HTMX, los fragmentos, los modales, los toasts y los requisitos de accesibilidad de la capa de presentación.

### Modified Capabilities

- Ninguna. Las capacidades `autenticacion`, `arbitros`, `partidos`, `designaciones`, `liquidacion`, `tesoreria`, `exportacion` y `periodos` se consumen sin cambios de comportamiento: se preservan sus códigos de estado, mensajes visibles, reglas de sesión, guardas y aislamiento del portal.
- No se modifican `openspec/specs/` en este paso; el delta vive en `openspec/changes/active-stack-frontend/specs/interfaz-web/spec.md`.

## Impact

**Código afectado**

- `app/templates/base.html` y los 13 templates restantes (≈2.000 líneas), incluidos los modales de árbitros, partidos, canchas, torneos, tarifas, designaciones y tesorería.
- `app/static/` (nuevo contenido), `app/main.py` (montaje de estáticos y handlers HX-aware) y `app/templating.py` o un nuevo `app/presentacion.py` para el despacho de fragmentos.
- Rutas de `app/routes/`: solo agregan la rama de respuesta HTMX; siguen orquestando (parsear → servicio → `commit`/`rollback` → render o redirect), según la regla 19 de `AGENTS.md`.

**Dependencias**

- No se agrega ninguna dependencia Python; se descarta `jinja2-fragments` a favor de un helper propio.
- Tailwind CSS, HTMX y Alpine.js se cargan desde CDN en esta entrega. La deuda de producción (Play CDN) queda documentada y se resuelve en un change posterior.

**Contratos preservados**

- Login y guardas: 303, 401, 403, 429 y `Retry-After` sin cambios sin `HX-Request`.
- Portal del árbitro: el aislamiento por `usuario.arbitro_id` no se toca.
- Exportación mensual: los enlaces CSV/PDF siguen siendo descargas de página completa.
- Los 401 tests actuales deben pasar sin modificaciones; se agregan tests nuevos para el comportamiento HTMX y de accesibilidad.

**Reglas de negocio**

- No se crean ni modifican reglas de dominio. Se preservan RN-19 (rutas solo orquestan), RN-37 (exportación), RN-43/RN-44 (sesión y guardas), RN-45 (aislamiento del portal), RN-47 (cambio de clave), RN-48 (rate limiting) y RN-49/RN-50 (auditoría y cierres) sin cambios.
- Los nuevos identificadores `RNF-UI-1` a `RNF-UI-8` son requisitos no funcionales de presentación, no reglas de negocio.

**Governance**

- `BAJO` / `MEDIO`: templates, enums de presentación y assets son de baja autonomía; el contrato de rutas y la navegación son de nivel medio y requieren checkpoint.
- **CRÍTICO excluido**: no se toca `MovimientoCuentaCorriente`, saldos, liquidaciones, `Usuario`, hashing, cookies ni reglas de acceso.

**Alcance excluido**

- Lógica de negocio, servicios, modelos, migraciones Alembic, seeds y esquema de base de datos.
- Cambios en el contrato HTTP sin cabecera `HX-Request`, en la semántica de sesión o en las reglas de autorización.
- SPA, API JSON pública, framework JavaScript de cliente, modo oscuro, internacionalización, PWA y pipeline Node de build.
- Migración automática de datos o reescritura de movimientos históricos.
