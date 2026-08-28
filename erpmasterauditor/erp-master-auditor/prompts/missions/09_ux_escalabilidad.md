---
title: "Auditoría de UX de consola y Escalabilidad"
mode: "AUDIT MODE + CODE AUDIT MODE"
reset_db: false
---

# OBJETIVO

Dos preguntas: ¿puede un empleado nuevo usar esto bien después de una capacitación razonable? Y ¿a partir de qué tamaño de empresa este ERP empieza a estorbar?

# PARTE A — UX DE CONSOLA

La UX en consola no es "que sea lindo". Es cuántas teclas cuesta la operación que se hace 200 veces por día.

**Medí lo que más se usa.** Para las 5 operaciones más frecuentes de una distribuidora (cargar un pedido, consultar stock, consultar precio, cobrar, consultar saldo de cliente):
- Cantidad de pantallas atravesadas.
- Cantidad de teclas / inputs.
- ¿Hay atajo directo o hay que navegar el árbol de menús cada vez?

**Navegación**
- ¿Se puede volver atrás desde cualquier pantalla? ¿Con qué tecla? ¿Es la misma tecla en todas las pantallas? (La inconsistencia acá genera errores de carga reales.)
- ¿Salir por accidente pierde lo cargado?
- ¿Hay forma de cancelar un flujo largo sin cerrar el programa?

**Mensajes**
- Provocá varios errores. Para cada mensaje evaluá: ¿dice qué pasó? ¿dice qué hacer? ¿está en el idioma del usuario? ¿o muestra una excepción técnica?
- ¿Los mensajes de éxito confirman **qué** se hizo (número de comprobante, total) o sólo dicen "OK"?

**Entrada de datos**
- ¿Se puede buscar un producto por descripción o hay que saber el código de memoria?
- ¿Hay autocompletado o selección de lista?
- ¿Los campos tienen valor por defecto sensato?
- ¿Se puede cargar un pedido de 20 líneas sin que sea una tortura?

**Test del empleado nuevo:** recorré el sistema como alguien que nunca lo vio y anotá cada punto donde te quedarías trabado sin que alguien te explique.

# PARTE B — ESCALABILIDAD

Simulá mentalmente y verificá en el código y en la base:

| Escala | Productos | Clientes | Pedidos/día | Usuarios simultáneos |
|---|---|---|---|---|
| ×1 (hoy) | 500 | 100 | 20 | 2 |
| ×5 | 2.500 | 500 | 100 | 10 |
| ×10 | 5.000 | 1.000 | 200 | 20 |
| ×50 | 25.000 | 5.000 | 1.000 | 50 |

**Qué buscar en el código (`Grep`/`Read`):**
- Listados sin paginación: pantallas que hacen `SELECT *` de una tabla entera.
- Búsquedas lineales en memoria en vez de consultas con índice.
- Consultas dentro de bucles (problema N+1).
- Cargas completas de catálogos al iniciar.
- Falta de índices en las columnas por las que se filtra.
- Concurrencia: ¿hay transacciones? ¿hay bloqueo optimista? ¿dos usuarios pueden vender el mismo último producto?
- Numeración de comprobantes: ¿cómo se genera? Si es `MAX(numero)+1` sin bloqueo, con dos usuarios se duplican números — hallazgo crítico y frecuente.

**Prueba práctica:** si podés, cargá muchos registros con `db_query`… no, no podés escribir. Entonces medí el tiempo de respuesta de los listados existentes y extrapolá según el tipo de consulta que hace el código.

# CRITERIO DE SALIDA

1. Tabla de las 5 operaciones frecuentes con su costo en pasos, y cuáles deberían optimizarse.
2. **El techo:** a qué escala aparece el primer cuello de botella, cuál es, y en qué línea del código está.
3. Lista de riesgos de concurrencia, con el fragmento de código que los origina en `evidence`.
