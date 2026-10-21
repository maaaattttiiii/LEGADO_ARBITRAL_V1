# Design

## Context

Ver `proposal.md` para la motivación. El estado actual que condiciona el diseño:

- `app/templates/base.html` (101 líneas) carga Bootstrap 5.3.3 y `bootstrap-icons` 1.11.3 por CDN; la navbar usa `navbar-toggler` y el dropdown "Datos" depende del JS de Bootstrap.
- Hay 14 templates (≈2.000 líneas) con modales Bootstrap en árbitros, partidos, canchas, torneos, tarifas, designaciones y tesorería.
- `app/static/` existe pero está vacío; `app/main.py` no monta `StaticFiles`.
- `app/templating.py` expone un único `Jinja2Templates` con los filtros `fecha_local`, `moneda` y `periodo_local`.
- Las rutas responden 303 tras un POST exitoso y 400 con re-render completo ante error de validación. No hay capa de fragmentos ni dependencia `jinja2-fragments`.
- La suite tiene 401 tests: 156 asserts sobre `status_code`, 65 usos de `follow_redirects` y 148 usos de `respuesta.text` que verifican texto visible.
- Tres asserts exigen el literal exacto `class="nav-link active"`:
  `tests/test_designaciones_routes.py:488`, `tests/test_partidos_routes.py:305` y `tests/test_tesoreria_routes.py:421`.
- No hay toolchain JavaScript ni `package.json`; `requirements.txt` no incluye dependencias de fragmentos.

## Goals / Non-Goals

**Goals:**

- Introducir Tailwind CSS, HTMX y Alpine.js sin cambiar la lógica de negocio ni el contrato HTTP sin `HX-Request`.
- Dejar una capa de componentes y parciales reutilizable, testeable y compatible con la suite existente.
- Entregar la migración en fases donde cada una deja los 401 tests en verde y agrega sus propios tests.
- Mejorar accesibilidad (teclado, foco, ARIA, movimiento reducido) y comportamiento responsive.

**Non-Goals:**

- No se crea una SPA, una API JSON pública ni lógica de negocio en el cliente.
- No se modifican servicios, modelos, migraciones, seeds, sesión, hashing ni guardas.
- No se implementa un pipeline Node ni un build de Tailwind en esta entrega.
- No se agregan reglas de negocio ni se reescriben movimientos históricos.
- No se modifica el comportamiento de exportación CSV/PDF ni el de los enlaces de descarga.

## Decisions

### 1. Mejora progresiva y despacho de respuestas HX

**Decisión:** el servidor decide la respuesta según `HX-Request`. Sin la cabecera, el camino es exactamente el actual. Con `HX-Request: true`, la ruta devuelve un fragmento, `HX-Redirect` o un fragmento con `HX-Trigger`.

Se incorpora `app/presentacion.py` con una API mínima:

- `es_htmx(request) -> bool`: compara `request.headers.get("HX-Request", "")` con `"true"` sin distinguir mayúsculas.
- `respuesta_o_fragmento(request, *, completa, parcial, contexto, status_code=200, headers=None, trigger=None, redirect=None)`: sin HX delega en `templates.TemplateResponse`; con HX renderiza `parcial`, agrega `HX-Trigger` y/o `HX-Redirect` y `Vary: HX-Request`.
- `redireccion_htmx(destino, status_code=204)`: responde `HX-Redirect` sin cuerpo.
- `toast(tipo, mensaje, duracion=None)`: serializa el payload con `json.dumps(..., ensure_ascii=True)` para que la cabecera sea ASCII y segura.

Las rutas conservan la orquestación de la regla 19: parsean, llaman al servicio, hacen `commit`/`rollback` y eligen la respuesta. El helper no conoce reglas de negocio.

Matriz de contrato:

