# interfaz-web Specification

## Purpose
Define la capa de presentación del sistema como una interfaz renderizada en servidor con mejora progresiva: layout y navegación responsive, formularios HTMX, modales y notificaciones accesibles, preservando el contrato HTTP y el funcionamiento sin JavaScript.

## Requirements

### Requirement: Layout base y activos de interfaz

Toda página SHALL heredar de un layout único que declare `lang="es"`, viewport, título por página y cargue la hoja del Active Stack, HTMX y Alpine desde recursos versionados. Los estilos y scripts propios MUST servirse desde `/static` con respuesta 200 y tipo de contenido correcto. El layout MUST NOT requerir Bootstrap para renderizar.

Ref: RNF-UI-1.

#### Scenario: Activos propios servidos

- **WHEN** se solicita `GET /static/css/app.css` o `GET /static/js/app.js`
- **THEN** la respuesta es 200 con el tipo de contenido correspondiente a CSS o JavaScript

#### Scenario: Layout común

- **WHEN** se solicita cualquier página HTML del sistema
- **THEN** la respuesta contiene un único `<html lang="es">`, la meta de viewport, un título de página y las referencias a Tailwind CSS, HTMX y Alpine.js
- **THEN** la respuesta no contiene referencias a Bootstrap CSS ni a Bootstrap JS

### Requirement: Navegación por rol y responsive

La navegación SHALL mostrar solo las secciones habilitadas para el rol de la sesión y SHALL colapsar en un control accesible en viewports angostos. El enlace de la sección actual MUST emitir exactamente `class="nav-link active"`, sin clases adicionales en ese atributo, y `aria-current="page"`. El cierre de sesión MUST permanecer visible para usuarios autenticados.

Ref: RNF-UI-2; RN-44.

#### Scenario: Navegación del tesorero

- **WHEN** un usuario con rol `TESORERO` solicita `/tesoreria`
- **THEN** la navegación muestra Árbitros, Partidos, Designaciones, Panel Tesorero y Datos
- **THEN** la navegación no muestra Mis partidos ni Mi cuenta

#### Scenario: Navegación del árbitro

- **WHEN** un usuario con rol `ARBITRO` solicita `/mis-partidos`
- **THEN** la navegación muestra únicamente Mis partidos, Mi cuenta y Salir
- **THEN** la navegación no muestra Árbitros, Partidos, Designaciones, Panel Tesorero ni Datos

#### Scenario: Enlace activo con literal estable

- **WHEN** se solicita `/partidos`, `/designaciones` o `/tesoreria`
- **THEN** el enlace de la sección correspondiente contiene exactamente `class="nav-link active"` y `aria-current="page"`
- **THEN** el atributo `class` de ese enlace no contiene ninguna otra clase

#### Scenario: Menú colapsable accesible

- **WHEN** el viewport es angosto y el usuario activa el control de menú
- **THEN** el control cambia `aria-expanded` de `false` a `true`, `aria-controls` referencia al contenedor del menú y el menú queda visible
- **WHEN** el usuario vuelve a activarlo o presiona `Escape`
- **THEN** el menú se oculta y `aria-expanded` vuelve a `false`

#### Scenario: Sin sesión

- **WHEN** un visitante sin sesión solicita `/login`
- **THEN** la navegación no muestra enlaces a secciones protegidas y conserva el acceso al formulario de ingreso

### Requirement: Compatibilidad sin JavaScript

Sin JavaScript, sin HTMX o sin cabecera `HX-Request`, cada formulario MUST conservar `method` y `action` y el servidor MUST responder igual que hoy: 303 tras éxito y 400 con página completa ante error de validación. Con `HX-Request: true` SHALL responder un fragmento o `HX-Redirect`. Ninguna operación MUST depender de JavaScript para completarse.

Ref: RNF-UI-3; RN-19.

#### Scenario: POST clásico exitoso

- **WHEN** se envía un alta válida por `POST` sin cabecera `HX-Request`
- **THEN** la respuesta es 303 con `Location` al listado correspondiente

#### Scenario: Validación clásica con página completa

- **WHEN** se envía un formulario inválido sin cabecera `HX-Request`
- **THEN** la respuesta es 400 con un documento HTML completo
- **THEN** el mensaje de error es visible en el cuerpo de la página

