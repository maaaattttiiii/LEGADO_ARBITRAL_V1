# Autenticación y control de acceso

## Purpose

Esta capacidad establece la identidad de los operadores del sistema y decide qué puede hacer cada uno: administra las credenciales, la sesión firmada, las guardas por rol, el aislamiento del portal del árbitro y la obligación de cambiar la clave inicial. También protege el login contra fuerza bruta y garantiza que una cuenta desactivada pierda el acceso de inmediato. Existe porque el circuito financiero no puede operarse sin saber quién ejecuta cada acción ni sin separar al tesorero del árbitro.
Fuente: `docs/specs/v2_seguridad_auditoria.md` (F1, F2) y `docs/dominio.md` (RN-42 a RN-48, §3.10, §4.6).

## Requirements

### Requirement: Modelo de usuario y credenciales seguras

El sistema SHALL modelar `Usuario` con `email` único normalizado a minúsculas, `password_hash`, `rol` (`TESORERO` o `ARBITRO`), `arbitro_id` opcional y `activo`. Un `ARBITRO` MUST estar vinculado a un `arbitro_id` existente y un `TESORERO` MUST NOT llevarlo; cada árbitro SHALL tener a lo sumo un usuario. La contraseña SHALL guardarse solo como hash scrypt con sal y comparación en tiempo constante, y SHALL NOT almacenarse en claro.
Ref: RN-42, §3.10.

#### Scenario: Alta de árbitro sin vínculo
- **WHEN** se intenta crear un usuario con rol `ARBITRO` y `arbitro_id` nulo
- **THEN** el alta falla con un error de validación y no se inserta ninguna fila en `usuario`

#### Scenario: Email duplicado con distinto formato
- **WHEN** existe `tesorero@cabm.org.ar` y se intenta crear `Tesorero@CABM.org.ar`
- **THEN** el email se normaliza a minúsculas y el alta se rechaza sin crear un segundo usuario

#### Scenario: Segundo usuario para el mismo árbitro
- **WHEN** se intenta crear un segundo usuario vinculado a un `arbitro_id` que ya tiene uno
- **THEN** el alta se rechaza con un error de validación y se conserva un único usuario para ese árbitro

### Requirement: Sesión firmada y ciclo de vida

La sesión SHALL usar una cookie firmada con HMAC y `CABM_SECRET_KEY` llamada `cabm_session`, `HttpOnly`, `SameSite=Lax`, de 8 horas y `Secure` con `CABM_HTTPS_ONLY`. SHALL guardar solo `usuario_id`, `rol`, `nombre`, `arbitro_id` y la marca de cambio de clave, nunca la contraseña ni el hash. Antes de autenticar MUST limpiarse para evitar fijación, y `POST /logout` MUST limpiarla y redirigir a `/login`.
Ref: RN-43, RN-47.

#### Scenario: Login exitoso crea la cookie
- **WHEN** un usuario activo ingresa credenciales válidas en `POST /login`
- **THEN** la respuesta es 303 y la cookie `cabm_session` es firmada, `HttpOnly`, `SameSite=Lax`, dura 8 horas y no contiene la contraseña ni el hash

#### Scenario: Logout limpia la sesión
- **WHEN** un usuario autenticado envía `POST /logout`
- **THEN** la sesión queda vacía y la respuesta es 303 a `/login`

#### Scenario: Sesión previa descartada al autenticar
- **WHEN** un cliente con una sesión anterior inicia sesión con otro usuario
- **THEN** la sesión se limpia antes de guardar la nueva identidad y no se conservan datos del usuario previo

### Requirement: Contrato HTTP de login

`GET /login` SHALL responder 200 con el formulario. `POST /login` SHALL aceptar `email`, `password` y `next`; con credenciales válidas MUST responder 303 al destino interno o al inicio del rol (`/tesoreria` o `/mis-partidos`). Ante email inexistente, clave incorrecta o usuario inactivo MUST responder 401 con el mismo mensaje y sin sesión. `next` SHALL aceptarse solo si es ruta interna; destinos externos MUST ignorarse.
Ref: RN-43, §4.6.

#### Scenario: Formulario público
- **WHEN** se solicita `GET /login` sin sesión
- **THEN** la respuesta es 200 con el formulario de ingreso

#### Scenario: Redirección al inicio del rol
- **WHEN** un tesorero inicia sesión sin `next`
- **THEN** la respuesta es 303 a `/tesoreria`
- **WHEN** un árbitro inicia sesión sin `next`
- **THEN** la respuesta es 303 a `/mis-partidos`

#### Scenario: Destino interno respetado
- **WHEN** un tesorero inicia sesión con `next=/tesoreria?periodo=2026-10`
- **THEN** la respuesta es 303 a `/tesoreria?periodo=2026-10`

#### Scenario: Destino externo rechazado
- **WHEN** un usuario inicia sesión con `next=//ejemplo.com` o `next=https://ejemplo.com`
- **THEN** la respuesta es 303 al inicio de su rol y no al destino externo

