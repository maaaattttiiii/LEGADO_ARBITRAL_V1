# Dominio — Sistema de Gestión Colegio de Árbitros (CABM)

## 1. Propósito

Sistema interno para administrar el padrón de árbitros, la programación de partidos, las designaciones y la cuenta corriente de cada árbitro (honorarios, viáticos, adelantos y pagos).

## 2. Glosario

| Término | Significado |
|---|---|
| **Árbitro** | Persona habilitada para dirigir partidos. |
| **Legajo** | Número identificatorio interno del árbitro (único). |
| **Terna** | Conjunto de árbitros asignados a un partido (principal + asistentes). |
| **Designación** | Asignación de un árbitro a un partido en un rol determinado. |
| **Honorario** | Monto a favor del árbitro por dirigir un partido. |
| **Tarifa (arancel)** | Precio del honorario según categoría de torneo y rol, con vigencia temporal. |
| **Viático** | Reintegro de combustible: `litros_viatico` fijos de la cancha × `precio_litro` de la fecha. |
| **Cuenta corriente** | Registro cronológico de créditos y débitos de un árbitro. |
| **Saldo** | `SUM(créditos) - SUM(débitos)`. **Calculado, nunca almacenado.** |
| **Período** | Mes contable de liquidación, formato `YYYY-MM`. |

## 3. Entidades

### 3.1 `CategoriaTorneo`
Catálogo de divisiones/categorías de competencia.
`id`, `nombre` (UNIQUE), `orden`, `activo`.

Incluye las divisiones de Inferiores como categorías independientes: `U23`, `U19`, `JUVENILES`, `CADETES`, `INFANTILES`, `U11_DOBLE`, `U11`, `U9` (ver §8).

### 3.2 `Torneo`
`id`, `nombre`, `categoria_torneo_id` → `CategoriaTorneo`, `temporada`, `fecha_inicio`, `fecha_fin`, `activo`.

### 3.3 `Cancha`
`id`, `nombre`, `direccion`, `localidad`, `activo`,
`litros_viatico` (`Numeric(8,2)`, `>= 0`, default 0) — litros fijos que fija la **planilla oficial** para esa localidad. No se derivan de kilómetros ni de un rendimiento supuesto.

### 3.4 `Arbitro`
`id`, `legajo` (UNIQUE), `nombre`, `apellido`, `dni` (UNIQUE), `fecha_nacimiento`,
`email`, `telefono`, `categoria` (`CategoriaArbitro`: `CAT_A`/`CAT_A1`/`CAT_B`/`PROMOCIONAL`/`UNICA`, nullable),
`estado` (`ACTIVO`/`SUSPENDIDO`/`INACTIVO`),
`tiene_auto` (Boolean, default `false`),
`fecha_alta`, `fecha_baja`, `domicilio`, `localidad`, `observaciones`.

La `categoria` (escalafón) participa en la resolución del arancel junto con el torneo.

`tiene_auto` es una **propiedad permanente del perfil**: indica que el árbitro dispone de vehículo propio y se usa al armar las ternas. Es independiente de `Designacion.usa_auto`, que registra si en *ese* partido usó el auto (y por lo tanto cobra viático).

### 3.5 `Partido`
`id`, `torneo_id` → `Torneo`, `cancha_id` → `Cancha`, `fecha_hora` (tz-aware, UTC),
`equipo_local`, `equipo_visitante`, `estado`, `observaciones`.
La categoría del partido se obtiene vía `torneo.categoria_torneo` (no se duplica).

La UI captura fecha y hora en **hora local del club (ART, UTC-3)** y las convierte a UTC al persistir (`app/tiempo.py`). Argentina no aplica horario de verano: se usa un offset fijo.

### 3.6 `Designacion`
`id`, `partido_id` → `Partido`, `arbitro_id` → `Arbitro`, `rol`, `estado`,
`fecha_designacion`, `honorario` (snapshot `Numeric(12,2)`), `usa_auto` (Boolean, default `false`), `observaciones`.

Restricciones:
- `UNIQUE(partido_id, arbitro_id)` — un árbitro no puede estar dos veces en el mismo partido.
- `UNIQUE(partido_id, rol)` — un solo principal, un solo asistente 1, etc.
  Al pasar a `RECHAZADA` el cupo se libera (la fila se conserva como historial, por eso la unicidad se valida en el servicio, no con índice parcial en v1).