#### Scenario: Petición HTMX

- **WHEN** se envía el mismo formulario con `HX-Request: true`
- **THEN** la respuesta es un fragmento HTML sin `<html>`, `<head>` ni `<body>`, o una redirección mediante `HX-Redirect`
- **THEN** el código de estado conserva el significado del flujo clásico (200, 400, 401, 403 o 429)

#### Scenario: Login sin JavaScript

- **WHEN** un usuario con JavaScript deshabilitado envía credenciales válidas en `/login`
- **THEN** el formulario realiza un `POST` normal y el navegador llega al inicio de su rol

### Requirement: Formularios HTMX sin recarga

Los formularios de login, alta y edición de árbitros, alta de partidos y acciones de liquidación SHALL usar HTMX para actualizar solo la región afectada, sin recarga completa. El servidor MUST aplicar las mismas validaciones y la misma idempotencia que el flujo clásico, y MUST NOT duplicar movimientos ante reintentos. El control de envío SHALL deshabilitarse mientras la petición está en curso.

Ref: RNF-UI-4; RN-19.

#### Scenario: Alta de árbitro con HTMX

- **WHEN** se envía un alta válida de árbitro con `HX-Request: true`
- **THEN** la respuesta es 200 con el fragmento actualizado del listado que incluye el nuevo árbitro
- **THEN** el modal de alta se cierra y se emite un evento de notificación de éxito

#### Scenario: Error de validación con HTMX

- **WHEN** se envía un alta inválida con `HX-Request: true`
- **THEN** la respuesta es 400 con el fragmento del formulario
- **THEN** los valores ingresados se conservan y el mensaje de error es visible dentro del formulario

#### Scenario: Liquidación idempotente con HTMX

- **WHEN** se envía dos veces la liquidación del mismo partido con `HX-Request: true`
- **THEN** la segunda respuesta informa el resultado sin crear honorarios, retenciones ni viáticos duplicados

#### Scenario: Login con HTMX

- **WHEN** se envían credenciales válidas con `HX-Request: true`
- **THEN** la respuesta usa `HX-Redirect` hacia el destino interno o el inicio del rol
- **WHEN** las credenciales son inválidas
- **THEN** la respuesta conserva 401 y devuelve el fragmento del formulario con el mensaje visible

### Requirement: Contrato de fragmentos y encabezados

Las respuestas parciales MUST reutilizar las mismas plantillas parciales incluidas por la página completa, MUST declarar `Vary: HX-Request` y MUST NOT contener `<html>`, `<head>` ni `<body>`. Los eventos de interfaz SHALL viajar en `HX-Trigger` como JSON y las redirecciones SHALL usar `HX-Redirect`. Los códigos 400/401/403/429 y la cabecera `Retry-After` MUST conservarse.

Ref: RNF-UI-5; RN-48.

#### Scenario: Fragmento mínimo

- **WHEN** una petición con `HX-Request: true` obtiene una respuesta parcial
- **THEN** el cuerpo no contiene `<!doctype`, `<html`, `<head` ni `<body`
- **THEN** la respuesta incluye `Vary: HX-Request`

#### Scenario: Evento y redirección

- **WHEN** una operación HTMX finaliza con éxito y debe notificar al usuario
- **THEN** la respuesta incluye `HX-Trigger` con un JSON válido cuyo evento contiene tipo y mensaje
- **WHEN** la operación requiere navegar a otra página
- **THEN** la respuesta incluye `HX-Redirect` con una ruta interna

#### Scenario: Rate limiting conservado

- **WHEN** un login bloqueado por intentos fallidos se envía con `HX-Request: true`
- **THEN** la respuesta conserva el código 429 y la cabecera `Retry-After`
- **THEN** el fragmento muestra el mismo mensaje visible que el flujo clásico

#### Scenario: Guarda con petición HTMX

- **WHEN** una petición HTMX llega sin sesión válida
- **THEN** la respuesta usa `HX-Redirect` hacia `/login?next=...` y no entrega una página completa para incrustar en la región

### Requirement: Modales de confirmación accesibles