| Situación | Sin `HX-Request` | Con `HX-Request: true` |
|---|---|---|
| POST exitoso con recarga de listado | 303 al listado | 200 fragmento actualizado + `HX-Trigger` |
| Login exitoso | 303 al inicio del rol | 204 + `HX-Redirect` |
| Error de validación | 400 página completa | 400 fragmento + `HX-Trigger` de error |
| Sin sesión (`NoAutenticado`) | 303 a `/login?next=` | 204 + `HX-Redirect` |
| Cambio de clave requerido | 303 a `/cambiar-password` | 204 + `HX-Redirect` |
| Acceso denegado | 403 página completa | 403 fragmento + `HX-Trigger` |
| Rate limit | 429 página completa + `Retry-After` | 429 fragmento + `Retry-After` + `HX-Trigger` |

**Alternativas descartadas:** convertir todos los 303 en `HX-Redirect` de forma global (rompe el PRG clásico y los tests); usar `hx-boost` en el `body` (convierte toda navegación y multiplica el riesgo sin necesidad); detectar HTMX por user-agent o por un campo oculto (frágil y no estándar).

**Justificación:** el header es el mecanismo estándar de HTMX, permite que los tests actuales sigan ejercitando el flujo clásico y hace que la mejora sea verdaderamente opcional.

### 2. Estrategia de fragmentos: helper propio + parciales

**Decisión:** usar plantillas parciales dedicadas en `app/templates/partials/`, incluidas por las páginas completas, y un helper propio de despacho. No se usa `jinja2-fragments` ni el renderizado de bloques por introspección.

Estructura propuesta:

```
app/templates/
├── base.html
├── componentes/
│   ├── iconos.html        # macro icono(nombre, clase, titulo)
│   ├── modal.html         # macro de diálogo nativo + Alpine
│   └── toasts.html        # contenedor aria-live
├── partials/
│   ├── arbitros/listado.html
│   ├── partidos/listado.html
│   ├── tesoreria/cuentas.html
│   ├── tesoreria/partidos_a_liquidar.html
│   ├── tesoreria/cobros.html
│   └── tesoreria/cierres.html
└── ... (páginas completas que hacen {% include "partials/..." %})
```

La página completa y el fragmento comparten el mismo archivo parcial, así el texto visible nunca vive solo en una de las dos rutas. Las regiones se identifican con `id` estables (`#listado-arbitros`, `#partidos-a-liquidar`, `#cuentas-corrientes`, etc.).

**Alternativas consideradas:**

- **`jinja2-fragments` (`Jinja2Blocks`)**: resuelve el caso, pero reemplaza el motor de templates que usan las 9 rutas y los 401 tests. Una diferencia sutil en el contexto o en la herencia afecta todas las páginas a la vez; es una dependencia nueva y el cambio deja de ser aditivo. Se descarta para esta entrega.
- **Renderizado de bloques con `templates.env.get_template(...).blocks[...]`**: evita la dependencia, pero requiere inyectar `request` y el contexto a mano, se vuelve frágil con `{% extends %}` y con los `{% set %}` de `base.html`, y acopla el helper a la estructura interna de cada plantilla. Se descarta.
- **Duplicar markup entre página y fragmento**: genera divergencia de textos y clases, justo lo que rompería los 148 asserts de texto visible. Se descarta.

**Justificación:** el helper es aditivo, no toca el camino de render actual y mantiene una única fuente de markup. El costo es disciplina de inclusión, mitigado porque las páginas completas incluyen los parciales (no los copian).

### 3. Tailwind: Play CDN con deuda de producción documentada

**Decisión:** Tailwind CSS 3.4 vía Play CDN, con versión fijada en la URL, durante esta entrega. Sin toolchain Node.

- `base.html` carga `https://cdn.tailwindcss.com/3.4.x` y un bloque `tailwind.config` con los tokens del proyecto.
- **Durante la convivencia con Bootstrap** se configura `corePlugins: { preflight: false }` para que el reset de Tailwind no rompa tablas, formularios y utilidades Bootstrap que todavía no se migraron.
- En la fase final se retira Bootstrap, se elimina la excepción de preflight y se conserva solo la configuración de tema.
- Los estilos propios viven en `app/static/css/app.css` (CSS plano y variables), montado con `StaticFiles` en `/static` desde `app/main.py`.
- Los scripts propios viven en `app/static/js/app.js` y se cargan con `defer` antes de Alpine.
- `.nav-link` y `.nav-link.active` se definen en `app/static/css/app.css`, no con utilidades Tailwind en el ancla. Así el atributo `class` del enlace activo sigue siendo exactamente `class="nav-link active"`.

