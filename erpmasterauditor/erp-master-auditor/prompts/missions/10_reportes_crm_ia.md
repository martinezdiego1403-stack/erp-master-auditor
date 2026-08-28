---
title: "Auditoría de Reportes, CRM y oportunidades de automatización / IA"
mode: "AUDIT MODE + PRODUCT MODE"
reset_db: false
---

# OBJETIVO

Determinar si el ERP sirve para **decidir**, no sólo para registrar. Y detectar qué se puede automatizar antes de pensar en IA.

# PARTE A — REPORTES

Inventariá qué reportes existen realmente (ejecutalos, no los cuentes desde el menú) sobre: ventas, compras, stock, rentabilidad, margen, clientes, productos, vendedores, proveedores, caja, finanzas, logística.

Para cada reporte **que existe**: ¿los números son correctos? Verificá al menos dos contra `db_query`.

Para cada reporte **que falta**, usá exactamente este formato en el hallazgo:

> **Reporte faltante → Decisión que permitiría tomar → Impacto empresarial**

Los que casi siempre faltan y más duelen en distribución: ranking de productos por rotación, productos sin movimiento (capital inmovilizado), clientes que dejaron de comprar, margen por cliente, cumplimiento de entrega, y quiebres de stock (ventas perdidas por falta de mercadería).

# PARTE B — CRM

Alcance: historial de compras · frecuencia · ticket promedio · clientes inactivos · clientes frecuentes · segmentación · seguimiento · oportunidades · riesgo de abandono.

Preguntas:
- ¿Se puede saber qué compra habitualmente un cliente, para que el vendedor le ofrezca lo que le falta?
- ¿Se puede detectar que un cliente que compraba todas las semanas hace un mes que no compra? **Ésta es la funcionalidad de mayor retorno y menor costo en un ERP de distribución** — si no está, es una oportunidad de alto valor.
- ¿Hay registro de contactos, visitas, motivos de no compra?

Determiná: ¿puede este ERP pasar de administrativo a herramienta comercial, y qué le falta para eso?

# PARTE C — AUTOMATIZACIÓN

Detectá procesos automatizables y clasificalos. Para cada uno:
`PROCESO → PROBLEMA → SOLUCIÓN → BENEFICIO → COMPLEJIDAD → PRIORIDAD`

- **SIMPLE** — reglas, validaciones y alertas. (Ej: avisar stock bajo mínimo, alertar cliente que superó su límite, recordar vencimientos.)
- **AVANZADA** — automatización entre módulos. (Ej: generar orden de compra sugerida desde el stock mínimo y las ventas del período.)
- **IA** — predicción, recomendaciones, detección de patrones.

Registralos con `report_finding` usando `type: OPPORTUNITY` y el campo `automation` correspondiente.

# PARTE D — IA (con criterio)

Evaluá oportunidades reales: forecast de demanda, compras inteligentes, reposición, proyección de flujo de caja, scoring de riesgo de clientes, detección de anomalías, recomendaciones de venta cruzada, asistente en lenguaje natural sobre los datos del ERP, optimización de rutas.

**Regla dura: no recomiendes IA cuando una regla tradicional resuelve mejor el problema.** Un punto de reposición calculado como `consumo_promedio × lead_time + stock_seguridad` le sirve al 90% de las distribuidoras y no necesita un modelo. Si proponés IA, justificá por qué la regla no alcanza y qué datos históricos harían falta (si el ERP todavía no los acumula, decilo: la IA sin datos es una promesa vacía).

# CRITERIO DE SALIDA

1. Tabla de reportes: existe y correcto / existe pero incorrecto / falta.
2. Los 5 reportes faltantes de mayor impacto, ordenados.
3. Backlog de automatización clasificado SIMPLE / AVANZADA / IA, con las SIMPLE arriba — son las que dan retorno inmediato.
4. Qué funcionalidades podrían ser **DIFFERENTIATOR** o **INNOVATION** frente a los ERPs que compiten en este segmento.
