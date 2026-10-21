# Liquidación de partidos

## Purpose

Define cómo se generan los honorarios, las retenciones y los viáticos de un partido al liquidarlo, respetando el honorario congelado, el devengado por fecha del partido y la idempotencia del historial financiero. También cubre la mora del pago diferido y la atomicidad de la operación.
Fuente: `docs/dominio.md` (RN-04, RN-05, RN-06, RN-07, RN-09, RN-11, RN-12, RN-13, RN-14, RN-15, RN-16, RN-17, RN-18, RN-19, RN-20, RN-21, RN-29, RN-30, RN-31, RN-32, RN-33).

## Requirements

### Requirement: Estados del partido liquidables

La liquidación SHALL aceptar únicamente partidos en estado `DESIGNADO` o `JUGADO`. Los estados `PROGRAMADO`, `SUSPENDIDO` y `REPROGRAMADO` SHALL NOT ser liquidables.
Ref: RN-13.

#### Scenario: Partido programado no se liquida
- **WHEN** el tesorero intenta liquidar un partido en estado `PROGRAMADO`
- **THEN** la operación se rechaza y no se crea ningún movimiento

#### Scenario: Partido designado se liquida
- **WHEN** el tesorero liquida un partido en estado `DESIGNADO` con designaciones elegibles
- **THEN** se generan los movimientos correspondientes y el partido pasa a `JUGADO`

### Requirement: Designaciones que devengan honorarios

Solo SHALL devengar honorarios las designaciones en estado `CONFIRMADA` o `CUMPLIDA`. Las designaciones `AUSENTE`, `RECHAZADA` y `PROPUESTA` SHALL NOT generar movimientos.
Ref: RN-14.

#### Scenario: Designación ausente no cobra
- **WHEN** un partido tiene una designación `CONFIRMADA` y otra `AUSENTE`
- **THEN** se crea un único movimiento `HONORARIO` para la designación `CONFIRMADA`

#### Scenario: Designación propuesta no cobra
- **WHEN** un partido tiene únicamente designaciones en estado `PROPUESTA`
- **THEN** la liquidación no crea movimientos de honorario para esas designaciones

### Requirement: Honorario congelado e inmutable

Al liquidar, el sistema SHALL usar el `honorario` ya definido en la designación como valor congelado y SHALL NOT volver a resolver la tarifa. Si no está definido, SHALL resolverlo con la fecha del partido, congelarlo en la designación y persistir ese mismo importe en el movimiento. Cambios posteriores en la tabla de aranceles SHALL NOT alterar designaciones ni movimientos pasados.
Ref: RN-06, RN-16.

#### Scenario: Se respeta el honorario congelado
- **WHEN** la designación tiene `honorario = 61000.00` y la tarifa vigente indica otro importe
- **THEN** el movimiento `HONORARIO` se crea por `61000.00`

#### Scenario: Cambio de arancel no reescribe el pasado
- **WHEN** se carga una nueva vigencia de arancel después de liquidado un partido
- **THEN** el movimiento existente conserva el importe originalmente congelado

### Requirement: Devengado por fecha del partido

La tarifa se SHALL resolver con la fecha del partido y el escalafón del árbitro designado, nunca con la fecha en que se ejecuta la liquidación.
Ref: RN-11.

#### Scenario: Partido de octubre liquidado en noviembre
- **WHEN** se liquida el 5 de noviembre un partido jugado el 31 de octubre
- **THEN** se usa la tarifa cuya vigencia contiene el 31 de octubre y el movimiento corresponde al período de octubre

#### Scenario: Escalafón del designado define el importe
- **WHEN** dos árbitros de escalafones distintos se liquidan en el mismo torneo
- **THEN** cada uno recibe el importe de la tarifa correspondiente a su escalafón

### Requirement: Movimiento de honorario por designación

