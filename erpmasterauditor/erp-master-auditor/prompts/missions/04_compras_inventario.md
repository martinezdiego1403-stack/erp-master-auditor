---
title: "Auditoría de Compras e Inventario"
mode: "AUDIT MODE + TEST MODE"
reset_db: true
---

# OBJETIVO

Verificar que el inventario sea **confiable**. Un ERP cuyo stock no coincide con el depósito es peor que no tener ERP, porque la gente toma decisiones creyendo en un número falso.

# PARTE A — COMPRAS

Alcance: proveedores · solicitudes · órdenes de compra · recepción · costos · facturación de compra · actualización de precios · historial de costos · devoluciones a proveedor · pagos · cuenta corriente de proveedor.

Pruebas:

- Circuito completo `ORDEN → RECEPCIÓN → FACTURA → PAGO`. ¿Están encadenados o son módulos sueltos?
- **Recepción parcial**: recibir 60 de 100 unidades. ¿Queda saldo pendiente en la orden?
- **Recepción de más**: recibir 120 de 100. ¿Lo permite? ¿Avisa?
- **Costo**: al recibir, ¿se actualiza el costo del producto? ¿Qué método usa (último, promedio ponderado, FIFO)? Verificá el cálculo con `db_query` sobre dos compras a precios distintos.
- **Historial de costos**: ¿se puede saber a qué costo se compró hace tres meses?
- ¿El sistema puede responder **qué comprar, cuánto, cuándo y a quién**? Si no hay sugerencia de compra basada en stock mínimo y rotación, es un faltante importante (`category: EXPECTED`).

# PARTE B — INVENTARIO

Alcance: stock · disponible · reservado · mínimo · máximo · depósitos · transferencias · ajustes · inventario físico · lotes · vencimientos · trazabilidad · rotación · inmovilizados.

**La ecuación maestra.** Después de un ciclo completo de operaciones, verificá con `db_query`:

```
stock_inicial + compras + devoluciones_de_cliente
             − ventas − devoluciones_a_proveedor ± ajustes = stock_actual
```

Si no cierra, ese es el hallazgo más importante de toda la auditoría. Documentá el desvío exacto y en qué operación se originó.

Otras pruebas:

- **Stock reservado.** Confirmar un pedido, ¿reserva? Anularlo, ¿libera? Dos pedidos simultáneos del último producto: ¿el sistema deja vender dos veces lo mismo?
- **Stock negativo.** ¿Se puede llegar a stock negativo? ¿Por qué camino? ¿Está permitido conscientemente o es un agujero?
- **Multi-depósito.** Transferencia entre depósitos: ¿el total se conserva? ¿Hay estado "en tránsito" o la mercadería se teletransporta?
- **Ajuste manual.** ¿Requiere motivo? ¿Queda auditado con usuario y fecha? Un ajuste de stock sin traza es un riesgo de fraude interno (`type: SECURITY`).
- **Inventario físico.** ¿Existe el proceso de conteo y ajuste masivo?
- **Lotes y vencimientos.** ¿Existen? ¿Se puede vender un lote vencido?

# CRITERIO DE SALIDA

- Reportá el resultado de la ecuación maestra con los números concretos.
- Generá tests de regresión para todo camino confirmado que produzca stock inconsistente.
- Veredicto de confianza para Compras e Inventario por separado.
