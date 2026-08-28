---
title: "Edge Case Engine — romper el ERP a propósito"
mode: "TEST MODE"
reset_db: true
---

# OBJETIVO

Buscar deliberadamente los bordes. No para hacer lucir mal al sistema, sino porque cada borde que encontrás acá es un borde que un empleado va a encontrar solo, un martes, con un cliente esperando.

**Buscá errores de negocio, no sólo errores técnicos.** Un crash es molesto. Una venta aceptada a un cliente bloqueado hace perder plata.

# BATERÍA A — LÍMITES DE NEGOCIO

- Stock = 0 y stock negativo (por todos los caminos posibles).
- Stock reservado > stock disponible.
- Venta que excede el límite de crédito.
- Devolución mayor a lo vendido.
- Devolución de un producto que ese cliente nunca compró.
- Pedido entregado parcialmente y después anulado.
- Producto eliminado que tiene historial de ventas.
- Cliente eliminado con operaciones abiertas.
- Precio modificado después de confirmado el pedido.
- Factura anulada después de cobrada.
- Cobro mayor al saldo adeudado.
- Pago parcial de una factura, y después otro pago que la excede.
- Doble confirmación de la misma operación (mandá la opción dos veces rápido).
- Cerrar caja dos veces el mismo día.

# BATERÍA B — ENTRADAS HOSTILES

Para cada campo de entrada que encuentres:

- Vacío (sólo Enter).
- Espacios en blanco.
- Cero y números negativos donde no corresponde.
- Decimales con muchos dígitos (0.000001) y números enormes (999999999999).
- Texto donde va número, y número donde va texto.
- Fechas imposibles (31/02, año 1900, año 2999).
- Cadenas muy largas (500 caracteres).
- Caracteres especiales y acentos: `ñ á ü ' " % _ ; -- < >`.
- IDs / códigos inexistentes.
- ESC o cancelar en medio de un flujo de varios pasos.

**Lo que buscás no es sólo el crash.** Buscás: mensajes de error incomprensibles, datos que se guardan mal, flujos abandonados que dejan registros huérfanos, y validaciones que existen en una pantalla pero no en otra que hace lo mismo.

# BATERÍA C — CANCELACIÓN Y ESTADO INTERMEDIO

Ésta es la que más bugs encuentra en ERPs jóvenes:

- Empezá una venta, cargá 2 líneas, y cancelá antes de confirmar. Verificá con `db_query` que **no quedó nada**: ni cabecera huérfana, ni stock reservado, ni numeración consumida.
- Lo mismo con una compra, una transferencia y un cobro.
- Cortá el proceso a mitad (`ctrl+c` si el backend es pty, o cerrando con `erp_stop`) durante una operación, reiniciá y verificá el estado de los datos.

# PROTOCOLO

- Trabajá con `reset_db` frecuente: esta misión ensucia los datos a propósito.
- **Registrá siempre la secuencia exacta de inputs**, porque casi todo lo de esta misión debería terminar en un test de regresión.
- Para cada hallazgo confirmado con pasos exactos, llamá a `emit_regression_test` con el `expect_pattern` de lo que el ERP *debería* responder cuando esté arreglado.
- Si el ERP crashea: `type: BUG`, `risk: 5`, secuencia exacta, y el stack trace si lo imprime.

# CRITERIO DE SALIDA

Cerrá con: cuántos bordes probaste, cuántos manejó bien, cuántos manejó mal, cuántos lo rompieron, y cuál es el patrón común de las fallas (¿falta validación centralizada? ¿falta transaccionalidad? ¿falta manejo de excepciones?). Ese patrón común suele valer más que la lista de bugs individuales.