La liquidación SHALL crear exactamente un movimiento `CREDITO` con concepto `HONORARIO` por cada designación elegible, por el 100% del honorario bruto.
Ref: RN-04, RN-30.

#### Scenario: Dos designaciones generan dos honorarios
- **WHEN** un partido `DESIGNADO` tiene dos designaciones `CONFIRMADA`
- **THEN** se crean dos movimientos `CREDITO` / `HONORARIO`, uno por cada designación

#### Scenario: Honorario acreditado al 100%
- **WHEN** una designación tiene honorario de `61000.00`
- **THEN** el movimiento `HONORARIO` se acredita por `61000.00`, sin descontar la retención

### Requirement: Retención del 10% en ambas modalidades

La liquidación SHALL crear un movimiento `DEBITO` con concepto `RETENCION` equivalente al 10% del honorario seco de cada designación, tanto en modalidad `EN_CANCHA` como `DIFERIDO`. La retención SHALL calcularse por designación con `ROUND_HALF_UP`, SHALL usar el honorario congelado cuando exista y SHALL NOT aplicarse sobre el viático.
Ref: RN-30, RN-31, RN-33.

#### Scenario: Retención en pago en cancha
- **WHEN** se liquida un partido `EN_CANCHA` con honorario de `61000.00`
- **THEN** se acredita `HONORARIO` por `61000.00` y se debita `RETENCION` por `6100.00`

#### Scenario: Retención en pago diferido
- **WHEN** se liquida un partido `DIFERIDO` con honorario de `52500.00`
- **THEN** se acredita `HONORARIO` por `52500.00` y se debita `RETENCION` por `5250.00`

#### Scenario: Retención sobre reparto U11
- **WHEN** dos designaciones U11 reciben `15950.00` cada una por el reparto de `U11_DOBLE`
- **THEN** cada designación genera una retención de `1595.00`

#### Scenario: El viático no sufre retención
- **WHEN** una designación con auto recibe honorario y viático
- **THEN** la retención se calcula solo sobre el honorario y el movimiento `VIATICO` queda íntegro

### Requirement: Viático por uso de auto

El viático SHALL ser un movimiento independiente `CREDITO` con concepto `VIATICO`, calculado como `cancha.litros_viatico × precio_litro` con la fecha del partido y asignado a la designación que declaró `usa_auto=True`. Como máximo una designación por partido SHALL tener `usa_auto=True`; si hay más, la liquidación SHALL fallar con `ViaticoInvalido` y SHALL NOT escribir ningún movimiento.
Ref: RN-12, RN-17.

#### Scenario: Viático calculado con la fecha del partido
- **WHEN** la cancha tiene `24` litros y el precio vigente a la fecha del partido es `2361.000`
- **THEN** se crea un `CREDITO` / `VIATICO` por `56664.00` para la designación con auto

#### Scenario: Dos autos en el mismo partido
- **WHEN** dos designaciones del mismo partido tienen `usa_auto=True`
- **THEN** la liquidación falla con `ViaticoInvalido` y no se crea ningún movimiento

### Requirement: Supresión del viático nulo

El sistema SHALL NOT generar movimiento de viático cuando la designación no usa auto, cuando `cancha.litros_viatico` es `0` o cuando el monto calculado es `0.00`.
Ref: RN-18.

#### Scenario: Cancha sin litros asignados
- **WHEN** la designación usa auto pero la cancha tiene `litros_viatico = 0`
- **THEN** no se crea movimiento de viático

#### Scenario: Designación sin auto
- **WHEN** el partido tiene un auto declarado en otra designación y esta no usa auto
- **THEN** esta designación no recibe movimiento de viático

### Requirement: Atomicidad de la liquidación

Antes de escribir cualquier movimiento, la liquidación SHALL pre-validar todas las tarifas y condiciones del partido. Si falta una tarifa o falla una validación, SHALL NOT crear ningún movimiento y SHALL dejar el partido en su estado original.
Ref: RN-15.

