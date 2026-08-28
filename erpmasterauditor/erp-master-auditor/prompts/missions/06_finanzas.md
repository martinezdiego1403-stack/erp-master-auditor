---
title: "Auditoría Financiera"
mode: "AUDIT MODE + TEST MODE"
reset_db: true
---

# OBJETIVO

Responder las seis preguntas que todo dueño de distribuidora se hace, y verificar que las respuestas del ERP sean **correctas**, no sólo que existan.

> ¿Cuánto dinero tengo? · ¿Cuánto me deben? · ¿Cuánto debo? · ¿Cuánto voy a cobrar? · ¿Cuánto voy a pagar? · ¿Cuánto gano realmente?

# ALCANCE

Caja · ingresos · egresos · cobros · pagos · deudas · vencimientos · cuenta corriente · cuentas por cobrar y por pagar · flujo de caja · rentabilidad · costos · márgenes.

# PRUEBAS

**Caja**
- Apertura, movimientos y cierre de un día completo.
- ¿Soporta múltiples medios de pago (efectivo, transferencia, cheque, tarjeta)? ¿Los separa?
- Cierre con diferencia: ¿lo detecta, lo permite, lo registra con motivo?
- Ecuación: `saldo_inicial + ingresos − egresos = saldo_final`. Verificala con `db_query` después de un día simulado.
- ¿Se puede modificar un movimiento de caja ya cerrado? Si sí, es un riesgo de fraude (`type: SECURITY`, `risk: 5`).

**Cuentas por cobrar**
- Listado de deuda por cliente con antigüedad (0-30, 31-60, 61-90, +90).
- ¿Distingue vencido de a vencer?
- ¿El total de la cuenta corriente coincide con la suma de comprobantes impagos?

**Cuentas por pagar**
- Lo mismo del lado proveedores. ¿Hay agenda de vencimientos?

**Flujo de caja proyectado**
- ¿Puede decir cuánto va a entrar y salir las próximas 4 semanas según vencimientos? Si no existe, es un faltante de alto impacto para la toma de decisiones (`category: EXPECTED`).

**Rentabilidad — el punto más delicado**
- ¿Calcula margen por producto? ¿Con qué costo (último, promedio, FIFO)?
- ¿El margen considera descuentos aplicados en la venta?
- ¿Considera costos indirectos (flete, logística)?
- Hacé una venta con descuento y verificá a mano el margen que reporta el sistema. **Un ERP que reporta un margen equivocado es peligroso: hace vender a pérdida creyendo que se gana.**
- ¿Hay rentabilidad por cliente, por vendedor, por zona?

**Consistencia global**
- Ecuación cruzada: `ventas facturadas − cobros = saldo total de clientes`. Debe cerrar exacto.

# CRITERIO DE SALIDA

- Respondé explícitamente las seis preguntas del dueño: ¿puede el ERP contestarlas, con qué precisión y qué le falta?
- Todo desvío aritmético va con `risk: 5` y la consulta que lo demuestra.
- Veredicto de confianza del módulo financiero.
