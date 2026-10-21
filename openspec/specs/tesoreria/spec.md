# Tesorería y cuenta corriente

## Purpose

Define el panel del tesorero y la cuenta corriente de cada árbitro: saldo calculado, filtro por período, ajustes manuales, liquidación desde el panel y registro del cobro municipal. El historial financiero es inmutable y el saldo nunca se persiste.
Fuente: `docs/dominio.md` (RN-05, RN-07, RN-08, RN-09, RN-26, RN-27, RN-28, RN-29, RN-32).

## Requirements

### Requirement: Saldo calculado y no persistido

El saldo de un árbitro SHALL calcularse como `SUM(CREDITO) - SUM(DEBITO)` sobre sus movimientos y SHALL NOT existir una columna de saldo en ninguna tabla.
Ref: RN-08, RN-26.

#### Scenario: Saldo con créditos y débitos
- **WHEN** un árbitro tiene un crédito de `61000.00` y un débito de `6100.00`
- **THEN** el saldo mostrado es `54900.00` y no se guarda en la base

#### Scenario: Alta de un movimiento recalcula el saldo
- **WHEN** se registra un nuevo movimiento de un árbitro
- **THEN** la próxima consulta de saldo incluye ese movimiento sin necesidad de actualizar una columna de saldo

### Requirement: Filtro de saldo por período

El panel SHALL permitir acotar el saldo a un período `AAAA-MM` y, en ese caso, SHALL sumar únicamente los movimientos cuyo `periodo` coincide. Sin filtro SHALL sumar todos los movimientos del árbitro.
Ref: RN-26.

#### Scenario: Saldo total sin filtro
- **WHEN** se consulta el saldo de un árbitro sin indicar período
- **THEN** se suman todos sus créditos y débitos históricos

#### Scenario: Saldo acotado a octubre
- **WHEN** se consulta el saldo con `periodo=2026-10`
- **THEN** solo se suman los movimientos de octubre y se excluyen los de otros meses

#### Scenario: Período inválido no rompe el panel
- **WHEN** se consulta con un período con formato inválido
- **THEN** el panel muestra el error y lista los saldos de todos los períodos

### Requirement: Significado visual del saldo

El saldo mostrado SHALL interpretarse como a favor del árbitro cuando es positivo (verde), como deuda del árbitro con la asociación cuando es negativo (rojo) y como sin saldo cuando es cero.
Ref: RN-27.

#### Scenario: Saldo positivo
- **WHEN** el saldo calculado de un árbitro es `54900.00`
- **THEN** el panel lo muestra en verde como importe a favor del árbitro

#### Scenario: Saldo negativo
- **WHEN** el saldo calculado de un árbitro es `-12000.00`
- **THEN** el panel lo muestra en rojo como deuda del árbitro

#### Scenario: Saldo cero
- **WHEN** los créditos y débitos de un árbitro se compensan exactamente
- **THEN** el panel muestra saldo cero, sin color de acreedor ni de deudor

### Requirement: Movimientos con monto positivo y designación coherente

Todo movimiento de cuenta corriente SHALL tener `monto` mayor que cero y su naturaleza SHALL expresarse en `tipo`. Un movimiento con `designacion_id` no nulo SHALL pertenecer al mismo árbitro de la designación.
Ref: RN-07, RN-09.

#### Scenario: Movimiento con monto cero
- **WHEN** se intenta registrar un movimiento con `monto = 0`
- **THEN** el registro se rechaza porque el monto debe ser positivo

#### Scenario: Movimiento de otra designación
- **WHEN** se intenta registrar un movimiento para un árbitro usando la designación de otro árbitro
- **THEN** la operación se rechaza y el movimiento no se persiste

#### Scenario: Débito con monto positivo
- **WHEN** se registra un débito de retención
- **THEN** el movimiento tiene `tipo = DEBITO` y `monto` positivo

### Requirement: Ajustes manuales restringidos

Los ajustes manuales SHALL limitarse a los conceptos `DESCUENTO`, `ADELANTO`, `PAGO`, `MULTA` y `AJUSTE`. Los conceptos `HONORARIO` y `VIATICO` SHALL generarse exclusivamente al liquidar un partido. Todo ajuste MUST tener `monto > 0`, MUST indicar un período `AAAA-MM` y SHALL quedar sin `designacion_id`.
Ref: RN-28.

#### Scenario: Ajuste manual válido
- **WHEN** el tesorero registra un `PAGO` de `20000.00` en el período `2026-10`
- **THEN** se crea un movimiento manual sin `designacion_id` asociado a ese período

#### Scenario: Alta manual de honorario
- **WHEN** se intenta registrar un ajuste manual con concepto `HONORARIO`
- **THEN** la operación se rechaza porque ese concepto solo nace de la liquidación

#### Scenario: Ajuste sin período
- **WHEN** se intenta registrar un ajuste sin período
- **THEN** el alta se rechaza con error de validación

#### Scenario: Ajuste con monto no positivo
- **WHEN** se intenta registrar un ajuste con monto `0.00` o negativo
- **THEN** el alta se rechaza

### Requirement: Liquidación desde el panel

El panel SHALL ofrecer la acción Liquidar sobre los partidos en estado `DESIGNADO` y SHALL delegar en `liquidar_partido()`. La operación SHALL ser idempotente, SHALL dejar el partido en `JUGADO` y, si falla, SHALL NOT escribir nada y SHALL mostrar el error al tesorero.
Ref: RN-29.

#### Scenario: Liquidación exitosa desde el panel
- **WHEN** el tesorero liquida un partido `DESIGNADO` con tarifas disponibles
- **THEN** se generan los movimientos y el partido queda en `JUGADO`

#### Scenario: Segundo clic en Liquidar
- **WHEN** el tesorero vuelve a liquidar un partido ya liquidado
- **THEN** no se duplican movimientos y los saldos no cambian

#### Scenario: Fallo mostrado al tesorero
- **WHEN** la liquidación falla por falta de tarifa
- **THEN** no se escribe ningún movimiento y el panel muestra el error

### Requirement: Registro del cobro municipal desde el panel

El panel SHALL permitir registrar la fecha real de cobro de los partidos `DIFERIDO` y SHALL informar los días transcurridos, si el partido está en mora y cuántos reintegros generó. El registro SHALL delegar en `registrar_cobro()` y respetar la idempotencia del reintegro.
Ref: RN-32.

#### Scenario: Cobro dentro del plazo
- **WHEN** se registra el cobro de un partido diferido a los `30` días
- **THEN** el panel informa que no hay mora y no genera reintegros

#### Scenario: Cobro en mora
- **WHEN** se registra el cobro de un partido diferido a los `100` días
- **THEN** el panel informa la mora y, si el partido estaba liquidado, un reintegro por designación

#### Scenario: Registro repetido del mismo cobro
- **WHEN** se vuelve a registrar la misma fecha de cobro
- **THEN** no se duplican los reintegros ya generados

### Requirement: Detalle de movimientos por árbitro

El panel SHALL exponer el detalle cronológico de movimientos de cada árbitro con fecha, tipo, concepto, monto, período y descripción, y SHALL mostrar el saldo calculado a partir de esos movimientos.
Ref: RN-26.

#### Scenario: Detalle de una cuenta
- **WHEN** el tesorero abre el detalle de un árbitro
- **THEN** ve sus movimientos y el saldo resultante de sumar créditos y restar débitos

#### Scenario: Detalle acotado a un período
- **WHEN** el tesorero abre el detalle con un período seleccionado
- **THEN** solo se listan y suman los movimientos de ese período