### 3.7 `MovimientoCuentaCorriente`
`id`, `arbitro_id` → `Arbitro`, `designacion_id` → `Designacion` (nullable),
`fecha`, `tipo` (`CREDITO`/`DEBITO`), `concepto`, `monto` (`Numeric(12,2)`, `> 0`), `periodo`, `descripcion`.

Restricción: `UNIQUE(designacion_id, concepto)` — como máximo un `HONORARIO` y un `VIATICO` por designación. Los movimientos manuales con `designacion_id` NULL no se ven afectados.

### 3.8 `Tarifa`
Arancel del honorario. No guarda el monto pagado: es la **fuente de verdad** de la que se resuelve el importe antes de congelarlo en la designación.
`id`, `categoria_torneo_id` → `CategoriaTorneo`, `rol` (`RolDesignacion`, nullable),
`categoria_arbitro` (`CategoriaArbitro`, nullable),
`monto_base` (`Numeric(12,2)`, `> 0`), `vigencia_desde`, `vigencia_hasta` (NULL = vigente), `descripcion`.

Semántica de las dimensiones:
- `rol = NULL` → el monto aplica a **cualquier rol de campo** (principal y asistentes).
- `categoria_arbitro = NULL` → aplica a **cualquier escalafón** (ej.: 3° juez).
- `categoria_arbitro = UNICA` → torneos con arancel único (Inferiores, Master).

Restricciones:
- `UNIQUE(categoria_torneo_id, rol, categoria_arbitro, vigencia_desde)`.
- `CHECK(monto_base > 0)`.
- `CHECK(vigencia_hasta IS NULL OR vigencia_hasta >= vigencia_desde)`.
- **Sin solapamiento** de vigencias para la misma `(categoría, rol, escalafón)`: se valida en `crear_tarifa()` (no es expresable de forma portable en SQLite).

Resolución: `resolver_tarifa(session, categoria_torneo_id, rol, categoria_arbitro, fecha)` busca por **especificidad decreciente**:

1. `(rol, escalafón)` exactos
2. `(rol, UNICA)`
3. `(rol, NULL)`
4. `(NULL, escalafón)`
5. `(NULL, UNICA)`
6. `(NULL, NULL)`

Gana la primera que exista, con la `vigencia_desde` más reciente. Sin coincidencia → `TarifaNoEncontrada`.

**`CUARTO` es especial**: solo busca aranceles de rol `CUARTO` (fijos por rol). Nunca hereda el arancel de campo, para que un 4° árbitro no cobre como principal en torneos sin cuarto (Ascenso, Promoción, Femenina).

### 3.9 `PrecioCombustible`
Precio del litro de **Nafta Infinia** con vigencias (misma mecánica que `Tarifa`).
`id`, `precio_litro` (`Numeric(12,3)`, `> 0`), `vigencia_desde`, `vigencia_hasta` (NULL = vigente), `descripcion`.

Restricciones:
- `UNIQUE(vigencia_desde)`.
- `CHECK(precio_litro > 0)`.
- `CHECK(vigencia_hasta IS NULL OR vigencia_hasta >= vigencia_desde)`.
- **Sin solapamiento** de vigencias: se valida en `crear_precio_combustible()`.

Resolución: `resolver_precio_combustible(session, fecha)` → la vigencia que contiene la fecha, ganando la más reciente. Sin coincidencia → `PrecioCombustibleNoEncontrado`.

### 3.10 `Usuario`
Credenciales de acceso al sistema (RN-42).
`id`, `email` (único, normalizado a minúsculas), `password_hash` (scrypt), `rol`, `arbitro_id` (FK opcional), `activo`.

Restricciones:
- `UNIQUE(email)`.
- `CHECK(rol IN ('TESORERO', 'ARBITRO'))`.
- `CHECK(rol <> 'ARBITRO' OR arbitro_id IS NOT NULL)`: todo usuario árbitro está vinculado a un árbitro.
- `FK(arbitro_id) ON DELETE RESTRICT`; un árbitro tiene a lo sumo un usuario (se valida en `crear_usuario()`).

La contraseña **nunca** se guarda en claro: `scrypt$n$r$p$sal$hash` con sal aleatoria de 16 bytes y comparación en tiempo constante.

## 4. Reglas de negocio

