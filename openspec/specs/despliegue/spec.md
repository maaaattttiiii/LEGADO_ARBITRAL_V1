# Despliegue con Docker y PostgreSQL

## Purpose

Esta capacidad describe cómo se empaqueta y opera la aplicación en producción: imagen Docker sin privilegios, PostgreSQL 17, migraciones automáticas al arrancar, configuración por variables de entorno, healthcheck, backups y límites operativos conocidos. También reúne los requisitos no funcionales transversales que hacen verificable una entrega en producción. Existe para que el sistema pueda desplegarse de forma reproducible y segura fuera del entorno de desarrollo SQLite.
Fuente: `docs/specs/v2_seguridad_auditoria.md` (F4, §7, §9) y `docs/despliegue.md`; `docs/dominio.md` (RN-43, RN-48).

## Requirements

### Requirement: Imagen de producción sin privilegios

El `Dockerfile` SHALL construirse sobre `python:3.14-slim`, instalar las dependencias de `requirements.txt` e incluir la aplicación y las migraciones de Alembic. El contenedor MUST ejecutarse como el usuario sin privilegios `cabm`, y `.dockerignore` MUST excluir `.env`, archivos `*.db`, `tests/` y demás datos locales para que no entren en la imagen.
Ref: F4, RF-4.1, RF-4.6.

#### Scenario: Usuario sin privilegios
- **WHEN** se inspecciona la imagen construida
- **THEN** el proceso de la aplicación corre como el usuario `cabm` y no como `root`

#### Scenario: Datos locales fuera de la imagen
- **WHEN** existe un `.env` o un archivo `cabm.db` en el contexto de build
- **THEN** la imagen no los incluye y el contenedor no depende de ellos para arrancar

#### Scenario: Dependencias instaladas desde requirements
- **WHEN** se construye la imagen
- **THEN** las dependencias se instalan desde `requirements.txt` y la aplicación y `alembic/` quedan copiadas en la imagen

### Requirement: Migraciones automáticas antes de arrancar

El contenedor SHALL ejecutar `alembic upgrade head` antes de iniciar `uvicorn`, de modo que el esquema quede al día en cada arranque. La aplicación MUST escuchar en `0.0.0.0` y el puerto publicado SHALL configurarse con `CABM_PORT`, por defecto 8000.
Ref: F4, RF-4.2.

#### Scenario: Orden de arranque
- **WHEN** se inicia el contenedor de la aplicación
- **THEN** `alembic upgrade head` se ejecuta antes de `uvicorn app.main:app` y el servidor queda escuchando en `0.0.0.0`

#### Scenario: Puerto configurable
- **WHEN** se define `CABM_PORT=8080`
- **THEN** el puerto 8080 del host se publica contra el puerto 8000 del contenedor

### Requirement: Healthcheck sobre una ruta pública

La imagen SHALL declarar un `HEALTHCHECK` que consulte `/login`, ruta pública que no exige sesión. El contenedor MUST considerarse saludable cuando `/login` responde 200 con la base migrada, y el healthcheck SHALL NOT depender de una ruta protegida ni de credenciales.
Ref: F4, RF-4.3.

#### Scenario: Contenedor saludable
- **WHEN** la base está migrada y la aplicación responde 200 en `/login`
- **THEN** el `HEALTHCHECK` marca el contenedor como saludable

#### Scenario: Aplicación no disponible
- **WHEN** `/login` no responde o responde con error
- **THEN** el `HEALTHCHECK` falla y el orquestador puede reiniciar o marcar el contenedor como no saludable

### Requirement: PostgreSQL 17 con arranque ordenado

`docker-compose.yml` SHALL definir un servicio `db` con PostgreSQL 17 y un healthcheck basado en `pg_isready`, persistencia en el volumen `cabm_pgdata` y un servicio `app` que dependa de `db` con `condition: service_healthy`. La aplicación MUST conectarse mediante una `DATABASE_URL` con el driver `psycopg` y el host interno `db`.
Ref: F4, RF-4.4, RF-4.5.

#### Scenario: Arranque limpio con volumen vacío
- **WHEN** se levanta `docker compose` con un volumen PostgreSQL vacío
- **THEN** `db` supera `pg_isready`, `app` espera `service_healthy`, Alembic aplica todas las migraciones y `/login` responde 200

