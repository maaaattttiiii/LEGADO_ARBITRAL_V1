# Períodos contables, cierre y reapertura

## Purpose

Esta capacidad define el mes contable de la tesorería, impide operar sobre períodos cerrados y regula la corrección controlada mediante reaperturas auditadas y cierres en lote. Fija además qué operaciones quedan bloqueadas por un cierre y cómo se corrigen errores sin reescribir el historial. Existe para que los saldos mensuales sean estables, auditables y consistentes con la fecha local de los partidos.
Fuente: `docs/specs/v2_seguridad_auditoria.md` (F5) y `docs/dominio.md` (RN-38, RN-39, RN-40, RN-41, RN-50, §4.5).

## Requirements

### Requirement: Período contable en hora local de Argentina

El período contable de un partido SHALL calcularse con `periodo_de(partido.fecha_hora)` sobre la fecha local ART (UTC-3, offset fijo), nunca con la fecha UTC. Los movimientos, cierres, filtros y exportaciones MUST usar esa misma definición. Un período se expresa como `AAAA-MM`; un valor inválido MUST rechazarse con un error de validación y SHALL NOT producir un error 500.
Ref: RN-39.

#### Scenario: Partido de fin de mes en ART
- **WHEN** un partido ocurre el 31/10/2026 a las 23:00 ART, que en UTC es 01/11/2026 a las 02:00
- **THEN** su período contable es `2026-10` y los movimientos generados quedan en `2026-10`

#### Scenario: Partido de madrugada del día siguiente
- **WHEN** un partido ocurre el 01/11/2026 a las 00:30 ART
- **THEN** su período contable es `2026-11`

#### Scenario: Período con formato inválido
- **WHEN** se envía el período `2026-13` o `octubre` a una operación de cierre, ajuste o filtro
- **THEN** la validación devuelve un mensaje de error y no se escribe ni se modifica ningún registro

### Requirement: Cierre de período único e idempotente

`cerrar_periodo()` SHALL registrar como máximo un `CierrePeriodo` por período `AAAA-MM`, con `cerrado_en` en UTC y el `usuario_id` de quien lo ejecutó. El cierre MUST ser idempotente: si el período ya tiene un cierre vigente, un segundo intento MUST fallar con `PeriodoYaCerrado` sin duplicar la fila, sin reescribir la existente y sin auditar dos veces el mismo cierre.
Ref: RN-38, RN-41.

#### Scenario: Primer cierre
- **WHEN** se cierra el período `2026-03` que estaba abierto
- **THEN** se crea una única fila `CierrePeriodo` para `2026-03` con `cerrado_en` en UTC y el usuario del tesorero

#### Scenario: Segundo cierre del mismo período
- **WHEN** se intenta cerrar nuevamente `2026-03`, que ya tiene un cierre vigente
- **THEN** la operación falla con `PeriodoYaCerrado` y sigue existiendo una sola fila para `2026-03`

#### Scenario: Unicidad por período
- **WHEN** la base ya contiene un `CierrePeriodo` para `2026-03`
- **THEN** cualquier intento de insertar otra fila con el mismo período es rechazado por la restricción única

### Requirement: Bloqueo de operaciones sobre períodos cerrados

Con un período cerrado y vigente, `validar_abierto()` MUST hacer fallar con `PeriodoCerrado` las altas de partidos, las asignaciones de terna, las liquidaciones, los registros de cobro municipal y los ajustes manuales cuyo período coincida con el cerrado. La validación MUST ejecutarse antes de cualquier escritura y el intento SHALL NOT crear movimientos, cambiar estados ni alterar el partido. Consultar y exportar un período cerrado SHALL seguir permitido.
Ref: RN-38, RN-41.

#### Scenario: Alta de partido en mes cerrado
- **WHEN** el período `2026-03` está cerrado y se intenta crear un partido con fecha 15/03/2026
- **THEN** la operación falla con `PeriodoCerrado` y no se inserta el partido

