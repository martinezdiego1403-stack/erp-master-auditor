---
title: "Prueba Día Caótico — todo lo que sale mal en una distribuidora real"
mode: "BUSINESS SIMULATION MODE"
reset_db: true
---

# OBJETIVO

Un ERP se juzga por cómo maneja el día malo, no el día perfecto. Metele al sistema las catorce situaciones que en una distribuidora pasan todas las semanas.

# LAS SITUACIONES

Ejecutá cada una y determiná si el ERP la resuelve, la resuelve mal, o directamente no la contempla:

1. **Producto sin stock.** Cargar un pedido de algo con stock 0. ¿Avisa? ¿Deja seguir? ¿Permite pedido pendiente / backorder?
2. **Cliente moroso.** Vender a un cliente con saldo vencido. ¿Bloquea? ¿Avisa y deja seguir con autorización? ¿No dice nada?
3. **Pedido urgente.** ¿Se puede priorizar un pedido sobre los demás en la preparación/reparto?
4. **Devolución parcial.** Devolver 3 de 10 unidades. Verificá con `db_query`: stock, nota de crédito, cuenta corriente.
5. **Error de vendedor.** Modificar o anular un pedido ya confirmado. ¿Queda rastro? ¿Se revierte el stock reservado?
6. **Error de depósito.** Se despachó un producto por otro. ¿Hay forma de corregirlo sin romper la trazabilidad?
7. **Diferencia de caja.** Cerrar caja con un faltante. ¿Lo permite? ¿Lo registra? ¿Pide justificación?
8. **Producto vencido.** ¿Existe control de vencimiento? ¿Se puede bloquear un lote?
9. **Producto dañado.** Dar de baja mercadería rota. ¿Impacta el costo? ¿Queda auditado?
10. **Vehículo fuera de servicio.** Reasignar un reparto ya armado.
11. **Entrega rechazada.** El cliente no recibe. ¿Vuelve el stock? ¿Qué pasa con la factura?
12. **Precio incorrecto.** Se facturó con precio viejo. ¿Nota de crédito y refacturación, o edición directa (que sería grave)?
13. **Proveedor entrega menos.** Recepción parcial de una orden de compra. ¿Queda el saldo pendiente?
14. **Pedido parcialmente preparado.** Entregar 8 de 10 unidades. ¿Factura por 8? ¿Queda pendiente por 2?

# PROTOCOLO

- Una situación por vez, arrancando de un estado conocido cuando haga falta (`erp_start` con `reset_db=1` si una situación dejó los datos sucios).
- **Verificá siempre el efecto en datos.** La mayoría de los bugs graves de esta misión no se ven en pantalla: se ven cuando el stock o la cuenta corriente quedan mal después de una operación excepcional.
- Prestá especial atención a las **reversiones**: anular, devolver, rechazar y corregir son las operaciones donde los ERP jóvenes fallan sistemáticamente, porque el camino feliz se prueba y el camino de vuelta no.
- Cada situación no contemplada es un hallazgo con `business_need` explicando qué le pasa a la empresa cuando ocurre y el ERP no la soporta.

# CRITERIO DE SALIDA

Terminá con una tabla de las 14 situaciones (RESUELVE / RESUELVE MAL / NO CONTEMPLA) y, para las que resuelve mal, una línea de qué queda inconsistente en los datos.

Si encontrás alguna que deje los datos en estado inconsistente, ese hallazgo va con `type: DATA_INTEGRITY` y `risk: 5`.