#### Scenario: Persistencia de datos
- **WHEN** se reinicia el servicio `db`
- **THEN** los datos se conservan en el volumen `cabm_pgdata`

#### Scenario: Conexión a PostgreSQL
- **WHEN** la aplicación arranca en Compose
- **THEN** usa una `DATABASE_URL` con prefijo `postgresql+psycopg://` apuntando al servicio `db` en el puerto 5432

### Requirement: Variables de entorno obligatorias y valores por defecto

La configuración SHALL provenir de variables de entorno. `DATABASE_URL` y `CABM_SECRET_KEY` MUST ser obligatorias: si falta `CABM_SECRET_KEY` o `POSTGRES_PASSWORD`, Compose MUST fallar antes de arrancar, y sin `DATABASE_URL` la aplicación MUST fallar al iniciar. `CABM_HTTPS_ONLY` SHALL valer 1 por defecto en Compose y `CABM_PORT` SHALL configurar el puerto publicado. `.env.example` MUST documentarlas y explicar `openssl rand -hex 32`.
Ref: F4, RF-4.5, RF-4.6, RN-43.

#### Scenario: Falta la clave del secreto
- **WHEN** se ejecuta Compose sin `CABM_SECRET_KEY`
- **THEN** Compose falla explícitamente antes de arrancar la aplicación

#### Scenario: Falta la clave de PostgreSQL
- **WHEN** se ejecuta Compose sin `POSTGRES_PASSWORD`
- **THEN** Compose falla explícitamente antes de arrancar la aplicación

#### Scenario: Defaults documentados
- **WHEN** se revisa `.env.example`
- **THEN** aparecen `POSTGRES_PASSWORD`, `CABM_SECRET_KEY`, `CABM_HTTPS_ONLY` y `CABM_PORT`, junto con la instrucción `openssl rand -hex 32`

#### Scenario: Secreto efímero fuera de producción
- **WHEN** la aplicación se ejecuta sin `CABM_SECRET_KEY` en un entorno de desarrollo
- **THEN** usa un secreto efímero por proceso, de modo que las sesiones se invalidan al reiniciar

### Requirement: TLS y cookie Secure

Con `CABM_HTTPS_ONLY=1` la cookie de sesión SHALL marcarse como `Secure` y el despliegue MUST asumir que un proxy inverso termina TLS delante del contenedor. Sin ese proxy el navegador MUST NOT enviar la cookie y el login no persistirá, por lo que la documentación SHALL advertirlo. Para pruebas locales por HTTP MUST usarse `CABM_HTTPS_ONLY=0`.
Ref: F4, RN-43, `docs/despliegue.md` §TLS.

#### Scenario: Producción detrás de TLS
- **WHEN** `CABM_HTTPS_ONLY=1` y la aplicación está detrás de un proxy con TLS
- **THEN** la cookie de sesión se emite con el atributo `Secure` y el navegador la envía por HTTPS

#### Scenario: HTTP local
- **WHEN** se prueba localmente por HTTP con `CABM_HTTPS_ONLY=0`
- **THEN** la cookie no exige `Secure` y el login persiste en el navegador

#### Scenario: HTTPS_ONLY sin proxy
- **WHEN** se usa `CABM_HTTPS_ONLY=1` sin un proxy que termine TLS
- **THEN** el navegador no envía la cookie y el login no persiste, tal como advierte la documentación

### Requirement: Backup, restauración y rotación del secreto

La documentación de despliegue SHALL describir el arranque, la ejecución de migraciones, el backup y la restauración de PostgreSQL y la rotación de `CABM_SECRET_KEY`. El backup MUST poder realizarse con `pg_dump -Fc` y la restauración con `pg_restore --clean`, y la documentación SHALL advertir que borrar el volumen `cabm_pgdata` elimina la base. Rotar el secreto MUST invalidar las sesiones existentes.
Ref: F4, RF-4.7, RN-43.

#### Scenario: Backup y restauración
- **WHEN** se ejecuta `pg_dump -Fc` sobre la base `cabm` y luego `pg_restore --clean` sobre una base limpia
- **THEN** el esquema y los datos se restauran y la aplicación vuelve a responder en `/login`

#### Scenario: Borrado del volumen
- **WHEN** se elimina el volumen `cabm_pgdata`
- **THEN** la base de datos se pierde, conforme a la advertencia documentada