**Deuda técnica de producción (se registra en `docs/arquitectura.md` y `CHANGES.md`):**

- Play CDN compila Tailwind en el navegador: agrega peso, provoca un primer render sin estilos (FOUC), no hace purge/tree-shaking y no permite SRI estable.
- Requiere red hacia el CDN; no funciona offline y complica una futura CSP estricta.
- Mitigaciones de esta entrega: versión fijada, CSS crítico propio en `app.css`, carga diferida de scripts y ninguna regla de negocio en el cliente.
- Trabajo futuro (fuera de alcance): Tailwind standalone CLI o PostCSS generando `app/static/css/tailwind.css` versionado y servido localmente, con CSP y SRI.

**Alternativas descartadas:** pipeline Node (el proyecto no tiene `package.json`, lockfile ni CI de frontend); Tailwind standalone CLI ahora (agrega un artefacto de build y un paso operativo que este change no necesita para validar el comportamiento); mantener Bootstrap y sumar Tailwind indefinidamente (deuda visual y de peso).

### 4. Iconografía: macro SVG inline y retiro gradual de `bootstrap-icons`

**Decisión:** crear `templates/componentes/iconos.html` con un macro `icono(nombre, clase="", titulo=None)` que renderiza SVG inline de 24×24, `stroke="currentColor"`, sin peticiones adicionales. Los íconos decorativos emiten `aria-hidden="true"`; los significativos emiten `role="img"` y `<title>`.

- Durante las fases 1 a 4 se mantiene `bootstrap-icons` para los templates aún no migrados.
- Cada template migrado reemplaza sus `<i class="bi ...">` por el macro.
- En la fase final se elimina el CSS de `bootstrap-icons` y se verifica que no queden referencias `bi bi-`.

El inventario inicial a cubrir es acotado: bandera, persona, auto, salida, check, alerta, información, filtro, dinero, candado, desbloqueo, CSV, PDF, suma, calendario, banco, cerrar y flechas de navegación.

**Alternativas descartadas:** conservar `bootstrap-icons` (es independiente del CSS de Bootstrap, pero suma otro CDN, una fuente de íconos y un lenguaje visual distinto a Tailwind); Lucide por CDN JS (dependencia de runtime y riesgo de layout shift); íconos como imágenes (peor accesibilidad y theming).

**Justificación:** elimina un CDN y una fuente, funciona offline y con `currentColor`, y permite controlar accesibilidad desde un único macro.

### 5. Modales: `<dialog>` nativo controlado por Alpine

**Decisión:** reemplazar `data-bs-toggle="modal"`, `modal fade` y `new bootstrap.Modal(...)` por un componente basado en `<dialog>` nativo y estado Alpine.

- El macro abre con `showModal()` y cierra con `close()`; Alpine maneja el estado (`abierto`) y el contenido.
- `<dialog>` aporta foco atrapado, inertización del fondo, `Escape` mediante el evento `cancel`, backdrop y semántica de modal sin JS manual.
- Se agregan `aria-labelledby` al título y `aria-describedby` a la descripción cuando corresponde; el botón de cierre tiene `aria-label="Cerrar"`.
- Al cerrar se devuelve el foco al disparador y se restaura el scroll del `body` si el componente lo bloqueó.
- La reapertura por error de validación usa un atributo server-side (`data-abrir-modal="modalAlta"`) que Alpine interpreta al inicializar; se elimina el `<script>new bootstrap.Modal(...).show()</script>`.
- Los modales de confirmación de acciones destructivas (liquidar, cerrar período, cierre en lote, reabrir, bajas lógicas) son un componente genérico con mensaje y botón de confirmación.
- Transiciones con `x-transition` y CSS; `@media (prefers-reduced-motion: reduce)` desactiva animaciones y transiciones.

