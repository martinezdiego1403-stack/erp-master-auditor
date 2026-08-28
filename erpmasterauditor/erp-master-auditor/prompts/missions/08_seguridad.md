---
title: "Auditoría de Seguridad, Permisos y Trazabilidad"
mode: "AUDIT MODE + CODE AUDIT MODE"
reset_db: true
---

# OBJETIVO

En una distribuidora el riesgo de seguridad no es un hacker: es el empleado que puede borrar un movimiento de caja, ajustar stock sin dejar rastro, o cambiar un precio para favorecer a un cliente. Auditá el sistema con esa lente.

# ALCANCE

Roles · permisos · acciones sensibles · auditoría / log de cambios · eliminaciones · modificaciones · acceso a información financiera · separación de responsabilidades.

# PRUEBAS

**Autenticación**
- ¿Hay login? ¿Contraseñas guardadas con hash? Revisalo en el código y en la base con `db_query` (si ves contraseñas en texto plano: `risk: 5`, `type: SECURITY`).
- ¿Hay usuario por defecto / hardcodeado? Buscalo con `Grep`.
- ¿Se puede saltear el login de alguna forma?

**Roles y permisos**
- ¿Existen roles diferenciados (vendedor, depósito, caja, administrador)?
- Entrá con el rol más bajo disponible e intentá llegar a: listado de costos, rentabilidad, caja, ajuste de stock, modificación de precios, eliminación de comprobantes.
- ¿Los permisos se validan en cada operación o sólo se ocultan opciones del menú? (Ocultar el menú no es un permiso. Buscá en el código si la validación está en la lógica o sólo en la UI.)

**Acciones sensibles — la lista que sí o sí debería estar controlada**
- Modificar un precio.
- Aplicar un descuento por encima de cierto porcentaje.
- Ajustar stock manualmente.
- Anular una factura.
- Eliminar cualquier comprobante.
- Modificar o eliminar un movimiento de caja.
- Cambiar el límite de crédito de un cliente.
- Reabrir una caja cerrada.

Para cada una: ¿la puede hacer cualquiera? ¿queda registrada con usuario, fecha y valor anterior? ¿requiere autorización de un superior?

**Trazabilidad**
- ¿Existe una tabla de auditoría? Buscala con `db_query`. Si no existe, es un hallazgo de alto impacto: sin traza no se puede investigar un faltante ni un desvío de caja.
- ¿Las eliminaciones son físicas o lógicas? Borrar físicamente un comprobante en un ERP es, además, un problema fiscal.

**Separación de responsabilidades**
- ¿La misma persona puede cargar una compra, recibirla y pagarla sin control cruzado?
- ¿La misma persona puede hacer una venta, cobrarla y anularla?

# CRITERIO DE SALIDA

Entregá dos listas:

1. **Operaciones que hoy no requieren autorización y deberían requerirla**, ordenadas por riesgo económico.
2. **Operaciones que hoy no dejan rastro y deberían dejarlo.**

Cada una como hallazgo, con la pérdida concreta que habilita en `business_need`.