#### Scenario: Falta una tarifa en una terna
- **WHEN** una de tres designaciones no tiene tarifa resoluble
- **THEN** la liquidación falla, no se escribe ningún honorario ni retención y el partido conserva su estado

#### Scenario: Liquidación válida completa
- **WHEN** todas las designaciones elegibles tienen tarifa y las validaciones pasan
- **THEN** se escriben todos los movimientos y recién entonces el partido pasa a `JUGADO`

### Requirement: Idempotencia de la liquidación

Reprocesar la liquidación de un partido SHALL NOT duplicar honorarios, retenciones ni viáticos. La restricción `UNIQUE(designacion_id, concepto)` SHALL garantizar como máximo un movimiento por concepto y designación, y un nuevo intento SHALL dejar los saldos sin cambios.
Ref: RN-05, RN-29.

#### Scenario: Liquidar dos veces el mismo partido
- **WHEN** se liquida un partido ya liquidado
- **THEN** no se crean movimientos nuevos y los saldos permanecen iguales

#### Scenario: Panel de tesorería repite la acción
- **WHEN** el tesorero vuelve a pulsar Liquidar sobre un partido ya liquidado
- **THEN** la operación es idempotente y el partido continúa en `JUGADO`

### Requirement: Mora del pago diferido

Cuando se registra `partido.fecha_cobro` y la diferencia con la fecha del partido supera `90` días, el árbitro SHALL cobrar el 100%: si el partido no estaba liquidado, SHALL omitirse la retención; si ya estaba liquidado, SHALL acreditarse un movimiento `CREDITO` con concepto `AJUSTE` por lo retenido. El reintegro SHALL ser idempotente por `UNIQUE(designacion_id, AJUSTE)`.
Ref: RN-32.

#### Scenario: Mora detectada antes de liquidar
- **WHEN** se registra un cobro a los `100` días de un partido diferido aún no liquidado
- **THEN** la liquidación posterior acredita el honorario completo y no crea la retención del 10%

#### Scenario: Mora detectada después de liquidar
- **WHEN** se registra un cobro a los `120` días de un partido diferido ya liquidado con retención
- **THEN** se crea un `CREDITO` / `AJUSTE` por el importe retenido y un segundo registro de cobro no lo duplica

### Requirement: Signo y valor de los movimientos

Todo movimiento generado por la liquidación SHALL tener `monto` estrictamente positivo; la naturaleza de crédito o débito SHALL expresarse exclusivamente en el campo `tipo`.
Ref: RN-07.

#### Scenario: Retención como débito positivo
- **WHEN** se genera la retención del 10% de un honorario de `61000.00`
- **THEN** el movimiento tiene `tipo = DEBITO` y `monto = 6100.00`, nunca un monto negativo

#### Scenario: Honorario como crédito positivo
- **WHEN** se genera el honorario de una designación
- **THEN** el movimiento tiene `tipo = CREDITO` y `monto` mayor que cero

### Requirement: Coherencia entre movimiento y designación

Un movimiento con `designacion_id` no nulo SHALL referenciar una designación del mismo árbitro al que se acredita o debita el movimiento.
Ref: RN-09.

#### Scenario: Movimiento de otra designación
- **WHEN** se intenta asociar a un árbitro un movimiento cuya designación pertenece a otro árbitro
- **THEN** la operación se rechaza y no se persiste el movimiento

#### Scenario: Movimiento del mismo árbitro
- **WHEN** se liquida una designación del árbitro y se crea su honorario
- **THEN** el movimiento queda asociado a esa designación y al mismo `arbitro_id`

### Requirement: Reparto especial de U11

Para un partido de categoría `U11`, con una designación elegible SHALL aplicarse la tarifa `U11` de `19600.00`; con dos designaciones elegibles SHALL aplicarse la tarifa global `U11_DOBLE` de `31900.00` dividida en partes iguales de `15950.00` para cada una. Con más de dos designaciones elegibles SHALL fallar con `CantidadDesignacionesInvalida` y SHALL NOT escribir nada.
Ref: RN-21.