| ID | Regla |
|---|---|
| **RN-01** | Un árbitro no puede tener dos designaciones en el mismo partido. |
| **RN-02** | Un partido tiene como máximo un árbitro por rol. |
| **RN-03** | `legajo` y `dni` son únicos en todo el padrón. |
| **RN-04** | Al pasar un partido a `JUGADO`, se genera **un** movimiento de honorario por cada designación `CONFIRMADA`/`CUMPLIDA`. |
| **RN-05** | La liquidación es **idempotente**: `UNIQUE(designacion_id, concepto)` impide duplicar el honorario (y el viático). Reprocesar un partido no altera saldos. |
| **RN-06** | El `monto` del movimiento es el honorario **congelado** al momento de liquidar. Cambios posteriores en aranceles no reescriben el pasado. |
| **RN-07** | `monto` siempre positivo. La naturaleza del movimiento la expresa `tipo`. |
| **RN-08** | El saldo se calcula; no existe columna `saldo` en ninguna tabla. |
| **RN-09** | Un movimiento con `designacion_id` no nulo debe referenciar una designación del **mismo** árbitro. |
| **RN-10** | No puede haber dos tarifas con vigencias solapadas para la misma `(categoría de torneo, rol, categoría de árbitro)`. |
| **RN-11** | La tarifa se resuelve por la **fecha del partido (devengado)** y por el **escalafón del árbitro designado**, nunca por la fecha de liquidación. |
| **RN-12** | Los viáticos son movimientos independientes (`concepto=VIATICO`) del honorario. Se calculan como `cancha.litros_viatico × precio_litro` con la fecha del partido y se asignan al árbitro de la designación que declaró `usa_auto=True`. |
| **RN-13** | Solo se liquidan partidos en estado `DESIGNADO` o `JUGADO`. `PROGRAMADO`, `SUSPENDIDO` y `REPROGRAMADO` no son liquidables. |
| **RN-14** | Solo devengan honorarios las designaciones `CONFIRMADA` o `CUMPLIDA`. `AUSENTE`, `RECHAZADA` y `PROPUESTA` no cobran. |
| **RN-15** | La liquidación es **atómica**: se pre-validan todas las tarifas antes de escribir. Si falta una, no se crea ningún movimiento y el partido no cambia de estado. |
| **RN-16** | Si `designacion.honorario` ya está definido, se respeta como valor congelado y no se vuelve a resolver la tarifa. |
| **RN-17** | Como máximo **una** designación por partido puede tener `usa_auto=True`. Si hay más → `ViaticoInvalido` y cero escrituras. |
| **RN-18** | No se genera movimiento de viático si la designación no usa auto, si `cancha.litros_viatico = 0` o si el monto calculado es `0.00` (el `CHECK(monto > 0)` lo prohíbe). |
| **RN-19** | El arancel depende del **torneo y del escalafón** del árbitro. Si no hay tarifa para su escalafón se usa `UNICA`; si tampoco, la tarifa genérica del rol. |
| **RN-20** | El rol `CUARTO` cobra siempre un arancel **fijo por rol** y nunca hereda el de campo. En Ascenso, Promoción y Super Liga Femenina no se designa cuarto: no hay arancel y liquidar un `CUARTO` allí falla con `TarifaNoEncontrada`. |
| **RN-21** | **U11 depende de la cantidad de árbitros del partido**: con 1 designación elegible se paga la tarifa individual (`U11`, `$19.600`); con 2 se paga la tarifa global (`U11_DOBLE`, `$31.900`) **dividida en partes iguales** (`$15.950` cada uno). Con más de 2 → `CantidadDesignacionesInvalida` y cero escrituras. **`asignar_terna()` rechaza la tercera designación al designar** (no se llega a la liquidación) y el panel ofrece solo dos slots para U11. |
| **RN-22** | **Conflicto horario**: un árbitro no puede estar designado en dos partidos con menos de **2 horas** de diferencia, **en la misma cancha o en otra**. Un partido de básquetbol (calentamiento, entretiempo y cierre de planilla) ocupa al árbitro ~1h30; aun sin traslado no puede solapar dos partidos consecutivos. Exactamente 2 horas está permitido. Las designaciones `RECHAZADA` no bloquean. |
| **RN-23** | Una designación que ya generó movimientos **no se puede reemplazar, quitar de la terna ni cambiar su `usa_auto`**: el historial financiero es inmutable. |
| **RN-24** | Solo se admite `CUARTO` si la categoría del torneo tiene arancel `CUARTO` vigente a la fecha del partido (RN-20). Evita designar un cuarto que luego no se puede liquidar. |
| **RN-25** | Al asignar la terna, el partido pasa de `PROGRAMADO`/`REPROGRAMADO` a `DESIGNADO`. Las designaciones creadas desde el panel quedan en `CONFIRMADA` (el tesorero confirma la terna). |
| **RN-26** | **El saldo nunca se persiste**: se muestra `SUM(CREDITO) - SUM(DEBITO)`. Con filtro de período, solo se suman los movimientos de ese `periodo` (`AAAA-MM`); el panel no reinterpreta un movimiento en otro mes. |
| **RN-27** | **Signo del saldo mostrado**: positivo = la asociación le debe al árbitro (verde); negativo = el árbitro debe a la asociación (rojo); cero = sin saldo. |
| **RN-28** | **Ajustes manuales**: solo `DESCUENTO`, `ADELANTO`, `PAGO`, `MULTA` y `AJUSTE`. `HONORARIO` y `VIATICO` se generan **exclusivamente** liquidando un partido. El monto debe ser `> 0`, el período `AAAA-MM` es obligatorio y el movimiento queda sin `designacion_id`. |
| **RN-29** | **Liquidar desde el panel** es idempotente (RN-05): deja el partido en `JUGADO` y no duplica movimientos. Si la liquidación falla, no se escribe nada y el error se muestra al tesorero. |
| **RN-30** | **Retención del 10% (contabilidad uniforme)**: el club le paga el 100% del arancel al árbitro; al liquidar se acredita siempre un `CREDITO` / `HONORARIO` por el **100%** y se crea un `DEBITO` / `RETENCION` por el **10% del honorario seco**. El neto es el 90% en **ambas** modalidades. El viático **no** sufre retención (es reembolso de combustible). |
| **RN-31** | **Modalidad `DIFERIDO`** (municipio, pago a 45-90 días): cobra la asociación. Contablemente es idéntica a `EN_CANCHA` (RN-30): 100% acreditado + 10% retenido. El recibo muestra el desglose honorario / retención / neto. |
| **RN-32** | **Mora del pago diferido (> 90 días)**: se dispara cuando el tesorero registra la **fecha real de cobro municipal** (`partido.fecha_cobro`). Si `fecha_cobro - fecha_partido > 90` días, el árbitro cobra el **100%**: si el partido aún no está liquidado se **omite la retención**; si ya estaba liquidado se acredita un `CREDITO` / `AJUSTE` por lo retenido. El reintegro es idempotente (`UNIQUE(designacion_id, AJUSTE)`). |
| **RN-33** | La retención se calcula sobre el **honorario de cada designación** (incluido el reparto U11) con `ROUND_HALF_UP` y usa el honorario congelado si existe (RN-16). No se aplica retroactivamente a partidos ya liquidados. |
| **RN-34** | La **modalidad de pago es del partido** (`partido.modalidad_pago`), por defecto `EN_CANCHA`. Un mismo torneo puede mezclar partidos en cancha y diferidos. |
| **RN-35** | **ABM de aranceles**: solo se cargan **nuevas vigencias**; una tarifa existente no se edita ni se borra (historial inmutable, RN-06). |
| **RN-36** | **ABM de canchas y torneos**: alta, edición y **baja lógica** (`activo=False`). Nunca se borra físicamente un registro con historia. |
| **RN-37** | **Exportación mensual**: `GET /tesoreria/exportar?periodo=AAAA-MM&formato=csv\|pdf` genera una fila por **designación** con *Árbitro, Legajo, Partido, Rol, Honorario, Retención (10%), Viático y Neto a Cobrar* (`neto = honorario - retención + viático`) y una fila de totales. Solo considera `HONORARIO`, `RETENCION` y `VIATICO` del período: los ajustes manuales y reintegros no forman parte de la liquidación. El CSV usa `;`, decimales con coma y BOM (`utf-8-sig`) para Excel; el PDF es A4 apaisado con membrete. |
| **RN-38** | **Cierre de período**: `cerrar_periodo()` registra un `CierrePeriodo` único por `AAAA-MM`. Un período cerrado **no admite altas ni modificaciones**: crear partidos, asignar ternas, liquidar partidos, registrar cobros municipales ni cargar ajustes de ese mes. El cierre es definitivo (no hay reapertura desde la UI) e idempotente: intentar cerrarlo dos veces avisa sin duplicar el registro. |
| **RN-39** | **El período contable es la fecha local (ART)**: `partido.periodo` se calcula con `periodo_de(partido.fecha_hora)`. Un partido del 31/10 a las 23:00 ART pertenece a octubre aunque en UTC ya sea 1 de noviembre. Los cierres y los movimientos usan esa misma definición. |
| **RN-40** | **Correcciones retroactivas**: toda corrección de un mes cerrado se canaliza como movimiento de `AJUSTE` **en el período abierto**. No se reabre el período ni se editan movimientos históricos. |
| **RN-41** | El cierre **no altera** los movimientos ya registrados: solo impide operaciones nuevas (altas, liquidaciones, cobros o ajustes) con fecha/período dentro del mes cerrado. Consultar y exportar un período cerrado sigue permitido. |
| **RN-42** | **Usuarios y credenciales**: `email` único (normalizado a minúsculas), `rol` ∈ {`TESORERO`, `ARBITRO`} y `password_hash` con **scrypt** (sal aleatoria, nunca texto plano). Un usuario `ARBITRO` **debe** estar vinculado a un `arbitro_id`; un `TESORERO` no. `activo=False` impide el acceso. |
| **RN-43** | **Sesión**: `POST /login` valida email + contraseña y crea una cookie **firmada** (HMAC con `CABM_SECRET_KEY`), **HttpOnly**, `SameSite=Lax`, 8 horas. Solo guarda `usuario_id`, rol, nombre y `arbitro_id`; nunca la contraseña. Email inexistente, clave incorrecta o usuario inactivo → `401` con el mismo mensaje (no revela qué emails existen). `POST /logout` limpia la sesión. |
| **RN-44** | **Guardas por rol**: sin sesión válida → `303` a `/login?next=<ruta>`; con sesión pero rol incorrecto → `403`. Son del **tesorero**: `/arbitros`, `/partidos`, `/designaciones`, `/tesoreria` (incluye exportar y cierre), `/canchas`, `/torneos` y `/tarifas`. Son del **árbitro**: `/mis-partidos` y `/mi-cuenta`. |
| **RN-45** | **Aislamiento del portal**: `/mis-partidos` y `/mi-cuenta` filtran **siempre** por el `arbitro_id` del usuario autenticado; se ignora cualquier id que venga en la URL o query. Un árbitro no puede ver ni inferir datos de otro. |
| **RN-46** | **Revocación**: `usuario_actual()` revalida contra la base en cada request. Si el usuario fue desactivado o eliminado, la sesión se limpia y la próxima petición vuelve a pedir login. |
| **RN-47** | **Cambio de contraseña (clave inicial)**: las cuentas nacidas del seed llevan `debe_cambiar_password=True`. Mientras la marca siga activa, cualquier ruta protegida redirige a `/cambiar-password`. Cualquier usuario autenticado cambia su clave indicando la actual, la nueva y su repetición (mínimo 8 caracteres, distinta de la actual). Guardar la nueva limpia la marca y reescribe la cookie de sesión. |

