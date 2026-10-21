# Auditoría de operaciones sensibles

## Purpose

Esta capacidad registra quién ejecutó cada operación con impacto financiero o contable: movimientos de cuenta corriente, reintegros, ajustes manuales y cierres de período. También mantiene un historial append-only de cierres y reaperturas que permite reconstruir las decisiones sobre cada período. Existe para que el circuito de tesorería sea trazable y para que ninguna operación sensible quede sin responsable identificable.
Fuente: `docs/specs/v2_seguridad_auditoria.md` (F3, F5) y `docs/dominio.md` (RN-49, RN-50, §4.5).

## Requirements

### Requirement: Identificación del usuario en movimientos y cierres

`MovimientoCuentaCorriente` y `CierrePeriodo` SHALL tener una columna `usuario_id` nullable, con clave foránea a `usuario.id` y `ON DELETE RESTRICT`, que identifique al operador que creó el registro. La columna SHALL permanecer nullable para ser compatible con los datos históricos anteriores a la auditoría, y la relación SHALL exponer el usuario para mostrarlo en la interfaz.
Ref: F3, RN-49.

#### Scenario: Liquidación auditada
- **WHEN** un tesorero autenticado con `usuario_id=7` liquida un partido que genera honorario, retención y viático
- **THEN** todos los movimientos creados quedan con `usuario_id=7`

#### Scenario: Cierre auditado
- **WHEN** un tesorero autenticado con `usuario_id=7` cierra el período `2026-03`
- **THEN** el `CierrePeriodo` de `2026-03` queda con `usuario_id=7`

#### Scenario: Movimiento histórico sin usuario
- **WHEN** existe un movimiento previo a la auditoría con `usuario_id` nulo
- **THEN** la fila se conserva y se puede consultar sin errores, con la columna de usuario vacía

### Requirement: Cobertura de los servicios de escritura auditados

Los servicios de escritura SHALL aceptar un `usuario_id` opcional y persistirlo en cada registro que generen. La cobertura MUST incluir los movimientos de liquidación (`HONORARIO`, `RETENCION`, `VIATICO`), el reintegro por mora (`AJUSTE`), los ajustes manuales y el cierre de período. Cuando el servicio se invoca sin `usuario_id`, el registro SHALL crearse con `NULL` para no romper procesos históricos o de mantenimiento.
Ref: F3, RN-49.

#### Scenario: Reintegro por mora auditado
- **WHEN** un tesorero registra el cobro de un partido diferido en mora y se genera un `AJUSTE` de reintegro
- **THEN** el movimiento de reintegro guarda el `usuario_id` del tesorero

#### Scenario: Ajuste manual auditado
- **WHEN** un tesorero carga un descuento, adelanto, pago, multa o ajuste desde el panel
- **THEN** el movimiento manual queda con el `usuario_id` del tesorero y sin `designacion_id`

#### Scenario: Servicio sin usuario explícito
- **WHEN** un servicio de escritura se invoca con `usuario_id=None`
- **THEN** el movimiento o cierre se crea con `usuario_id` nulo y la operación no falla por esa causa

### Requirement: Origen confiable del usuario auditado

Las rutas SHALL obtener el usuario de la dependencia de autenticación del rol (`Depends(requiere_tesorero)`) y MUST NOT tomar un `usuario_id` desde el formulario, query string, cabecera o cuerpo de la petición. Un valor de usuario enviado por el cliente SHALL ignorarse aunque esté presente en el formulario.
Ref: F3, RN-49.

#### Scenario: Usuario falsificado en el formulario
- **WHEN** un tesorero autenticado con `usuario_id=7` envía un ajuste con un campo `usuario_id=999`
- **THEN** el movimiento se persiste con `usuario_id=7` y el valor 999 se descarta

#### Scenario: Operación sin sesión
- **WHEN** un cliente anónimo intenta liquidar un partido o cargar un ajuste
- **THEN** la guarda responde 303 a `/login` y no se crea ningún movimiento

### Requirement: Visualización del usuario que registró

