# Designaciones y armado de terna

## Purpose

Define cómo se asigna, reemplaza y valida la terna de un partido: roles, unicidad, conflictos horarios, uso de auto, límite de U11 y protección de las designaciones ya liquidadas. También fija los estados válidos de una designación y la transición del partido al designar.
Fuente: `docs/dominio.md` (RN-01, RN-02, RN-17, RN-21, RN-22, RN-23, RN-24, RN-25).

## Requirements

### Requirement: Un árbitro por partido

Un árbitro SHALL tener como máximo una designación en el mismo partido. El alta o la asignación de terna SHALL rechazar la repetición del mismo `arbitro_id` en otro rol del mismo partido.
Ref: RN-01.

#### Scenario: Mismo árbitro en dos roles
- **WHEN** se intenta asignar al mismo árbitro como principal y como asistente 1 del mismo partido
- **THEN** la asignación se rechaza y no se modifica la terna

#### Scenario: Árbitros distintos en roles distintos
- **WHEN** se asigna un principal y un asistente con `arbitro_id` diferentes
- **THEN** ambas designaciones se crean correctamente

### Requirement: Un árbitro por rol

Un partido SHALL tener como máximo una designación vigente por rol (`PRINCIPAL`, `ASISTENTE_1`, `ASISTENTE_2`, `CUARTO`). Al pasar una designación a `RECHAZADA`, el cupo de ese rol SHALL quedar libre para asignar a otro árbitro, conservando la fila rechazada como historial.
Ref: RN-02.

#### Scenario: Dos principales en el mismo partido
- **WHEN** se intenta asignar un segundo principal a un partido que ya tiene principal vigente
- **THEN** la asignación se rechaza

#### Scenario: Reasignación después de un rechazo
- **WHEN** el principal rechaza la designación y el tesorero designa a otro árbitro como principal
- **THEN** el nuevo principal ocupa el rol y la designación rechazada se conserva como historial

### Requirement: Estados y transiciones de la designación

Una designación SHALL recorrer solo transiciones válidas: `PROPUESTA` a `CONFIRMADA`, `CONFIRMADA` a `CUMPLIDA` o `AUSENTE`, y `PROPUESTA` o `CONFIRMADA` a `RECHAZADA`. Cualquier otra transición SHALL rechazarse.
Ref: RN-25.

#### Scenario: Confirmar y cumplir una designación
- **WHEN** una designación `PROPUESTA` se confirma y luego el árbitro dirige el partido
- **THEN** la designación pasa a `CONFIRMADA` y después a `CUMPLIDA`

#### Scenario: Transición inválida desde RECHAZADA
- **WHEN** se intenta pasar una designación `RECHAZADA` a `CONFIRMADA`
- **THEN** la transición se rechaza y el estado no cambia

### Requirement: Asignación completa de la terna

`asignar_terna()` SHALL exigir que el partido exista y esté en `PROGRAMADO`, `DESIGNADO` o `REPROGRAMADO`, que haya al menos un árbitro asignado y que los árbitros no se repitan entre roles. Los roles vacíos SHALL eliminarse; los roles con árbitro SHALL crearse o actualizarse. El partido SHALL pasar a `DESIGNADO` y las designaciones nuevas SHALL nacer en `CONFIRMADA`.
Ref: RN-25.

#### Scenario: Terna con roles vacíos
- **WHEN** se asigna solo principal y asistente 1, dejando asistente 2 y cuarto vacíos
- **THEN** se crean únicamente esas dos designaciones y el partido queda `DESIGNADO`

#### Scenario: Retiro de un rol de la terna
- **WHEN** se vuelve a asignar la terna sin árbitro en el rol de asistente 2, que antes tenía uno
- **THEN** la designación de ese rol se elimina y las demás se conservan

#### Scenario: Terna sin ningún árbitro
- **WHEN** se intenta asignar una terna sin ningún rol completo
- **THEN** la operación se rechaza y el partido no cambia de estado

#### Scenario: Partido en estado no designable
- **WHEN** se intenta asignar terna a un partido en estado `JUGADO`
- **THEN** la operación se rechaza

### Requirement: Conflicto horario entre partidos

