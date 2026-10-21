# Padrón de árbitros

## Purpose

Define el alta y los datos del padrón de árbitros: identificación única, escalafón, estado y disponibilidad de vehículo. El escalafón participa en la resolución del arancel y `tiene_auto` describe el perfil, no el uso concreto en un partido.
Fuente: `docs/dominio.md` (RN-03, RN-12, RN-17, RN-19).

## Requirements

### Requirement: Identificación única del árbitro

El `legajo` y el `dni` de un árbitro SHALL ser únicos en todo el padrón. El alta SHALL rechazar cualquier legajo o DNI ya registrado, sin crear un segundo árbitro.
Ref: RN-03.

#### Scenario: Legajo duplicado
- **WHEN** se intenta dar de alta un árbitro con un legajo que ya existe
- **THEN** el alta se rechaza con error de validación y no se persiste el árbitro

#### Scenario: DNI duplicado
- **WHEN** se intenta dar de alta un árbitro con un DNI que ya pertenece a otro árbitro
- **THEN** el alta se rechaza y el padrón queda sin cambios

#### Scenario: Legajo y DNI nuevos
- **WHEN** se da de alta un árbitro con legajo y DNI que no existen
- **THEN** el árbitro se crea correctamente en el padrón

### Requirement: Datos mínimos de alta

El alta de un árbitro SHALL exigir legajo, nombre, apellido y DNI. La ausencia de cualquiera de esos datos SHALL impedir la creación del registro.
Ref: RN-03.

#### Scenario: Alta sin apellido
- **WHEN** se intenta crear un árbitro sin apellido
- **THEN** el alta se rechaza con error de validación

#### Scenario: Alta completa
- **WHEN** se informan legajo, nombre, apellido y DNI válidos
- **THEN** el árbitro se crea y queda disponible para ser designado

### Requirement: Escalafón del árbitro

La categoría del árbitro SHALL ser uno de los valores `CAT_A`, `CAT_A1`, `CAT_B`, `PROMOCIONAL` o `UNICA`, o bien quedar vacía. El escalafón registrado SHALL ser el que se use al resolver el arancel del árbitro.
Ref: RN-19.

#### Scenario: Alta con escalafón
- **WHEN** se registra un árbitro con categoría `CAT_A1`
- **THEN** el padrón guarda `CAT_A1` y la resolución de tarifas lo usa como su escalafón

#### Scenario: Árbitro sin escalafón
- **WHEN** se registra un árbitro sin categoría
- **THEN** el alta se acepta con categoría nula y la resolución de tarifas aplica sus reglas de fallback

#### Scenario: Escalafón inválido
- **WHEN** se intenta registrar un árbitro con una categoría fuera del enum
- **THEN** el alta se rechaza con error de validación

### Requirement: Estado del árbitro

El estado del árbitro SHALL ser `ACTIVO`, `SUSPENDIDO` o `INACTIVO`; cualquier otro valor SHALL rechazarse. El estado SHALL conservarse como dato del padrón junto con las fechas de alta y baja.
Ref: RN-03.

#### Scenario: Estado válido
- **WHEN** se registra un árbitro con estado `SUSPENDIDO`
- **THEN** el padrón guarda ese estado

#### Scenario: Estado inválido
- **WHEN** se intenta guardar un estado distinto de `ACTIVO`, `SUSPENDIDO` o `INACTIVO`
- **THEN** la operación se rechaza con error de validación

### Requirement: Disponibilidad de vehículo del perfil

`tiene_auto` SHALL ser una propiedad permanente del perfil del árbitro que indica si dispone de vehículo propio. SHALL ser independiente de `Designacion.usa_auto`: marcar el perfil SHALL NOT generar viáticos y cambiar el uso de auto en una designación SHALL NOT modificar el perfil.
Ref: RN-12, RN-17.

#### Scenario: Perfil con auto no genera viático
- **WHEN** un árbitro tiene `tiene_auto=True` pero su designación tiene `usa_auto=False`
- **THEN** la liquidación no le genera movimiento de viático

#### Scenario: Uso de auto sin cambiar el perfil
- **WHEN** una designación de un árbitro con `tiene_auto=False` declara `usa_auto=True` y se liquida
- **THEN** se genera el viático de esa designación y el perfil del árbitro sigue con `tiene_auto=False`

#### Scenario: Perfil sin auto
- **WHEN** un árbitro tiene `tiene_auto=False`
- **THEN** el padrón lo refleja así al armar las ternas, con independencia de sus designaciones pasadas