Los modales SHALL abrirse y cerrarse con Alpine.js y exponer `role="dialog"`, `aria-modal="true"` y un nombre accesible. Mientras estén abiertos MUST atrapar el foco, cerrarse con `Escape` y devolver el foco al disparador. Las acciones destructivas MUST pedir confirmación explícita. Con `prefers-reduced-motion: reduce` MUST NOT animarse.

Ref: RNF-UI-6.

#### Scenario: Apertura con foco contenido

- **WHEN** el usuario activa el botón que abre un modal
- **THEN** el modal queda visible con `role="dialog"`, `aria-modal="true"` y nombre accesible
- **THEN** el foco se mueve al primer control del modal y los elementos del fondo no reciben foco

#### Scenario: Cierre con Escape

- **WHEN** el modal está abierto y el usuario presiona `Escape`
- **THEN** el modal se cierra y el foco vuelve al botón que lo abrió

#### Scenario: Confirmación de acción destructiva

- **WHEN** el usuario activa Liquidar, Cerrar período o Reabrir período
- **THEN** aparece un modal de confirmación con la consecuencia de la acción
- **WHEN** el usuario cancela
- **THEN** no se envía ninguna petición al servidor

#### Scenario: Reapertura por error de validación

- **WHEN** un formulario dentro de un modal recibe 400
- **THEN** el modal se reabre con el mensaje de error y los valores ingresados

#### Scenario: Movimiento reducido

- **WHEN** el sistema operativo declara `prefers-reduced-motion: reduce`
- **THEN** el modal se abre y cierra sin animación

### Requirement: Notificaciones flotantes

El sistema SHALL mostrar notificaciones flotantes ante el resultado de una operación HTMX, con tipo, duración, apilado acotado y cierre manual. Éxito e información MUST usar `role="status"` y `aria-live="polite"`; error MUST usar `role="alert"` y `aria-live="assertive"`. El mensaje MUST seguir disponible en la página completa cuando no hay JavaScript.

Ref: RNF-UI-7.

#### Scenario: Notificación de éxito

- **WHEN** una operación HTMX responde con un evento de éxito
- **THEN** aparece un toast con `role="status"` y `aria-live="polite"`
- **THEN** el toast se descarta automáticamente a los 5 segundos y se apilan como máximo 3 visibles

#### Scenario: Notificación de error

- **WHEN** una operación HTMX responde con un evento de error
- **THEN** aparece un toast con `role="alert"` y `aria-live="assertive"`
- **THEN** permanece visible al menos 8 segundos o hasta que el usuario lo cierre

#### Scenario: Pausa de la duración

- **WHEN** el puntero o el foco se posa sobre un toast
- **THEN** su descarte automático se pausa y se reanuda al salir

#### Scenario: Sin JavaScript

- **WHEN** una operación se completa sin JavaScript
- **THEN** el mensaje de resultado se muestra como alerta en la página completa, sin depender del toast

### Requirement: Accesibilidad y estados de carga

Toda la interfaz SHALL ser operable por teclado, con foco visible, etiquetas asociadas, contraste suficiente y jerarquía de encabezados. Durante una petición HTMX la región afectada MUST exponer `aria-busy="true"` y un indicador que no dependa solo del color. Los íconos decorativos MUST ocultarse a tecnologías asistivas y los significativos MUST tener nombre accesible.

Ref: RNF-UI-8.

#### Scenario: Operación por teclado

- **WHEN** el usuario recorre la página con `Tab` y `Shift+Tab`
- **THEN** puede alcanzar y activar todos los controles en orden lógico
- **THEN** el elemento enfocado muestra un indicador de foco visible

#### Scenario: Estado de carga HTMX

- **WHEN** una petición HTMX está en curso sobre una región
- **THEN** la región expone `aria-busy="true"` y un texto o ícono de carga
- **WHEN** la petición finaliza
- **THEN** `aria-busy` vuelve a `false` o se elimina

#### Scenario: Íconos accesibles

- **WHEN** un ícono es decorativo
- **THEN** se emite con `aria-hidden="true"` y sin texto alternativo redundante
- **WHEN** un ícono transmite información sin texto adyacente
- **THEN** tiene un nombre accesible mediante `aria-label` o `<title>`

#### Scenario: Estado no dependiente del color

- **WHEN** se muestra el estado de un partido, un saldo o una notificación
- **THEN** el estado incluye texto o un ícono con nombre accesible además del color