Un árbitro SHALL NOT quedar designado en dos partidos cuya diferencia horaria sea menor a `2` horas, ya sea en la misma cancha o en otra. Una diferencia de exactamente `2` horas SHALL estar permitida. Las designaciones `RECHAZADA` SHALL NOT bloquear la asignación.
Ref: RN-22.

#### Scenario: Partidos separados por 90 minutos
- **WHEN** un árbitro ya designado en un partido a las 20:00 se intenta designar en otro a las 21:30, en la misma cancha o en otra
- **THEN** la asignación se rechaza por conflicto horario

#### Scenario: Partidos separados por dos horas exactas
- **WHEN** un árbitro ya designado a las 20:00 se intenta designar en otro partido a las 22:00
- **THEN** la asignación se acepta

#### Scenario: Designación rechazada no bloquea
- **WHEN** el único antecedente cercano del árbitro es una designación en estado `RECHAZADA`
- **THEN** la nueva designación se acepta sin conflicto

### Requirement: Un solo auto por partido

Como máximo una designación del partido SHALL tener `usa_auto=True`. El rol indicado en `auto_rol` MUST corresponder a un rol con árbitro asignado. Si se detectan dos autos o un `auto_rol` sin árbitro, `asignar_terna()` SHALL fallar con `ViaticoInvalido` y SHALL NOT aplicar ningún cambio.
Ref: RN-17.

#### Scenario: Dos roles con auto
- **WHEN** la terna indica `usa_auto=True` para el principal y para un asistente
- **THEN** la asignación falla con `ViaticoInvalido` y la terna anterior queda intacta

#### Scenario: Auto en un rol vacío
- **WHEN** `auto_rol` apunta a un rol que no tiene árbitro asignado
- **THEN** la asignación se rechaza sin modificar el partido

#### Scenario: Auto único válido
- **WHEN** la terna asigna un solo `auto_rol` sobre un rol con árbitro
- **THEN** esa designación queda con `usa_auto=True` y las demás con `usa_auto=False`

### Requirement: Inmutabilidad de designaciones liquidadas

Una designación que ya generó movimientos SHALL NOT reemplazarse, quitarse de la terna ni cambiar su `usa_auto`. Cualquier intento SHALL fallar con `DesignacionLiquidada` y SHALL dejar la terna y los movimientos sin cambios.
Ref: RN-23.

#### Scenario: Reemplazo de un árbitro ya liquidado
- **WHEN** se intenta cambiar el principal de un partido cuyas designaciones ya generaron honorarios
- **THEN** la operación falla con `DesignacionLiquidada` y se conserva la designación original

#### Scenario: Cambio de auto después de liquidar
- **WHEN** se intenta mover `usa_auto` a otra designación de un partido ya liquidado
- **THEN** la operación se rechaza y no se altera el viático existente

### Requirement: Designación de CUARTO con arancel vigente

Solo SHALL admitirse una designación en rol `CUARTO` cuando la categoría del torneo tenga arancel `CUARTO` vigente a la fecha del partido. Si no lo tiene, la asignación SHALL rechazarse.
Ref: RN-24.

#### Scenario: Cuarto en torneo sin arancel de cuarto
- **WHEN** se intenta designar un cuarto en Ascenso, Promoción o Super Liga Femenina
- **THEN** la asignación se rechaza porque no hay arancel `CUARTO` vigente

#### Scenario: Cuarto en torneo con arancel de cuarto
- **WHEN** se designa un cuarto en Super Liga con arancel `CUARTO` vigente a la fecha del partido
- **THEN** la designación se crea correctamente

### Requirement: Límite de designaciones en U11

En un partido de categoría `U11`, `asignar_terna()` SHALL aceptar como máximo dos designaciones. La tercera SHALL rechazarse al designar, sin llegar a la liquidación, y el panel SHALL ofrecer solo dos slots para U11.
Ref: RN-21.

#### Scenario: Dos árbitros en U11
- **WHEN** se asignan dos árbitros a un partido U11
- **THEN** la terna se guarda con dos designaciones

#### Scenario: Tercer árbitro en U11
- **WHEN** se intenta asignar un tercer árbitro a un partido U11 que ya tiene dos
- **THEN** la asignación se rechaza y la terna de dos queda intacta

#### Scenario: Panel de U11 con dos slots
- **WHEN** el tesorero abre el panel de designaciones de un partido U11
- **THEN** la interfaz muestra únicamente dos lugares de designación