### 4.1 Flujo de liquidación

`liquidar_partido(session, partido)`:

1. Valida que el partido sea liquidable (RN-13).
2. Selecciona las designaciones `CONFIRMADA` / `CUMPLIDA` (RN-14).
3. Si el torneo es `U11`, valida que haya como máximo 2 designaciones elegibles (RN-21).
4. Valida que haya como máximo una designación con `usa_auto=True` (RN-17).
5. Resuelve los honorarios con la **fecha del partido** (RN-11):
   - `U11` con 2 designaciones → `U11_DOBLE / 2` para cada una (RN-21).
   - Resto → tarifa por `(torneo, rol, escalafón)`.
   Si falta alguna → `TarifaNoEncontrada` con el detalle de la designación y cero escrituras (RN-15).
6. Si hay una designación con auto, resuelve el **precio del combustible** a la fecha del partido y calcula `litros_viatico × precio_litro` (RN-12/RN-18).
7. Crea un `MovimientoCuentaCorriente` (`CREDITO` / `HONORARIO`) por designación por el **100%** del honorario y congela `Designacion.honorario`; crea además un `DEBITO` / `RETENCION` por el 10% del honorario seco, **en ambas modalidades** (RN-30). La única excepción es un partido `DIFERIDO` en mora (> 90 días) sin liquidar: se omite la retención (RN-32).
8. Crea, si corresponde, un `MovimientoCuentaCorriente` (`CREDITO` / `VIATICO`) para la designación con auto. El viático nunca se retiene.
9. Pasa el partido a `JUGADO`.
10. Es idempotente por `UNIQUE(designacion_id, concepto)` (RN-05).
11. No hace `commit`: la transacción pertenece al llamador.

