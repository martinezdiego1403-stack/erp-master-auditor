---
title: "Auditoría de Logística y Distribución"
mode: "AUDIT MODE + BUSINESS SIMULATION MODE"
reset_db: true
---

# OBJETIVO

Determinar si el ERP soporta realmente la operación física de la distribución, o si termina en la factura y deja el reparto a mano.

# EL FLUJO A VERIFICAR

```
PEDIDO → PICKING → PACKING → DESPACHO → TRANSPORTE → ENTREGA
```

Recorrelo con pedidos reales. Para cada eslabón determiná: ¿existe? ¿cambia el estado del pedido? ¿queda registrado quién y cuándo?

# ALCANCE

Picking · packing · preparación · despacho · rutas · vehículos · repartidores · zonas · entregas · entregas parciales · rechazos · devoluciones en ruta · costos logísticos.

# PRUEBAS

- **Hoja de trabajo del depósito.** ¿Existe una lista de "qué hay que preparar hoy", ordenada de forma útil (por ubicación, por ruta)? Sin esto, el depósito trabaja con papeles impresos y el ERP no sirve para operar.
- **Armado de reparto.** Asignar varios pedidos a un vehículo y un repartidor. ¿Hay control de capacidad (peso, volumen, bultos)? ¿Existe el concepto de zona?
- **Estados.** Seguí un pedido por todos sus estados. ¿Se puede saber en cualquier momento dónde está? ¿Se puede retroceder un estado si hubo error?
- **Entrega parcial.** Entregar 8 de 10 unidades en el domicilio: ¿el sistema lo contempla, o hay que anular todo y rehacer?
- **Rechazo.** El cliente no recibe. ¿El stock vuelve al depósito? ¿Qué pasa con la factura ya emitida? Verificá con `db_query`.
- **Reasignación.** Vehículo roto: mover un reparto armado a otro vehículo.
- **Costos.** ¿Se puede saber cuánto costó entregar? ¿Hay costo por viaje, por km, por bulto?
- **Trazabilidad.** ¿Queda registro de quién preparó, quién despachó y quién entregó? En una distribuidora, esto es lo que permite resolver un faltante reclamado por el cliente.

# ESCALA

Repetí el armado de reparto pensando en la empresa mediana (10 vehículos, 10 vendedores). ¿La pantalla sigue siendo usable con 60 pedidos pendientes? ¿Hay filtros y búsqueda o hay que scrollear?

# CRITERIO DE SALIDA

- Mapa de qué eslabones del flujo existen realmente, cuáles son parciales y cuáles faltan.
- Para cada faltante: qué hace hoy la empresa en su lugar (papel, WhatsApp, Excel) y qué riesgo genera.
- Veredicto de confianza del módulo.
