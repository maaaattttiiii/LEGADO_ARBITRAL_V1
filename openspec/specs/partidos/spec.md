# Partidos

## Purpose

Define el alta y el ciclo de vida de los partidos: datos mínimos, categoría heredada del torneo, fecha y hora en hora local argentina, estados, reprogramación, modalidad de pago y registro de la fecha de cobro municipal.
Fuente: `docs/dominio.md` (RN-04, RN-13, RN-25, RN-32, RN-34, RN-39).

## Requirements

### Requirement: Registro del partido

El alta de un partido SHALL exigir torneo, cancha, fecha y hora, equipo local y equipo visitante. La categoría del partido SHALL obtenerse siempre desde `torneo.categoria_torneo` y SHALL NOT duplicarse en el partido. Todo partido nuevo SHALL iniciar en estado `PROGRAMADO`.
Ref: RN-13, RN-34.

#### Scenario: Alta completa de un partido
- **WHEN** se registra un partido con torneo, cancha, fecha, equipos local y visitante
- **THEN** el partido se crea en estado `PROGRAMADO`

#### Scenario: Categoría heredada del torneo
- **WHEN** se consulta la categoría de un partido de un torneo U19
- **THEN** la categoría se obtiene de `torneo.categoria_torneo` y no existe un campo de categoría propio del partido

#### Scenario: Alta sin cancha
- **WHEN** se intenta crear un partido sin cancha
- **THEN** el alta se rechaza con error de validación y no se persiste el partido

### Requirement: Fecha y hora en hora local argentina

La interfaz SHALL capturar la fecha y hora en hora local del club (ART, UTC-3, offset fijo) y el sistema SHALL persistirlas en UTC mediante la conversión de `app/tiempo.py`. La visualización SHALL volver a mostrar la fecha en ART.
Ref: RN-39.

#### Scenario: Partido de las 21:00 ART
- **WHEN** se carga un partido para el 31 de octubre a las 21:00 ART
- **THEN** se persiste como `2026-11-01 00:00` UTC y se muestra nuevamente como 31 de octubre a las 21:00 ART

#### Scenario: Sin horario de verano
- **WHEN** se carga un partido en cualquier mes del año
- **THEN** la conversión usa siempre el offset fijo UTC-3, sin variación estacional

### Requirement: Estados y transiciones del partido

El partido SHALL respetar las transiciones `PROGRAMADO` a `DESIGNADO`, `DESIGNADO` a `JUGADO` o `SUSPENDIDO`, y `PROGRAMADO` o `DESIGNADO` a `SUSPENDIDO`. Cualquier transición no prevista SHALL rechazarse. Solo los estados `DESIGNADO` y `JUGADO` SHALL ser liquidables.
Ref: RN-13.

#### Scenario: Partido designado pasa a jugado
- **WHEN** se liquida un partido en estado `DESIGNADO`
- **THEN** el partido pasa a `JUGADO`

#### Scenario: Partido suspendido
- **WHEN** un partido `PROGRAMADO` o `DESIGNADO` se suspende
- **THEN** queda en estado `SUSPENDIDO`

#### Scenario: Intento de liquidar un suspendido
- **WHEN** se intenta liquidar un partido en estado `SUSPENDIDO`
- **THEN** la liquidación se rechaza y no se generan movimientos

### Requirement: Reprogramación del partido

Un partido SHALL poder pasar a `REPROGRAMADO` y desde ese estado volver a `PROGRAMADO` con una nueva fecha u otra terna. Mientras esté en `REPROGRAMADO` SHALL NOT ser liquidable.
Ref: RN-13, RN-25.

#### Scenario: Reprogramar y volver a programar
- **WHEN** un partido `DESIGNADO` se reprograma y luego se le asigna una nueva fecha
- **THEN** el partido queda nuevamente en `PROGRAMADO` y admite una nueva terna

#### Scenario: Liquidar un reprogramado
- **WHEN** se intenta liquidar un partido en estado `REPROGRAMADO`
- **THEN** la liquidación se rechaza sin movimientos

### Requirement: Modalidad de pago del partido

La modalidad de pago SHALL pertenecer al partido, con valor por defecto `EN_CANCHA` y alternativa `DIFERIDO`. Un mismo torneo SHALL poder mezclar partidos en cancha y diferidos. El cambio de modalidad SHALL NOT modificar el honorario bruto de las designaciones.
Ref: RN-34.

#### Scenario: Alta sin modalidad explícita
- **WHEN** se crea un partido sin indicar modalidad de pago
- **THEN** el partido queda en modalidad `EN_CANCHA`

#### Scenario: Partidos mezclados en un torneo
- **WHEN** un torneo tiene un partido `EN_CANCHA` y otro `DIFERIDO`
- **THEN** cada partido conserva su propia modalidad sin afectar al torneo ni al otro partido

#### Scenario: Cambio de modalidad antes de liquidar
- **WHEN** se cambia la modalidad de un partido aún no liquidado
- **THEN** el honorario bruto de sus designaciones no se altera

### Requirement: Registro de la fecha de cobro municipal

La fecha real de cobro municipal SHALL registrarse únicamente en partidos con modalidad `DIFERIDO` y SHALL ser posterior o igual a la fecha del partido. El registro SHALL habilitar el cálculo de días transcurridos y de mora que consume la capacidad `liquidacion`.
Ref: RN-32.

#### Scenario: Cobro anterior al partido
- **WHEN** se intenta registrar una `fecha_cobro` anterior a la fecha del partido
- **THEN** el registro se rechaza con error de validación

#### Scenario: Cobro en un partido en cancha
- **WHEN** se intenta registrar fecha de cobro municipal en un partido `EN_CANCHA`
- **THEN** la operación se rechaza porque la modalidad no es diferida

#### Scenario: Cobro diferido válido
- **WHEN** se registra una fecha de cobro posterior a la fecha de un partido `DIFERIDO`
- **THEN** el partido guarda la fecha y queda disponible para evaluar la mora de 90 días