### 4.2 Asignación de terna

`asignar_terna(session, partido_id, principal_id, asistente_1_id, asistente_2_id, cuarto_id, auto_rol)`:

1. El partido debe existir y estar en `PROGRAMADO`, `DESIGNADO` o `REPROGRAMADO`.
2. Debe haber al menos un árbitro asignado (los roles vacíos son válidos: U11 puede tener 1 o 2).
3. Los árbitros deben existir y no repetirse entre roles.
4. `CUARTO` requiere arancel `CUARTO` vigente para la categoría (RN-24).
5. `auto_rol` debe ser un rol con árbitro asignado (RN-17: un solo auto por partido).
6. Sin conflictos horarios (RN-22): menos de 2 horas de diferencia, sin importar la cancha.
7. Roles con árbitro: se crean o actualizan. Roles que quedan vacíos: se eliminan.
   Si la designación ya tiene movimientos → `DesignacionLiquidada` y cero cambios (RN-23).
8. El partido pasa a `DESIGNADO` y las designaciones nuevas nacen en `CONFIRMADA` (RN-25).
9. No hace `commit`: la transacción pertenece al llamador.

### 4.3 Panel del Tesorero

`GET /tesoreria`:

1. Saldo por árbitro (`saldos()`), opcionalmente acotado a un `periodo` (RN-26).
2. Verde si el saldo es positivo, rojo si es negativo (RN-27).
3. Detalle de movimientos por árbitro en `GET /tesoreria/arbitros/{id}`.
4. Partidos en `DESIGNADO` con acción **Liquidar** (`POST /tesoreria/liquidar-partido/{id}`), que delega en `liquidar_partido()` (RN-29).
5. Ajustes manuales (`POST /tesoreria/ajuste`) restringidos por RN-28.
6. Registro de la fecha real de cobro municipal (`POST /tesoreria/cobro/{partido_id}`) para los partidos `DIFERIDO`: informa los días transcurridos, si están en mora y cuántos reintegros generó (RN-32).
7. Descargas de la liquidación mensual en CSV y PDF (RN-37).

