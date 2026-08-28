---
title: "Auditoría de Ventas y Cuenta Corriente"
mode: "AUDIT MODE + TEST MODE"
reset_db: true
---

# OBJETIVO

Auditar en profundidad el circuito comercial y verificar que las etapas estén realmente encadenadas, no simplemente presentes.

# ALCANCE

Clientes · productos · precios · listas de precios · pedidos · presupuestos · ventas · créditos · descuentos · promociones · devoluciones · notas de crédito y débito · vendedores · comisiones · cuenta corriente · límites de crédito · preventa.

# EL FLUJO A VERIFICAR

```
CLIENTE → PEDIDO → STOCK → PREPARACIÓN → ENTREGA → FACTURACIÓN → COBRO
```

Recorrelo entero con un caso real y, **entre cada par de etapas**, verificá con `db_query` que el estado se propagó. Las inconsistencias entre etapas son el hallazgo más valioso de esta misión.

# PRUEBAS OBLIGATORIAS

**Precios y descuentos**
- Un cliente con lista de precios especial, ¿ve su precio en el pedido y en la factura?
- Descuento por línea + descuento general: ¿el total cierra? Verificá la aritmética a mano.
- Redondeo: cargá cantidades y precios con decimales (ej. 3 × 1.333). ¿El total de la factura es la suma de las líneas o hay centavos que se pierden?
- Cambiar el precio de un producto **después** de cargado el pedido: ¿el pedido conserva el precio pactado o muta? (Que mute es un bug de negocio grave.)

**Crédito**
- Cliente con límite de crédito: vender por encima del límite.
- Cliente con factura vencida: intentar una venta nueva.
- ¿El límite considera pedidos pendientes o sólo facturado?

**Cuenta corriente**
- Después de facturar: ¿el saldo del cliente subió exactamente por el total facturado?
- Después de cobrar parcialmente: ¿el saldo bajó exactamente lo cobrado?
- Después de una nota de crédito: ¿el saldo se ajustó?
- Ecuación a verificar con `db_query`: `SUM(facturas) − SUM(cobros) − SUM(notas de crédito) = saldo del cliente`. Si no cierra, hallazgo crítico.

**Comisiones**
- ¿Se calculan sobre lo facturado o sobre lo cobrado? (En distribución esto importa mucho.)
- ¿Se revierten cuando hay devolución o nota de crédito?

**Integridad**
- Eliminar un cliente con operaciones históricas: ¿lo permite? ¿qué pasa con las facturas?
- Eliminar un producto vendido: ¿el histórico sobrevive?

# CRITERIO DE SALIDA

- Cada inconsistencia entre etapas registrada con la consulta SQL que la demuestra en `evidence`.
- Para todo hallazgo `CONFIRMADO` con pasos exactos, generá el test de regresión con `emit_regression_test`.
- Cerrá con un veredicto: ¿confiarías la facturación y la cuenta corriente de una distribuidora a este módulo? (🟢/🟡/🟠/🔴 + motivo).