#### Scenario: Credenciales inválidas con mensaje uniforme
- **WHEN** se envía un email inexistente, una clave incorrecta o un usuario inactivo
- **THEN** la respuesta es 401 con el mismo mensaje en los tres casos y no se crea sesión

### Requirement: Guardas por rol

Toda ruta protegida SHALL declarar su guarda como dependencia y SHALL NOT resolver permisos manualmente. Sin sesión válida MUST responder 303 a `/login?next=<ruta>` conservando ruta y query; con rol incorrecto MUST responder 403. Son del tesorero `/arbitros`, `/partidos`, `/designaciones`, `/tesoreria`, `/canchas`, `/torneos` y `/tarifas`; son del árbitro `/mis-partidos` y `/mi-cuenta`.
Ref: RN-44.

#### Scenario: Sin sesión en ruta del tesorero
- **WHEN** un cliente anónimo solicita `/tesoreria?periodo=2026-10`
- **THEN** la respuesta es 303 a `/login?next=%2Ftesoreria%3Fperiodo%3D2026-10`

#### Scenario: Árbitro en ruta del tesorero
- **WHEN** un usuario con rol `ARBITRO` solicita `/tesoreria`
- **THEN** la respuesta es 403 y no se ejecuta ninguna operación del panel

#### Scenario: Tesorero en el portal del árbitro
- **WHEN** un usuario con rol `TESORERO` solicita `/mis-partidos` o `/mi-cuenta`
- **THEN** la respuesta es 403

### Requirement: Revalidación del usuario y revocación de sesión

En cada request el sistema MUST revalidar al usuario de la sesión contra la base y SHALL considerar válida solo una cuenta existente y con `activo=True`. Si el usuario fue desactivado o eliminado, la sesión MUST limpiarse y la petición MUST responder 303 a `/login`. La marca de cambio de clave SHALL refrescarse desde la base en cada request para que un restablecimiento administrativo obligue a cambiarla también en sesiones abiertas.
Ref: RN-46, RN-47.

#### Scenario: Usuario desactivado durante la sesión
- **WHEN** un usuario autenticado es marcado `activo=False` y realiza una nueva petición
- **THEN** la sesión se limpia y la respuesta es 303 a `/login`

#### Scenario: Usuario eliminado durante la sesión
- **WHEN** un usuario autenticado fue eliminado de la base y realiza una nueva petición
- **THEN** la sesión se limpia y la respuesta es 303 a `/login`

#### Scenario: Restablecimiento administrativo de la clave
- **WHEN** la base marca `debe_cambiar_password=True` para un usuario con sesión abierta
- **THEN** la siguiente petición protegida responde 303 a `/cambiar-password`

### Requirement: Aislamiento del portal del árbitro

`/mis-partidos` y `/mi-cuenta` SHALL filtrar siempre por el `arbitro_id` del usuario autenticado. El sistema MUST NOT aceptar un `arbitro_id` por query, cuerpo o parámetro de ruta para determinar qué datos mostrar, y un árbitro SHALL NOT poder ver ni inferir datos de otro árbitro.
Ref: RN-45.

#### Scenario: Query con otro árbitro es ignorada
- **WHEN** el árbitro vinculado al id 5 solicita `/mi-cuenta?arbitro_id=9`
- **THEN** la respuesta muestra únicamente los movimientos y el saldo del árbitro 5

#### Scenario: Partidos de otro árbitro no visibles
- **WHEN** el árbitro vinculado al id 5 solicita `/mis-partidos?arbitro_id=9`
- **THEN** la respuesta lista únicamente las designaciones del árbitro 5

### Requirement: Cambio de clave inicial obligatorio

Las cuentas del seed SHALL nacer con `debe_cambiar_password=True`, y la re-siembra MUST marcar toda cuenta preexistente que conserve la clave default. Mientras la marca esté activa, cualquier ruta protegida y el login exitoso MUST responder 303 a `/cambiar-password`. Guardar la nueva clave MUST limpiar la marca en la base y en la sesión.
Ref: F1, RN-47.

#### Scenario: Primera sesión redirige al cambio
- **WHEN** un usuario con `debe_cambiar_password=True` inicia sesión con su clave provisoria
- **THEN** la respuesta es 303 a `/cambiar-password`

#### Scenario: Ruta protegida con clave pendiente
- **WHEN** el usuario autenticado con la marca activa solicita `/tesoreria`, `/partidos` o cualquier otra ruta protegida
- **THEN** la respuesta es 303 a `/cambiar-password` y no se ejecuta la operación pedida

#### Scenario: Re-siembra idempotente
- **WHEN** se ejecuta el seed sobre una cuenta existente que conserva la clave default
- **THEN** la cuenta queda con `debe_cambiar_password=True` y una segunda ejecución no duplica usuarios

### Requirement: Formulario de cambio de contraseña