Un período inválido no rompe la pantalla: se muestra el error y se listan todos los saldos.

### 4.4 Exportación mensual

`GET /tesoreria/exportar?periodo=AAAA-MM&formato=csv|pdf`:

1. El `periodo` es obligatorio y se normaliza (`AAAA-MM`); inválido → `400`. `formato` distinto de `csv`/`pdf` → `400`.
2. `liquidacion_mensual()` agrupa los movimientos del período por designación (`HONORARIO`, `RETENCION`, `VIATICO`) y ordena por apellido y nombre **ignorando tildes** (SQLite ordena por bytes).
3. `liquidacion_csv()` emite BOM + `;` + decimales con coma + fila `TOTAL`.
4. `liquidacion_pdf()` emite A4 apaisado con membrete, encabezado repetido por página y nota al pie con la fórmula del neto.
5. La respuesta lleva `Content-Disposition: attachment; filename="liquidacion-AAAA-MM.csv|pdf"`.

### 4.5 Cierre de período

`POST /tesoreria/cierre-periodo` con `periodo=AAAA-MM`:

1. Normaliza el período; si es inválido → `400` con mensaje.
2. Si el período ya estaba cerrado → aviso (`200`), sin duplicar el registro (RN-38).
3. Crea el `CierrePeriodo` con `cerrado_en` en UTC.
4. Desde ese momento `validar_abierto()` bloquea (`PeriodoCerrado`):
   - `crear_partido()` (período del partido en ART, RN-39),
   - `asignar_terna()` del partido,
   - `liquidar_partido()`,
   - `registrar_cobro()`,
   - `crear_ajuste()` con ese período.
5. El panel muestra los cierres, marca el filtro como **Cerrado** y deshabilita los botones de liquidar y registrar cobro de los partidos congelados.
6. Las correcciones se registran como `AJUSTE` en el período abierto (RN-40). El cierre no borra ni reescribe nada (RN-41).

### 4.6 Autenticación y control de acceso

