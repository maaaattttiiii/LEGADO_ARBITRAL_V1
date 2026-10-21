# Tarifas y aranceles

## Purpose

Define los aranceles del honorario por categoría de torneo, rol y escalafón, su resolución por especificidad y vigencia, y las reglas de alta que preservan el historial inmutable. Incluye el tratamiento especial del rol `CUARTO` y de las tarifas U11.
Fuente: `docs/dominio.md` (RN-10, RN-11, RN-19, RN-20, RN-21, RN-24, RN-35).

## Requirements

### Requirement: Dimensiones de la tarifa

Una tarifa SHALL identificar la categoría de torneo, el rol y el escalafón al que aplica. Un `rol = NULL` SHALL significar que el monto aplica a cualquier rol de campo; una `categoria_arbitro = NULL` SHALL significar que aplica a cualquier escalafón; y `categoria_arbitro = UNICA` SHALL ser el comodín de los torneos con arancel único, como Inferiores y Master.
Ref: RN-19.

#### Scenario: Tarifa genérica de campo
- **WHEN** existe una tarifa con `rol = NULL` y `categoria_arbitro = CAT_A` para Super Liga
- **THEN** esa tarifa aplica tanto al principal como a los asistentes de escalafón `CAT_A`

#### Scenario: Tarifa de cualquier escalafón
- **WHEN** existe una tarifa con `categoria_arbitro = NULL` para un rol de campo
- **THEN** esa tarifa aplica a árbitros de cualquier escalafón

#### Scenario: Torneo con arancel único
- **WHEN** se resuelve una tarifa de U19 registrada con `categoria_arbitro = UNICA`
- **THEN** la tarifa aplica a todos los árbitros del torneo, sin importar su escalafón

### Requirement: Resolución por especificidad decreciente

La resolución SHALL buscar en este orden y quedarse con la primera coincidencia existente: `(rol, escalafón)`, `(rol, UNICA)`, `(rol, NULL)`, `(NULL, escalafón)`, `(NULL, UNICA)` y `(NULL, NULL)`. Dentro de la combinación ganadora SHALL tomar la vigencia con `vigencia_desde` más reciente.
Ref: RN-19.

#### Scenario: Coincidencia exacta de rol y escalafón
- **WHEN** existen tarifas para `(PRINCIPAL, CAT_A)` y para `(NULL, CAT_A)`
- **THEN** se usa la tarifa de `(PRINCIPAL, CAT_A)`

#### Scenario: Sin tarifa del escalafón se usa UNICA
- **WHEN** no existe tarifa para el escalafón del árbitro y sí existe `(rol, UNICA)`
- **THEN** se usa la tarifa `(rol, UNICA)` antes que la genérica `(rol, NULL)`

#### Scenario: Ninguna combinación coincide
- **WHEN** no existe ninguna tarifa para la categoría de torneo y la fecha indicada
- **THEN** la resolución falla con `TarifaNoEncontrada`

### Requirement: Vigencia aplicada a la fecha del partido

La tarifa SHALL considerarse vigente cuando `vigencia_desde <= fecha` y `vigencia_hasta` es `NULL` o mayor o igual a la fecha. La resolución SHALL usar la fecha del partido y SHALL NOT usar la fecha de liquidación.
Ref: RN-11.

#### Scenario: Dos vigencias superpuestas en el tiempo
- **WHEN** existen dos tarifas aplicables y la más reciente empezó a regir antes de la fecha del partido
- **THEN** se usa la de `vigencia_desde` más reciente

#### Scenario: Vigencia futura no aplica
- **WHEN** la única tarifa aplicable comienza a regir después de la fecha del partido
- **THEN** la resolución falla con `TarifaNoEncontrada`

### Requirement: Arancel fijo del rol CUARTO

La resolución para `CUARTO` SHALL buscar exclusivamente tarifas con `rol = CUARTO` y SHALL NOT heredar el arancel de campo, aunque exista una tarifa genérica o de principal aplicable.
Ref: RN-20.