#### Scenario: Rotación del secreto
- **WHEN** se cambia `CABM_SECRET_KEY` y se reinicia la aplicación
- **THEN** las cookies emitidas con el secreto anterior dejan de ser válidas y los usuarios deben volver a iniciar sesión

### Requirement: Calidad verificable de la entrega

Antes de cada entrega la suite completa SHALL estar en verde, con 401 tests en la versión V2.0, y `alembic check` MUST informar que no hay diferencias entre los modelos y el esquema. Toda migración SHALL implementar `downgrade` y MUST poder recorrerse en ambos sentidos sin dejar el esquema inconsistente.
Ref: F4, RNF-1, RNF-2, RNF-5.

#### Scenario: Suite completa en verde
- **WHEN** se ejecuta la suite de tests antes de un commit
- **THEN** los 401 tests pasan y no hay fallos pendientes

#### Scenario: Modelos y esquema alineados
- **WHEN** se ejecuta `alembic check`
- **THEN** no se detectan diferencias entre los modelos y la base migrada

#### Scenario: Migración reversible
- **WHEN** se ejecuta `alembic upgrade head` y luego `alembic downgrade` sobre una migración que implementa su reverso
- **THEN** el esquema vuelve al estado anterior sin errores y puede volver a migrarse hacia adelante

### Requirement: Errores esperados sin 500 y sin secretos expuestos

Los errores de validación esperados SHALL resolverse con respuestas controladas (200 de re-render, 303, 400, 401, 403 o 429 según corresponda) y MUST NOT producir un error 500. Ninguna respuesta, log, HTML o query string SHALL contener claves, hashes, tokens ni secretos de configuración.
Ref: F4, RNF-3, RNF-4.

#### Scenario: Validación esperada
- **WHEN** se envía un formulario con datos inválidos en una ruta de tesorería o autenticación
- **THEN** la respuesta es 400, 401 o 429 con un mensaje, nunca 500

#### Scenario: Sin secretos en la salida
- **WHEN** se revisan las respuestas y los logs de login, cierre o despliegue
- **THEN** no aparecen claves, hashes, `CABM_SECRET_KEY` ni tokens en HTML, logs o query strings

### Requirement: Compatibilidad entre SQLite y PostgreSQL

La aplicación SHALL funcionar con SQLite en desarrollo y tests y con PostgreSQL en producción. El esquema MUST usar construcciones portables: enums como `VARCHAR` con `CHECK` explícito, alteraciones de tabla por lotes en las migraciones y claves foráneas explícitas, de modo que la misma suite y las mismas migraciones se comporten igual en ambos motores.
Ref: F4, RNF-6, §9.

#### Scenario: Suite sobre SQLite
- **WHEN** se ejecuta la suite de tests en desarrollo
- **THEN** todos los tests pasan sobre SQLite sin depender de tipos nativos exclusivos de PostgreSQL

#### Scenario: Producción sobre PostgreSQL
- **WHEN** se levanta la aplicación con PostgreSQL 17 y se aplican las migraciones
- **THEN** el esquema se crea con los mismos enums, checks y claves foráneas y `/login` responde 200

### Requirement: Límites operativos documentados

La documentación SHALL declarar los límites operativos conocidos: el limitador de login vive en memoria de una sola instancia y MUST migrarse a Redis o a la base si se escala horizontalmente; un secreto efímero invalida sesiones al reiniciar; y la reapertura de períodos exige motivo y deja auditoría. El sistema MUST NOT prometer protección distribuida ni persistente del rate limiting en la versión actual.
Ref: F4, RN-48, §9.

#### Scenario: Reinicio del limitador
- **WHEN** se reinicia el proceso de la aplicación
- **THEN** los contadores y bloqueos de login en memoria se pierden y el rate limiting vuelve a empezar

#### Scenario: Varias instancias
- **WHEN** se ejecutan dos instancias de la aplicación sin Redis ni base compartida
- **THEN** cada instancia cuenta sus propios fallos y el bloqueo de una no se aplica en la otra, conforme a la deuda documentada

#### Scenario: Reapertura controlada
- **WHEN** se reabre un período
- **THEN** la operación exige motivo de al menos 10 caracteres y deja un registro append-only con el usuario y la fecha