`GET /login`, `POST /login` (`email`, `password`, `next`) y `POST /logout`:

1. `autenticar()` normaliza el email, verifica el hash scrypt y exige `activo=True`. Ante cualquier falla responde `401` con el mismo mensaje (RN-43).
2. Éxito → `request.session.clear()` (evita fijación de sesión) y guarda `usuario_id`, `rol`, `nombre` y `arbitro_id`; redirige a `next` **solo si es una ruta interna** (`destino_seguro`, rechaza `//` y URLs absolutas) o al inicio del rol: `/tesoreria` (tesorero) o `/mis-partidos` (árbitro).
3. `/logout` limpia la sesión y redirige a `/login`.
4. Las guardas son dependencias FastAPI: `requiere_tesorero` y `requiere_arbitro`. `NoAutenticado` se traduce en `303` al login conservando la ruta pedida; `AccesoDenegado` se traduce en `403`.
5. El portal del árbitro nunca recibe un `arbitro_id` por parámetro: lo toma del usuario autenticado (RN-45).
6. Si `usuario.debe_cambiar_password` es verdadero, las guardas de rol lanzan `CambioPasswordRequerido` (303 a `/cambiar-password`) y el login también redirige allí. El formulario pide actual + nueva + repetición, valida con `cambiar_password()` y, al guardar, limpia la marca en la base y en la sesión (RN-47).

## 5. Estados

```
Partido:      PROGRAMADO ──▶ DESIGNADO ──▶ JUGADO
                   │             │
                   └──▶ SUSPENDIDO ◀──┘        REPROGRAMADO (vuelve a PROGRAMADO)

Designacion:  PROPUESTA ──▶ CONFIRMADA ──▶ CUMPLIDA
                   │             └──────▶ AUSENTE
                   └──▶ RECHAZADA
```

## 6. Decisiones de arquitectura

| ID | Decisión | Motivo |
|---|---|---|
| ADR-01 | Movimiento generado al pasar a `JUGADO`, no al designar | Evita liquidar partidos que no se jugaron. |
| ADR-02 | Snapshot del honorario en designación/movimiento | Inmutabilidad del historial financiero. |
| ADR-03 | `tipo` CREDITO/DEBITO + `monto` positivo | Legibilidad y auditoría contable. |
| ADR-04 | SQLite dev / PostgreSQL prod, `native_enum=False` | Portabilidad sin migraciones de tipos. |
| ADR-05 | Nombres de dominio en español | El vocabulario del negocio es local; evita traducciones ambiguas. |
| ADR-06 | `Torneo`, `Cancha`, `CategoriaTorneo` como tablas desde v1 | Evita strings duplicados y normaliza reportes. |
| ADR-07 | Saldo calculado, nunca almacenado | Elimina la clase de bug #1 de cuentas corrientes (deriva). |
| ADR-08 | Tarifas con vigencias (`desde`/`hasta`), no un flag `vigente` | Permite cambiar precios sin reescribir el historial; el solapamiento se valida en el servicio. |
| ADR-09 | Pre-validación en seco antes de escribir movimientos | Garantiza atomicidad sin depender de rollbacks parciales ni de savepoints. |
| ADR-10 | Sesión firmada (`SessionMiddleware`) + scrypt de la stdlib | Cookie HttpOnly sin datos sensibles y hashing sin dependencias nuevas (bcrypt/passlib dan problemas con Python 3.14). |

## 7. Preguntas abiertas