#### Scenario: Cuarto no hereda el arancel de campo
- **WHEN** un torneo tiene tarifa de principal pero no tiene tarifa `CUARTO`
- **THEN** la resolución para el rol `CUARTO` falla con `TarifaNoEncontrada`

#### Scenario: Cuarto con arancel propio
- **WHEN** el torneo tiene una tarifa `(CUARTO, NULL)` vigente a la fecha del partido
- **THEN** la resolución devuelve ese arancel fijo de rol

### Requirement: Verificación de arancel CUARTO para designar

La capacidad SHALL exponer una verificación de existencia de arancel `CUARTO` vigente para una categoría de torneo y fecha, de modo que la asignación de terna pueda rechazar un cuarto que luego no se podría liquidar.
Ref: RN-24.

#### Scenario: Categoría sin arancel de cuarto
- **WHEN** se consulta si Ascenso tiene arancel `CUARTO` vigente a la fecha del partido
- **THEN** la verificación devuelve falso y la designación de un cuarto se rechaza

#### Scenario: Categoría con arancel de cuarto
- **WHEN** se consulta si Super Liga tiene arancel `CUARTO` vigente a la fecha del partido
- **THEN** la verificación devuelve verdadero

### Requirement: Tarifas U11 simple y doble

El sistema SHALL mantener una tarifa `U11` de `19600.00` para el partido con un árbitro y una tarifa `U11_DOBLE` de `31900.00` como arancel global del partido con dos árbitros. `U11_DOBLE` SHALL NOT ser una categoría de torneo a designar: es el arancel que usa la liquidación cuando el partido U11 tiene dos designaciones elegibles.
Ref: RN-21.

#### Scenario: Un árbitro en U11
- **WHEN** se resuelve el arancel de un partido U11 con una designación elegible
- **THEN** se usa la tarifa `U11` de `19600.00`

#### Scenario: Dos árbitros en U11
- **WHEN** se liquida un partido U11 con dos designaciones elegibles
- **THEN** se usa la tarifa global `U11_DOBLE` de `31900.00` y la liquidación la divide en `15950.00` por designación

### Requirement: Integridad de la vigencia

Al crear una tarifa, el sistema MUST exigir `monto_base > 0`, MUST aceptar `vigencia_hasta` nula o mayor o igual a `vigencia_desde`, MUST garantizar la unicidad de `(categoría de torneo, rol, categoría de árbitro, vigencia_desde)` y SHALL rechazar cualquier solapamiento de vigencias para la misma combinación de categoría, rol y escalafón.
Ref: RN-10.

#### Scenario: Monto no positivo
- **WHEN** se intenta crear una tarifa con `monto_base = 0`
- **THEN** el alta se rechaza con error de validación y no se persiste

#### Scenario: Rango de vigencia invertido
- **WHEN** se intenta crear una tarifa con `vigencia_hasta` anterior a `vigencia_desde`
- **THEN** el alta se rechaza con error de validación

#### Scenario: Vigencias solapadas
- **WHEN** se intenta crear una tarifa para una combinación que ya tiene una vigencia que se superpone
- **THEN** `crear_tarifa()` rechaza el alta y no se persiste ninguna fila

### Requirement: ABM de aranceles solo por nueva vigencia

El alta de aranceles SHALL limitarse a cargar nuevas vigencias. Una tarifa existente SHALL NOT editarse ni borrarse, para preservar el historial inmutable del que se resuelven los honorarios.
Ref: RN-35.

#### Scenario: Intento de edición de una tarifa
- **WHEN** se intenta modificar el `monto_base` de una tarifa ya registrada
- **THEN** la operación se rechaza y la tarifa original permanece intacta

#### Scenario: Cambio de precio mediante nueva vigencia
- **WHEN** el colegio actualiza el arancel de una categoría
- **THEN** se crea una nueva tarifa con una `vigencia_desde` posterior y la vigencia anterior se conserva