#### Scenario: Liquidación en mes cerrado
- **WHEN** el período `2026-03` está cerrado y se intenta liquidar un partido de marzo
- **THEN** la operación falla con `PeriodoCerrado`, no se crean movimientos y el partido conserva su estado

#### Scenario: Cobro y ajuste en mes cerrado
- **WHEN** el período `2026-03` está cerrado y se intenta registrar un cobro municipal o un ajuste con período `2026-03`
- **THEN** ambas operaciones fallan con `PeriodoCerrado` y no se escribe ningún movimiento

#### Scenario: Consulta y exportación permitidas
- **WHEN** el tesorero consulta el panel o exporta la liquidación de `2026-03` estando el período cerrado
- **THEN** la consulta y la exportación responden con los datos existentes sin modificar nada

### Requirement: Contrato HTTP del cierre individual

`POST /tesoreria/cierre-periodo` SHALL recibir el campo `periodo` y exigir rol de tesorero. Con un período válido y abierto MUST responder 303 al panel con un aviso de éxito. Con un período inválido o ausente MUST responder 400 re-renderizando el panel con el mensaje de error. Si el período ya estaba cerrado MUST responder 200 con el aviso, sin duplicar el registro; sin sesión MUST responder 303 a `/login` y con rol `ARBITRO` MUST responder 403.
Ref: RN-38, RN-41, §4.5.

#### Scenario: Cierre exitoso por HTTP
- **WHEN** el tesorero envía `POST /tesoreria/cierre-periodo` con `periodo=2026-03` abierto
- **THEN** la respuesta es 303 a `/tesoreria` con el aviso de período cerrado

#### Scenario: Cierre con período inválido
- **WHEN** el tesorero envía `POST /tesoreria/cierre-periodo` con `periodo=2026-13`
- **THEN** la respuesta es 400 con el mensaje de validación y no se crea ningún cierre

#### Scenario: Cierre de un período ya cerrado
- **WHEN** el tesorero envía `POST /tesoreria/cierre-periodo` para un período con cierre vigente
- **THEN** la respuesta es 200 con el aviso de que ya estaba cerrado, sin duplicar la fila ni la auditoría

#### Scenario: Acceso al cierre según rol
- **WHEN** un cliente anónimo envía `POST /tesoreria/cierre-periodo`
- **THEN** la respuesta es 303 a `/login` con la ruta pedida
- **WHEN** un usuario con rol `ARBITRO` envía `POST /tesoreria/cierre-periodo`
- **THEN** la respuesta es 403 y no se cierra el período

### Requirement: Correcciones retroactivas sin reescribir el historial

El sistema SHALL NOT editar ni borrar movimientos históricos. La corrección por defecto de un mes cerrado MUST canalizarse como un movimiento de `AJUSTE` en el período abierto. Si la corrección exige operar sobre el mes cerrado, por ejemplo liquidar un partido olvidado, el tesorero MUST reabrir el período con motivo, realizar la operación y volver a cerrarlo; la reapertura SHALL NOT modificar los movimientos ya registrados.
Ref: RN-40, RN-41.

#### Scenario: Corrección habitual en período abierto
- **WHEN** se detecta un error de un mes cerrado y el tesorero carga un `AJUSTE` con período del mes abierto
- **THEN** se crea un movimiento nuevo en el período abierto y los movimientos del mes cerrado quedan intactos

#### Scenario: Operación impostergable sobre el mes cerrado
- **WHEN** hay que liquidar un partido olvidado de marzo y el período está cerrado
- **THEN** el tesorero reabre marzo con motivo, liquida el partido y vuelve a cerrar, sin editar ni borrar movimientos previos

#### Scenario: Intento de ajuste en el mes cerrado
- **WHEN** el tesorero intenta cargar un ajuste con período de un mes cerrado
- **THEN** la operación falla con `PeriodoCerrado` y el historial no cambia

### Requirement: Reapertura auditada de un período