**Alternativa descartada:** `x-show` con un `div` y foco atrapado manual. Requiere reimplementar inertización, tab cycling, backdrop y Escape, con más código y más superficie de bugs de accesibilidad. `x-trap` (plugin de Alpine) agrega una dependencia que `<dialog>` vuelve innecesaria.

**Justificación:** menos JavaScript propio, mejor accesibilidad por defecto y compatibilidad con los navegadores soportados por el proyecto.

### 6. Toasts: evento HTMX + store Alpine

**Decisión:** el servidor emite un evento `cabm:toast` en `HX-Trigger` y un store Alpine lo consume.

Formato de la cabecera:

```
HX-Trigger: {"cabm:toast":{"tipo":"success","mensaje":"Árbitro creado.","duracion":5000}}
```

- `app/static/js/app.js` registra el store en `alpine:init` y escucha el evento en `document.body` (HTMX lo dispara sobre el elemento que originó la petición y burbujea).
- El store mantiene una lista con máximo 3 toasts visibles; al superar el límite descarta el más antiguo.
- Duración por defecto: 5 segundos para éxito/información; 8 segundos para error; `duracion: 0` lo hace persistente hasta el cierre manual.
- Pausa al pasar el puntero o enfocar, reanuda al salir.
- Contenedor con `aria-live="polite"`; cada toast de éxito/información usa `role="status"`, los de error usan `role="alert"` y `aria-live="assertive"`.
- Posición superior derecha en escritorio y parte inferior en móvil; cierre con botón accesible y con `Escape` cuando tiene foco.
- Sin JavaScript, el mensaje sigue en la página completa como alerta (`?ok=` / `?error=`), que es lo que verifican los tests actuales. En respuestas HTMX el parcial no duplica la alerta visible: el toast es el canal accesible.

**Alternativas descartadas:** renderizar el toast dentro del fragmento (se pierde al hacer el siguiente swap y no se apila); usar solo `alert()` (bloqueante e inaccesible); una librería de toasts (dependencia innecesaria para el alcance).

### 7. Entrega por fases con suite verde en cada una

Cada fase es un commit revisable e independientemente revertible. No hay migraciones de esquema, así que el rollback es revertir el commit de la fase.

| Fase | Alcance | Criterio de suite verde |
|---|---|---|
| F1. Cimientos | `StaticFiles`, `app.css`, `app.js`, Tailwind/HTMX/Alpine en `base.html`, navbar responsive por rol, `.nav-link` propio, macro de íconos inicial | 401 tests existentes verdes sin modificarlos + `tests/test_interfaz_web.py` verde; los 3 asserts de `class="nav-link active"` pasan |
| F2. Componentes | Macro de íconos completo, modal `<dialog>` + Alpine, store de toasts; migración de los modales de árbitros y partidos | 401 + `tests/test_ui_componentes.py` verdes; no quedan `data-bs-*` en los templates migrados |
| F3. Auth y contrato HX | `app/presentacion.py`, login y cambio de clave HTMX, handlers HX-aware de `main.py` | 401 + `tests/test_presentacion.py` + `tests/test_htmx_auth.py` verdes; 303/401/403/429 y `Retry-After` sin header intactos |
| F4. Formularios CRUD | Parciales y HTMX en árbitros, partidos, canchas, torneos y tarifas | 401 + `tests/test_htmx_crud.py` verdes; los 65 `follow_redirects` y los 156 asserts de status siguen pasando |
| F5. Tesorería y liquidaciones | Parciales de cuentas/partidos/cobros/cierres, HTMX en liquidar, cobro, ajuste, cierre y reapertura, swaps OOB | 401 + `tests/test_htmx_tesoreria.py` verdes; idempotencia de liquidación verificada |
| F6. Retiro de Bootstrap | Quitar Bootstrap CSS/JS y `bootstrap-icons`, habilitar preflight, reemplazar clases restantes, pasada final de accesibilidad y documentación | 401 + todos los tests nuevos verdes; `test_accesibilidad_ui.py` verde; sin referencias a Bootstrap en templates; `openspec validate --specs` verde |