#### Scenario: U11 con un árbitro
- **WHEN** se liquida un partido U11 con una sola designación elegible
- **THEN** esa designación recibe un honorario de `19600.00`

#### Scenario: U11 con dos árbitros
- **WHEN** se liquida un partido U11 con dos designaciones elegibles
- **THEN** cada designación recibe un honorario de `15950.00` y el total liquidado es `31900.00`

#### Scenario: U11 con tres árbitros
- **WHEN** se intenta liquidar un partido U11 con tres designaciones elegibles
- **THEN** la liquidación falla con `CantidadDesignacionesInvalida` y no se crea ningún movimiento

### Requirement: Arancel fijo del rol CUARTO

El rol `CUARTO` SHALL cobrar siempre un arancel fijo de rol `CUARTO` y SHALL NOT heredar el arancel de campo. Si la categoría del torneo no tiene arancel `CUARTO` vigente a la fecha del partido, la liquidación SHALL fallar con `TarifaNoEncontrada`.
Ref: RN-20.

#### Scenario: Cuarto en torneo con arancel propio
- **WHEN** se liquida un `CUARTO` en Super Liga, que tiene arancel `CUARTO` vigente
- **THEN** el honorario surge de ese arancel fijo y no del arancel de principal

#### Scenario: Cuarto en Ascenso
- **WHEN** se liquida un `CUARTO` en un partido de Ascenso sin arancel `CUARTO`
- **THEN** la liquidación falla con `TarifaNoEncontrada` y no se escribe ningún movimiento

### Requirement: Resolución del arancel por escalafón

La resolución del honorario SHALL intentar primero la tarifa del escalafón del árbitro, luego la tarifa `UNICA` y por último la tarifa genérica del rol, según el orden de especificidad definido por la capacidad `tarifas`. Si ninguna coincide, la liquidación SHALL fallar con `TarifaNoEncontrada`.
Ref: RN-19.

#### Scenario: Escalafón sin tarifa propia usa UNICA
- **WHEN** el árbitro tiene un escalafón sin tarifa para el torneo y existe una tarifa `UNICA` vigente
- **THEN** se usa el importe de la tarifa `UNICA`

#### Scenario: Sin ninguna tarifa aplicable
- **WHEN** no existe tarifa para el escalafón, ni `UNICA`, ni genérica del rol
- **THEN** la liquidación falla con `TarifaNoEncontrada` y detalla la designación afectada

### Requirement: Transición del partido a JUGADO

Una liquidación exitosa SHALL dejar el partido en estado `JUGADO`. Si la liquidación falla, el partido SHALL conservar el estado que tenía antes del intento.
Ref: RN-04, RN-29.

#### Scenario: Partido liquidado queda jugado
- **WHEN** la liquidación termina sin errores
- **THEN** el partido pasa a `JUGADO` en la misma transacción

#### Scenario: Fallo de liquidación no cambia el estado
- **WHEN** la liquidación falla por tarifa faltante
- **THEN** el partido sigue en `DESIGNADO`

### Requirement: Desglose en el recibo

El recibo de liquidación SHALL mostrar el honorario bruto, la retención del 10% y el neto resultante, tanto para `EN_CANCHA` como para `DIFERIDO`.
Ref: RN-31.

#### Scenario: Recibo de pago en cancha
- **WHEN** se emite el recibo de un partido `EN_CANCHA` con honorario de `61000.00`
- **THEN** el recibo muestra honorario `61000.00`, retención `6100.00` y neto `54900.00`

#### Scenario: Recibo de pago diferido
- **WHEN** se emite el recibo de un partido `DIFERIDO` con honorario de `52500.00`
- **THEN** el recibo muestra el mismo desglose de honorario, retención y neto que en cancha
