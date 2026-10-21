# Canchas, torneos y categorías

## Purpose

Define el ABM de canchas y torneos con baja lógica, el catálogo de categorías de torneo y los litros de viático fijados por localidad. Estos datos son la base de la programación de partidos y del cálculo del viático.
Fuente: `docs/dominio.md` (RN-12, RN-36).

## Requirements

### Requirement: ABM de canchas con baja lógica

El sistema SHALL permitir dar de alta y editar canchas, y SHALL dar de baja mediante `activo=False`. Una cancha con historia SHALL NOT borrarse físicamente.
Ref: RN-36.

#### Scenario: Baja de una cancha
- **WHEN** el tesorero da de baja una cancha usada en partidos anteriores
- **THEN** la cancha queda con `activo=False` y sus datos siguen existiendo para el historial

#### Scenario: Edición de una cancha
- **WHEN** se modifica la dirección o la localidad de una cancha existente
- **THEN** el cambio se guarda sin crear un registro nuevo

#### Scenario: Borrado físico de una cancha
- **WHEN** se intenta eliminar definitivamente una cancha que tiene partidos asociados
- **THEN** la operación se rechaza y la cancha conserva su registro

### Requirement: Litros de viático por localidad

Cada cancha SHALL tener `litros_viatico` mayor o igual a `0`, con valor por defecto `0`, fijado por la planilla oficial para su localidad. Los litros SHALL NOT derivarse de kilómetros ni de un rendimiento supuesto.
Ref: RN-12.

#### Scenario: Cancha con litros de la planilla
- **WHEN** se registra una cancha de Tunuyán con `24` litros
- **THEN** el viático de un partido en esa cancha se calcula como `24 × precio_litro` de la fecha del partido

#### Scenario: Cancha sin viático
- **WHEN** se registra una cancha sin litros asignados
- **THEN** queda con `litros_viatico = 0` y no genera viático al liquidar

#### Scenario: Litros negativos
- **WHEN** se intenta guardar una cancha con `litros_viatico` negativo
- **THEN** la operación se rechaza con error de validación

### Requirement: ABM de torneos con baja lógica

El sistema SHALL permitir dar de alta y editar torneos, y SHALL darlos de baja mediante `activo=False`, sin borrado físico. Todo torneo MUST referenciar una categoría de torneo existente.
Ref: RN-36.

#### Scenario: Baja de un torneo
- **WHEN** el tesorero da de baja un torneo con partidos históricos
- **THEN** el torneo queda inactivo y sus partidos asociados se conservan

#### Scenario: Torneo con categoría inexistente
- **WHEN** se intenta crear un torneo con una categoría que no existe
- **THEN** el alta se rechaza por integridad referencial

#### Scenario: Edición de temporada
- **WHEN** se corrige la temporada de un torneo existente
- **THEN** el torneo se actualiza sin perder su categoría ni sus partidos

### Requirement: Catálogo de categorías de torneo

Las categorías de torneo SHALL ser un catálogo con `nombre` único, `orden` y `activo`, e SHALL incluir las divisiones de Inferiores `U23`, `U19`, `JUVENILES`, `CADETES`, `INFANTILES`, `U11_DOBLE`, `U11` y `U9`. La categoría de un partido SHALL obtenerse desde su torneo y SHALL NOT duplicarse en el partido.
Ref: RN-36.

#### Scenario: Nombre de categoría duplicado
- **WHEN** se intenta crear una categoría con un nombre ya existente
- **THEN** el alta se rechaza por unicidad

#### Scenario: Categoría de Inferiores disponible
- **WHEN** se consulta el catálogo de categorías
- **THEN** aparecen las divisiones de Inferiores con su orden y estado

#### Scenario: Categoría del partido
- **WHEN** se registra un partido de un torneo de categoría `CADETES`
- **THEN** la categoría del partido se lee desde el torneo y no se guarda una copia en el partido