`CierrePeriodo.reabierto_en` SHALL ser nullable: `NULL` es cierre vigente y una fecha indica período habilitado. `reabrir_periodo()` MUST exigir un cierre vigente y un motivo de al menos 10 caracteres sin contar espacios; si no está cerrado, ya fue reabierto o el motivo es corto MUST fallar sin escribir. La reapertura válida MUST marcar `reabierto_en`, auditar `REAPERTURA` y habilitar las operaciones del mes; un nuevo cierre MUST reutilizar la misma fila.
Ref: F5, RN-50, RN-41.

#### Scenario: Reapertura exitosa
- **WHEN** el período `2026-03` está cerrado y el tesorero lo reabre con un motivo de 10 o más caracteres
- **THEN** `reabierto_en` queda seteado, se audita `REAPERTURA` con motivo y usuario, y se puede crear un partido de marzo

#### Scenario: Reapertura de un período abierto
- **WHEN** se intenta reabrir un período que no tiene cierre vigente
- **THEN** la operación falla con `PeriodoNoCerrado` y no se escribe nada

#### Scenario: Reapertura de un período ya reabierto
- **WHEN** se intenta reabrir un período cuyo cierre ya tiene `reabierto_en` seteado
- **THEN** la operación falla con `PeriodoNoCerrado` y no se escribe nada

#### Scenario: Motivo insuficiente
- **WHEN** se intenta reabrir con un motivo de 9 caracteres o con espacios en blanco únicamente
- **THEN** la operación falla con `ReaperturaInvalida`, no se marca `reabierto_en` y no se audita nada

#### Scenario: Ciclo cierre, reapertura y nuevo cierre
- **WHEN** un período reabierto se vuelve a cerrar
- **THEN** se reactiva la misma fila de `CierrePeriodo`, `reabierto_en` vuelve a `NULL` y se audita un nuevo `CIERRE`

#### Scenario: Operaciones habilitadas tras la reapertura
- **WHEN** el período `2026-03` fue reabierto y el tesorero liquida un partido de marzo
- **THEN** `validar_abierto()` permite la liquidación y los movimientos se crean en `2026-03`

### Requirement: Contrato HTTP de la reapertura

`POST /tesoreria/reapertura` SHALL recibir `periodo` y `motivo`, y MUST ser exclusivo del tesorero. Con datos válidos MUST responder 303 con un aviso de éxito. Con período no cerrado, ya reabierto o motivo de menos de 10 caracteres MUST responder 400 re-renderizando el panel con el mensaje y sin escrituras. Sin sesión MUST responder 303 a `/login` y con rol `ARBITRO` MUST responder 403.
Ref: F5, RN-50.

#### Scenario: Reapertura exitosa por HTTP
- **WHEN** el tesorero envía `POST /tesoreria/reapertura` con `periodo=2026-03` y un motivo válido
- **THEN** la respuesta es 303 al panel con el aviso de período reabierto y la operación queda auditada

#### Scenario: Reapertura inválida por HTTP
- **WHEN** el tesorero envía `POST /tesoreria/reapertura` con un período abierto, ya reabierto o un motivo de 9 caracteres
- **THEN** la respuesta es 400 con el mensaje correspondiente y no se escribe ni se modifica ningún registro

#### Scenario: Reapertura solo para tesorero
- **WHEN** un cliente anónimo envía `POST /tesoreria/reapertura`
- **THEN** la respuesta es 303 a `/login` con la ruta pedida
- **WHEN** un usuario con rol `ARBITRO` envía `POST /tesoreria/reapertura`
- **THEN** la respuesta es 403 y el período no se reabre

### Requirement: Cierre en lote validado y atómico

`cerrar_periodos()` SHALL aceptar períodos como texto separado por coma, punto y coma o espacios, o como lista o tupla, y MUST validar todos antes de escribir: formato, lista no vacía, sin repetidos y ninguno con cierre vigente. Si algo falla MUST fallar con `CierreInvalido` o `PeriodoYaCerrado` y dejar cero cambios; si todo es válido MUST cerrarlos en una sola transacción con su auditoría.
Ref: F5, RN-50.