**Justificación:** el cambio toca 14 templates y una suite con muchos asserts frágiles. Las fases separan infraestructura, componentes, contrato HTTP, formularios y acciones financieras, de modo que una regresión se localiza en la fase que la introdujo. La fase 6 (retiro de Bootstrap) es deliberadamente la última: durante la convivencia el sitio sigue funcionando aunque una migración visual quede incompleta.

### 8. Riesgos y mitigaciones

Ver la sección siguiente.

## Risks / Trade-offs

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Romper el literal `class="nav-link active"` | 3 tests fallan y se bloquea la entrega | El ancla no lleva utilidades Tailwind; `.nav-link` se estiliza en `app.css`; test dedicado en `tests/test_interfaz_web.py` que verifica el atributo exacto |
| Perder texto visible al moverlo a parciales | 148 asserts de `respuesta.text` fallan | La página completa incluye el mismo parcial; nunca se renderiza texto solo en la rama HTMX; suite completa en cada fase |
| Cambiar códigos de estado o redirects por accidente | 156 asserts de status y 65 `follow_redirects` fallan | La rama HX se decide solo por cabecera; el camino sin header no se reescribe; tests de contrato en `tests/test_presentacion.py` |
| HTMX sigue un 303 y lo incrusta en la región | Página rota tras login o guarda | `HX-Redirect` en login/guardas; response 204; tests con `HX-Request: true` |
| Perder `Retry-After` en el flujo HTMX | Rate limiting inconsistente | La rama HX conserva cabeceras y status; test específico de 429 |
| Regresión visual al convivir Tailwind y Bootstrap | Layout roto en pantallas no migradas | Preflight desactivado durante la convivencia; migración por fases; retiro de Bootstrap solo en F6 |
| Play CDN no apto para producción | Peso, FOUC, dependencia de red y CSP | Deuda documentada; versión fijada; CSS crítico propio; change futuro con build local |
| Duplicación de markup entre página y parcial | Divergencia de textos y estilos | Una sola fuente por parcial incluida en la página; revisión en cada fase |
| Doble envío de una liquidación | Movimientos duplicados | `hx-disabled-elt` en el control + idempotencia existente del servicio; test de doble POST |
| Regresiones de accesibilidad en modales | Usuarios de teclado bloqueados | `<dialog>` nativo, foco devuelto al disparador, `Escape`, `aria-*`, `prefers-reduced-motion`; tests en `tests/test_accesibilidad_ui.py` |
| Orden de carga Tailwind/Alpine/HTMX | Store de toasts no registrado o FOUC | `defer` en orden, store en `alpine:init`, `x-cloak` en CSS |
| Sin CSP ni SRI en los CDN | Superficie de seguridad | No hay CSP hoy; se documenta y se resuelve junto con el build local futuro |

## Migration Plan

1. **F1**: montar `/static`, crear `app.css`/`app.js`, reescribir `base.html` con Tailwind (preflight off), HTMX y Alpine, y migrar la navbar. Bootstrap sigue cargado para el resto. Actualizar `docs/arquitectura.md` §2 y §6.
2. **F2**: crear `componentes/` y migrar modales de árbitros y partidos; reemplazar los scripts de reapertura por atributos declarativos.
3. **F3**: agregar `app/presentacion.py`, migrar login y cambio de clave, hacer HX-aware los handlers de `main.py` y documentar el contrato de fragmentos.
4. **F4**: extraer parciales y agregar la rama HTMX a los formularios CRUD restantes.
5. **F5**: extraer parciales de tesorería y migrar liquidaciones, cobros, ajustes, cierres y reaperturas con swaps OOB.
6. **F6**: retirar Bootstrap y `bootstrap-icons`, habilitar preflight, completar la pasada de accesibilidad y actualizar `docs/arquitectura.md`, `docs/specs/v3_interfaz_web.md`, `CHANGES.md` y la spec viva.

**Rollback:** revertir el commit de la fase afectada. No hay cambios de esquema, datos ni contratos sin `HX-Request`, por lo que un rollback no requiere migración inversa.

**Verificación por fase:** `& C:\Python314\python.exe -m pytest -q` (401 tests existentes + los nuevos de la fase), revisión de que no se modificaron tests existentes y, al cerrar, `openspec validate --specs`.
