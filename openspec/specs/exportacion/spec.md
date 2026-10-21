# Exportación mensual de liquidación

## Purpose

Define la exportación de la liquidación mensual en CSV y PDF: contrato HTTP, filas por designación, importes incluidos, orden, formato de archivo y nombre de descarga. La exportación refleja solo honorarios, retenciones y viáticos del período.
Fuente: `docs/dominio.md` (RN-37).

## Requirements

### Requirement: Contrato HTTP de exportación

La exportación SHALL estar disponible en `GET /tesoreria/exportar` con los parámetros `periodo` y `formato`. El período MUST ser obligatorio y normalizarse a `AAAA-MM`; un período inválido SHALL responder `400`. Un formato distinto de `csv` o `pdf` SHALL responder `400`.
Ref: RN-37.

#### Scenario: Período válido en CSV
- **WHEN** se solicita `GET /tesoreria/exportar?periodo=2026-10&formato=csv`
- **THEN** se devuelve la liquidación de octubre en formato CSV

#### Scenario: Período inválido
- **WHEN** se solicita la exportación con `periodo=2026-13`
- **THEN** la respuesta es `400` con un mensaje de período inválido

#### Scenario: Formato no soportado
- **WHEN** se solicita la exportación con `formato=xlsx`
- **THEN** la respuesta es `400` y no se genera ningún archivo

### Requirement: Una fila por designación

La liquidación mensual SHALL generar una fila por designación con las columnas Árbitro, Legajo, Partido, Rol, Honorario, Retención (10%), Viático y Neto a Cobrar, donde `neto = honorario - retención + viático`.
Ref: RN-37.

#### Scenario: Designación con honorario, retención y viático
- **WHEN** una designación del período tiene honorario `61000.00`, retención `6100.00` y viático `56664.00`
- **THEN** la fila muestra esos tres importes y un neto de `111564.00`

#### Scenario: Designación sin viático
- **WHEN** una designación del período no tiene movimiento de viático
- **THEN** la fila muestra viático `0.00` y el neto resulta del honorario menos la retención

### Requirement: Alcance de los movimientos exportados

La exportación SHALL considerar únicamente los conceptos `HONORARIO`, `RETENCION` y `VIATICO` del período. Los ajustes manuales y los reintegros por mora SHALL NOT formar parte de la liquidación mensual.
Ref: RN-37.

#### Scenario: Ajuste manual excluido
- **WHEN** el período tiene un ajuste `PAGO` registrado
- **THEN** ese ajuste no aparece en ninguna fila de la exportación

#### Scenario: Reintegro por mora excluido
- **WHEN** el período tiene un `AJUSTE` de reintegro por pago diferido en mora
- **THEN** el reintegro no forma parte de las columnas ni del neto exportado

#### Scenario: Solo movimientos del período
- **WHEN** se exporta `2026-10` y existen honorarios de septiembre y octubre
- **THEN** solo se incluyen las designaciones con movimientos de octubre

### Requirement: Fila de totales

La exportación SHALL incluir una fila `TOTAL` que sume honorarios, retenciones, viáticos y netos de todas las designaciones listadas.
Ref: RN-37.

#### Scenario: Totales de dos designaciones
- **WHEN** la liquidación incluye dos designaciones con netos `54900.00` y `111564.00`
- **THEN** la fila `TOTAL` muestra la suma de ambos netos y de cada columna

#### Scenario: Período sin movimientos
- **WHEN** se exporta un período sin honorarios, retenciones ni viáticos
- **THEN** el archivo contiene solo la fila `TOTAL` con importes en cero

### Requirement: Orden por apellido sin tildes

Las filas SHALL ordenarse por apellido y nombre del árbitro ignorando las tildes, de modo que el orden no dependa de la comparación por bytes de SQLite.
Ref: RN-37.

#### Scenario: Apellidos con tilde
- **WHEN** la liquidación incluye a `Ávila` y `Ayala`
- **THEN** `Ávila` aparece antes que `Ayala`, como si se comparara `Avila` con `Ayala`

#### Scenario: Mismo apellido y distinto nombre
- **WHEN** dos árbitros comparten apellido
- **THEN** se ordenan por nombre con la misma comparación sin tildes

### Requirement: Formato del archivo CSV

El CSV SHALL codificarse en `utf-8-sig` con BOM, SHALL usar punto y coma como separador de columnas y SHALL expresar los decimales con coma.
Ref: RN-37.

#### Scenario: BOM al inicio del archivo
- **WHEN** se descarga la liquidación en CSV
- **THEN** los primeros bytes del archivo son `EF BB BF`

#### Scenario: Importe con decimales con coma
- **WHEN** una fila tiene un neto de `15950.00`
- **THEN** el CSV contiene `15950,00` y usa `;` entre columnas

### Requirement: Formato del archivo PDF

El PDF SHALL generarse en A4 apaisado con membrete, SHALL repetir el encabezado de columnas en cada página y SHALL incluir una nota al pie con la fórmula del neto.
Ref: RN-37.

#### Scenario: PDF de varias páginas
- **WHEN** la liquidación supera una página
- **THEN** cada página muestra el encabezado de columnas y el membrete

#### Scenario: Nota de fórmula del neto
- **WHEN** se abre el PDF generado
- **THEN** el pie documenta `neto = honorario - retención + viático`

### Requirement: Nombre del archivo descargado

La respuesta SHALL incluir `Content-Disposition: attachment` con el nombre `liquidacion-AAAA-MM.csv` o `liquidacion-AAAA-MM.pdf` según el formato solicitado.
Ref: RN-37.

#### Scenario: Descarga CSV de octubre
- **WHEN** se exporta `2026-10` en CSV
- **THEN** la cabecera de descarga indica `attachment; filename="liquidacion-2026-10.csv"`

#### Scenario: Descarga PDF de octubre
- **WHEN** se exporta `2026-10` en PDF
- **THEN** la cabecera de descarga indica `attachment; filename="liquidacion-2026-10.pdf"`