`GET /cambiar-password` SHALL responder 200 con un formulario que pida clave actual, nueva y repetición cuando hay sesión, y MUST responder 303 a `/login` cuando no la hay. El formulario SHALL NOT precargar ni mostrar la clave actual ni el hash almacenado.
Ref: F1, RN-47.

#### Scenario: Formulario con sesión
- **WHEN** un usuario autenticado solicita `GET /cambiar-password`
- **THEN** la respuesta es 200 con los campos actual, nueva y repetir

#### Scenario: Formulario sin sesión
- **WHEN** un cliente anónimo solicita `GET /cambiar-password`
- **THEN** la respuesta es 303 a `/login`

### Requirement: Validación y guardado del cambio de contraseña

`POST /cambiar-password` MUST exigir que la clave actual sea correcta, que la nueva tenga al menos 8 caracteres, que difiera de la actual y que coincida con la repetición. Con datos válidos MUST guardar el nuevo hash scrypt, limpiar `debe_cambiar_password` en la base y en la sesión, y responder 303 al inicio del rol. Cualquier falla MUST responder 400 con mensaje, sin modificar la clave.
Ref: F1, RN-47.

#### Scenario: Cambio exitoso
- **WHEN** el usuario envía la clave actual correcta, una nueva de 8 o más caracteres y la repetición idéntica
- **THEN** la respuesta es 303 al inicio de su rol, la marca `debe_cambiar_password` queda en `False` en la base y en la sesión, y el `password_hash` corresponde a la nueva clave

#### Scenario: Clave actual incorrecta
- **WHEN** el usuario envía una clave actual que no coincide
- **THEN** la respuesta es 400 con mensaje y la clave almacenada no cambia

#### Scenario: Nueva clave demasiado corta
- **WHEN** el usuario envía una nueva clave de 7 caracteres o menos
- **THEN** la respuesta es 400 con mensaje y la clave almacenada no cambia

#### Scenario: Nueva clave igual a la actual
- **WHEN** el usuario envía como nueva la misma clave actual
- **THEN** la respuesta es 400 con mensaje y la clave almacenada no cambia

#### Scenario: Repetición distinta
- **WHEN** el usuario envía una nueva clave y una repetición que no coincide
- **THEN** la respuesta es 400 con mensaje y la clave almacenada no cambia

### Requirement: Rate limiting del login

El sistema SHALL contar los fallos de autenticación por par `(IP, email normalizado)` en una ventana deslizante de 15 minutos. Al llegar a 5 fallos, el par MUST quedar bloqueado 15 minutos y `POST /login` MUST responder 429 con `Retry-After` en segundos. El bloqueo SHALL consultarse antes de verificar credenciales y un login exitoso MUST limpiar el contador. El estado SHALL vivir en memoria y SHALL NOT persistirse; cada IP MUST llevar su propio conteo.
Ref: F2, RN-48.

#### Scenario: Bloqueo tras cinco fallos
- **WHEN** un par `(IP, email)` acumula 4 fallos y falla el quinto intento dentro de los 15 minutos
- **THEN** la respuesta es 429 con `Retry-After` de 900 segundos y el par queda bloqueado

#### Scenario: Clave correcta durante el bloqueo
- **WHEN** un par bloqueado intenta ingresar con la clave correcta
- **THEN** la respuesta es 429 con `Retry-After` y las credenciales no se evalúan

#### Scenario: Éxito limpia el contador
- **WHEN** un par acumuló 3 fallos y luego ingresa con la clave correcta
- **THEN** la respuesta es 303 y el contador vuelve a cero, por lo que hacen falta 5 fallos nuevos para bloquearlo

#### Scenario: Bloqueo vencido
- **WHEN** el bloqueo de 15 minutos expiró y el par reintenta
- **THEN** las credenciales se evalúan normalmente y el intento recibe 303 o 401 según corresponda

#### Scenario: Mismo email desde otra IP
- **WHEN** un email está bloqueado para una IP e intenta ingresar desde otra IP
- **THEN** el segundo par se evalúa con su propio contador y no hereda el bloqueo del primero

#### Scenario: Estado no persistido
- **WHEN** el proceso se reinicia
- **THEN** los contadores y bloqueos en memoria se pierden, porque el limitador no se guarda en la base

### Requirement: Confidencialidad de credenciales en respuestas y logs

El sistema SHALL NOT registrar claves, hashes ni tokens en logs, HTML, mensajes de error o query strings, y las respuestas de login y cambio de clave MUST NOT devolver el `password_hash` ni el valor ingresado. Los errores de autenticación SHALL ser genéricos para no revelar qué emails existen.
Ref: F1, RNF-4.

#### Scenario: Error de login sin datos sensibles
- **WHEN** se envía una clave incorrecta en `POST /login`
- **THEN** el HTML y el log de la aplicación no contienen la clave ingresada, el hash almacenado ni indicios de si el email existe

#### Scenario: Cambio de clave sin eco de valores
- **WHEN** se envía `POST /cambiar-password` con datos inválidos
- **THEN** la respuesta 400 no incluye la clave actual, la nueva ni el hash, y tampoco aparecen en la URL