El detalle de cuenta del tesorero SHALL mostrar la columna **Registró** con el usuario que creó cada movimiento. Para los movimientos históricos con `usuario_id` nulo la columna MUST mostrar `—` sin generar errores ni respuestas 500.
Ref: F3, RN-49.

#### Scenario: Columna Registró con usuario
- **WHEN** se consulta `/tesoreria/arbitros/{id}` para un movimiento creado por el tesorero `Pérez, Ana`
- **THEN** la fila muestra esa identidad en la columna **Registró**

#### Scenario: Columna Registró con dato histórico
- **WHEN** el detalle incluye un movimiento con `usuario_id` nulo
- **THEN** la columna **Registró** muestra `—` y la página responde 200

### Requirement: Integridad referencial de la auditoría

Las claves foráneas de `usuario_id` SHALL usar `ON DELETE RESTRICT` para impedir que se borre un usuario con movimientos o cierres registrados. El borrado de un usuario referenciado MUST fallar y SHALL NOT alterar ni dejar huérfanas las filas auditadas.
Ref: F3, RN-49.

#### Scenario: Borrado de usuario con operaciones
- **WHEN** se intenta eliminar un usuario que tiene al menos un movimiento o un cierre asociado
- **THEN** la base rechaza la operación por la FK `RESTRICT` y las filas auditadas permanecen intactas

#### Scenario: Integridad del cierre auditado
- **WHEN** se intenta eliminar al tesorero que figura en un `CierrePeriodo`
- **THEN** el borrado falla y el cierre conserva su `usuario_id`

### Requirement: Historial append-only de cierres y reaperturas

El sistema SHALL mantener `auditoria_periodo` con `id`, `periodo` `AAAA-MM`, `accion` (`CIERRE` o `REAPERTURA`), `motivo`, `usuario_id` con FK `RESTRICT` y marcas de tiempo. La tabla SHALL ser append-only: sus filas MUST NOT actualizarse ni borrarse, y cada cierre o reapertura MUST agregar una fila con período, acción, usuario y fecha. Un cierre repetido de un período ya cerrado SHALL NOT auditarse dos veces.
Ref: F3, F5, RN-50.

#### Scenario: Reapertura auditada
- **WHEN** el tesorero reabre `2026-03` con un motivo válido
- **THEN** se agrega una fila `REAPERTURA` con `periodo=2026-03`, el motivo, el `usuario_id` del tesorero y la fecha de la operación

#### Scenario: Cierre auditado en el historial
- **WHEN** el tesorero cierra el período `2026-04`
- **THEN** se agrega una fila `CIERRE` con `periodo=2026-04`, el `usuario_id` del tesorero y la fecha del cierre

#### Scenario: Cierre duplicado sin doble auditoría
- **WHEN** se intenta cerrar un período que ya tiene un cierre vigente
- **THEN** la operación informa que ya estaba cerrado y no agrega una segunda fila de auditoría para ese cierre

#### Scenario: Historial preservado en el ciclo completo
- **WHEN** se ejecuta cierre, luego reapertura y luego un nuevo cierre del mismo período
- **THEN** el historial contiene exactamente `[CIERRE, REAPERTURA, CIERRE]` y las filas anteriores conservan su motivo, usuario y fecha

#### Scenario: Formato de período validado
- **WHEN** se intenta insertar una fila de auditoría con un período que no tiene formato `AAAA-MM`
- **THEN** la restricción de la tabla rechaza el registro

### Requirement: Historial de auditoría visible en el panel

El panel de tesorería SHALL mostrar los últimos 10 registros de `auditoria_periodo`, ordenados del más reciente al más antiguo, con período, acción, motivo y usuario. La visualización MUST ser de solo lectura y SHALL NOT ofrecer acciones para editar ni eliminar registros.
Ref: F5, RN-50.

#### Scenario: Últimos diez registros
- **WHEN** existen 12 registros de auditoría y el tesorero abre el panel
- **THEN** se muestran los 10 más recientes en orden descendente y no los 2 más antiguos

#### Scenario: Detalle de una reapertura
- **WHEN** el panel muestra una fila `REAPERTURA`
- **THEN** se ven el período, el motivo completo y el usuario que la ejecutó