1. **Escala de categorías de árbitro**: ~~¿A/B/C...?~~ **Resuelto**: enum `CategoriaArbitro` = `CAT_A`, `CAT_A1`, `CAT_B`, `PROMOCIONAL`, `UNICA`.
2. ~~**Tabla de aranceles**~~ **Resuelto**: `Tarifa` con `(categoría de torneo, rol, escalafón, vigencias)`.
3. ~~**Viáticos**~~ **Resuelto**: la planilla oficial fija **litros por localidad**; el viático es `litros_viatico × precio_litro`. No interviene ningún rendimiento. Valores cargados por `app/seeds/datos_iniciales.py` (ver §8).
4. **Signo del saldo**: ¿saldo positivo = a favor del árbitro (acreedor) o de la institución? Se asume **a favor del árbitro**.
5. **Cierre de período**: ~~¿una liquidación bloquea el período para nuevas cargas?~~ **Resuelto (RN-38 a RN-41)**: el cierre es explícito (`POST /tesoreria/cierre-periodo`) y bloquea altas, designaciones, liquidaciones, cobros y ajustes del mes; las correcciones van como `AJUSTE` en el período abierto.
6. ~~**Aranceles oficiales**~~ **Resuelto**: 26 aranceles cargados (ver §8).
7. ~~**Asistentes**~~ **Resuelto**: principal y asistentes cobran según su **escalafón**; la planilla no distingue por rol de campo.
8. ~~**Retención del 10% "En Cancha"**~~ **Resuelto (RN-30 a RN-34)**: contabilidad uniforme — siempre 100% acreditado + 10% retenido, en ambas modalidades. La mora superior a 90 días se detecta al registrar la fecha de cobro municipal y reintegra lo retenido automáticamente (RN-32).
9. ~~**Acceso al sistema**~~ **Resuelto (RN-42 a RN-46)**: dos roles (`TESORERO` administra todo, `ARBITRO` solo su portal), sesión firmada HttpOnly y contraseñas con scrypt. Queda como pendiente de producción cambiar las claves iniciales del seed y definir `CABM_SECRET_KEY`.

## 8. Datos iniciales (planilla oficial CABM — Octubre 2026)

Cargados por `app/seeds/datos_iniciales.py` (idempotente):

```powershell
& C:\Python314\python.exe -m app.seeds.datos_iniciales
```

**Combustible**: Nafta Infinia `$2.361,00`/litro desde `2026-10-13`.

| Localidad | Litros | Viático |
|---|---:|---:|
| La Paz | 39 | 92.079,00 |
| San Carlos | 27 | 63.747,00 |
| Tunuyán | 24 | 56.664,00 |
| Tupungato | 24 | 56.664,00 |
| Rivadavia | 18 | 42.498,00 |
| Junín | 16 | 37.776,00 |
| Barriales | 16 | 37.776,00 |
| San Martín | 14 | 33.054,00 |
| Lavalle | 8 | 18.888,00 |
| Luján | 5 | 11.805,00 |
| Maipú | 5 | 11.805,00 |

**Categorías de torneo** (13): Super Liga, Ascenso, Promoción, Super Liga Femenina, U23, U19, JUVENILES, CADETES, INFANTILES, U11_DOBLE, U11, U9, Master.

**Aranceles** (vigencia `2026-10-01`, 26 filas). `rol = –` significa "cualquier rol de campo":

| Torneo | Rol | Escalafón | Monto |
|---|---|---|---:|
| Super Liga | – | CAT_A | 73.100,00 |
| Super Liga | – | CAT_A1 | 61.200,00 |
| Super Liga | – | CAT_B | 53.100,00 |
| Super Liga | – | PROMOCIONAL | 53.100,00 |
| Super Liga | CUARTO | – | 30.700,00 |
| Ascenso | – | CAT_A | 52.500,00 |
| Ascenso | – | CAT_A1 | 44.500,00 |
| Ascenso | – | CAT_B | 40.300,00 |
| Ascenso | – | PROMOCIONAL | 40.300,00 |
| Promoción | – | CAT_A | 42.300,00 |
| Promoción | – | CAT_A1 | 41.400,00 |
| Promoción | – | CAT_B | 38.500,00 |
| Promoción | – | PROMOCIONAL | 38.500,00 |
| Super Liga Femenina | – | CAT_A | 45.400,00 |
| Super Liga Femenina | – | CAT_A1 | 44.500,00 |
| Super Liga Femenina | – | CAT_B | 40.300,00 |
| Super Liga Femenina | – | PROMOCIONAL | 40.300,00 |
| U23 | – | UNICA | 38.700,00 |
| U19 | – | UNICA | 31.600,00 |
| JUVENILES | – | UNICA | 28.200,00 |
| CADETES | – | UNICA | 25.900,00 |
| INFANTILES | – | UNICA | 24.600,00 |
| U11_DOBLE | – | UNICA | 31.900,00 |
| U11 | – | UNICA | 19.600,00 |
| U9 | – | UNICA | 19.600,00 |
| Master | – | UNICA | 52.500,00 |

**Regla U11** (RN-21): 1 árbitro → `$19.600`; 2 árbitros → `$31.900` repartidos `$15.950` cada uno. `U11_DOBLE` no es otra categoría de torneo a designar: es el arancel global que usa la liquidación cuando el partido U11 tiene dos árbitros.
