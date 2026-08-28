---
title: "Fase 0 — Descubrimiento del sistema"
mode: "CODE AUDIT MODE + AUDIT MODE"
reset_db: true
---

# OBJETIVO

Construir el mapa real del ERP antes de emitir cualquier juicio. Al terminar esta misión, las misiones siguientes tienen que poder navegar el sistema sin adivinar.

Esta misión **no busca bugs**. Busca entender.

# PROTOCOLO

1. **Código primero.** Con `Glob` y `Grep` sobre el código fuente, identificá: lenguaje y versión, estructura de carpetas, punto de entrada, capas (UI de consola / lógica / datos), motor de base de datos, ORM o acceso a datos, manejo de configuración, autenticación, y si existen tests.

2. **Esquema de datos.** Si `db_query` está habilitado, listá tablas y columnas principales. Esto te dice qué módulos existen *de verdad*, mucho mejor que los menús. Un menú "Logística" sin tablas de rutas ni entregas es una etiqueta, no un módulo.

3. **Recorrido de menús.** `erp_start`, y recorré el árbol de menús **sin ejecutar operaciones destructivas ni completar flujos**: entrá, anotá las opciones, volvé atrás. Registrá la ruta de teclas para llegar a cada pantalla — las misiones siguientes van a usar ese mapa.

4. **Contrastá las tres fuentes.** Menú vs código vs base. Donde no coincidan, hay algo interesante: una opción de menú sin código detrás, tablas sin pantalla que las use, código sin acceso desde ningún menú.

# QUÉ REGISTRAR

Usá `record_map` (uno por cada uno):

- `kind: arquitectura` — stack, capas, base de datos, dependencias externas, cómo arranca.
- `kind: modulos` — lista de módulos **reales** con el estado inicial de cada uno: ¿tiene menú? ¿tiene tablas? ¿tiene código? Marcá EXISTE / PARCIAL / SOLO_ETIQUETA / NO_EXISTE.
- `kind: datos` — tablas principales y sus relaciones, en especial las que unen módulos (pedido↔stock, venta↔cuenta corriente, compra↔costo).
- `kind: dependencias` — el mapa `CLIENTE → PEDIDO → VENTA → STOCK → ... → FINANZAS` marcando qué eslabones están realmente conectados en el código/datos y cuáles están rotos o ausentes.
- `kind: notas` — la ruta de teclas de cada pantalla relevante, para las próximas misiones.

# HALLAZGOS EN ESTA FASE

Sólo registrá hallazgos de tipo estructural, con `report_finding`:

- Módulos ausentes que un ERP de distribución necesita sí o sí.
- Módulos que existen en el menú pero no tienen soporte real en datos o código (`type: MISSING` o `PARTIAL`, `evidence_level` según lo que hayas podido probar).
- Eslabones rotos del mapa de dependencias (`type: DATA_INTEGRITY` o `RISK`).

No reportes bugs de comportamiento acá: eso es trabajo de las misiones siguientes.

# CRITERIO DE SALIDA

Terminá cuando puedas responder, con evidencia: *¿qué módulos tiene este ERP, cuáles están conectados entre sí, y por dónde se llega a cada uno desde la consola?*

Cerrá con un resumen en prosa de 15–25 líneas: qué es este ERP, qué cubre, qué no cubre, y cuáles son las tres cosas que más te preocupan de entrada.