#### Scenario: Cierre conjunto de dos períodos
- **WHEN** `2026-01` y `2026-02` están abiertos y se cierran juntos
- **THEN** ambos quedan cerrados y auditados en una sola operación

#### Scenario: Separadores mixtos
- **WHEN** se envían los períodos `2026-01;2026-02 2026-03`
- **THEN** los tres se normalizan y se cierran

#### Scenario: Un período inválido invalida el lote
- **WHEN** se intenta cerrar `[2026-01, 2026-13, 2026-02]`
- **THEN** la operación falla con `CierreInvalido` y los tres períodos siguen abiertos

#### Scenario: Períodos repetidos
- **WHEN** se envía `2026-01, 2026-01`
- **THEN** la operación falla sin cerrar `2026-01`

#### Scenario: Lote vacío
- **WHEN** se envía una cadena vacía o solo separadores
- **THEN** la operación falla con `CierreInvalido` y no se escribe nada

#### Scenario: Un período ya cerrado invalida el lote
- **WHEN** `2026-01` está cerrado, `2026-02` está abierto y se intenta cerrar `[2026-01, 2026-02]`
- **THEN** la operación falla con `PeriodoYaCerrado` y `2026-02` sigue abierto

### Requirement: Contrato HTTP del cierre en lote

`POST /tesoreria/cierres-lote` SHALL recibir `periodos` y MUST ser exclusivo del tesorero. Con un lote válido MUST responder 303 con el aviso de cuántos y cuáles se cerraron. Con un lote inválido, vacío o con repetidos MUST responder 400 con el mensaje; si alguno ya estaba cerrado MUST responder 200 con el aviso sin cerrar ninguno. Todo error SHALL dejar cero cambios; sin sesión MUST responder 303 a `/login` y un `ARBITRO` MUST recibir 403.
Ref: F5, RN-50.

#### Scenario: Lote exitoso por HTTP
- **WHEN** el tesorero envía `POST /tesoreria/cierres-lote` con `periodos=2026-01, 2026-02`
- **THEN** la respuesta es 303 al panel con el aviso de dos períodos cerrados y ambos quedan auditados

#### Scenario: Lote inválido por HTTP
- **WHEN** el tesorero envía `periodos=2026-13`
- **THEN** la respuesta es 400 con el mensaje de validación y no se cierra ningún período

#### Scenario: Lote con un período ya cerrado
- **WHEN** el tesorero envía un lote que incluye un período con cierre vigente
- **THEN** la respuesta es 200 con el aviso y ninguno de los períodos del lote queda cerrado por esa operación

#### Scenario: Cierre en lote solo para tesorero
- **WHEN** un cliente anónimo envía `POST /tesoreria/cierres-lote`
- **THEN** la respuesta es 303 a `/login` con la ruta pedida
- **WHEN** un usuario con rol `ARBITRO` envía `POST /tesoreria/cierres-lote`
- **THEN** la respuesta es 403 y no se cierra ningún período

### Requirement: Estado del período reflejado en el panel

El panel de tesorería SHALL listar los períodos con cierre vigente y, cuando el filtro corresponda a uno de ellos, MUST marcarlo como **Cerrado** y deshabilitar las acciones de liquidar y registrar cobro de los partidos congelados. Un período de filtro inválido MUST mostrar el error en pantalla y listar igualmente los saldos, sin producir un error 500.
Ref: RN-38, RN-41, §4.5.

#### Scenario: Panel con período cerrado seleccionado
- **WHEN** el tesorero filtra el panel por `2026-03`, que tiene cierre vigente
- **THEN** el filtro se muestra como **Cerrado** y las acciones de liquidar y cobrar están deshabilitadas para los partidos de ese período

#### Scenario: Filtro de período inválido
- **WHEN** el tesorero abre el panel con `periodo=2026-13`
- **THEN** se muestra el mensaje de error y se listan todos los saldos, sin respuesta 500
