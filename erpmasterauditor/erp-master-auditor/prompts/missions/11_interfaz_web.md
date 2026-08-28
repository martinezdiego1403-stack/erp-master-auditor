---
title: "Auditoría de la interfaz web — el día a día del empleado"
mode: "AUDIT MODE + UX MODE"
reset_db: false
needs_browser: true
---

# OBJETIVO

Hasta acá auditaste el sistema por su API: eso te dice si las reglas de negocio
están bien. Ahora vas a usar la pantalla como la usa tu gente, y juzgar si
**se puede trabajar con esto ocho horas por día**.

Sos el dueño. Tenés un preventista, dos en depósito, una administrativa y un
facturador. Ninguno es informático. La pregunta que tenés que responder es
simple: *¿esto los hace más rápidos o los va a hacer renegar?*

# QUÉ HACER

## 1. La prueba del facturador (la más importante)

Andá a la pantalla de facturación y emití una venta real: un cliente, tres o
cuatro artículos, cantidades distintas.

Medí y anotá:

- **Cuántas acciones cuesta** de punta a punta (cada clic y cada tecla cuenta).
- **Cuántas veces hay que soltar el teclado** para agarrar el mouse.
- Si se puede hacer **entera con teclado**. Probá: buscar el artículo, Enter
  para agregarlo, cambiar la cantidad, y emitir con la tecla que corresponda.
- Si el total en pantalla coincide con lo que devuelve la API para ese mismo
  comprobante, y con lo que quedó en la base (`db_query`).

Un facturador hace esto 80 veces por día. Diez segundos de más por factura son
más de dos horas por mes tiradas.

## 2. Lo que ve el que decide

Entrá al inicio y a la pantalla de inteligencia financiera.

- ¿En cuántos segundos entendés cómo está la empresa hoy?
- ¿Los números que muestra son los mismos que devuelve la API?
- Cuando el sistema dice algo fuerte ("la caja queda negativa en 90 días"),
  ¿podés llegar desde ahí al dato que lo origina, o hay que creerle?
- ¿Distingue claramente lo que es un **hecho** de lo que es una **proyección**?
  Si mezcla las dos cosas, es grave: se toman decisiones con eso.

## 3. Romperla como la rompe la gente de verdad

- Mandá un formulario vacío. Mandá cantidades en cero, negativas, absurdas.
- Empezá a cargar algo y cambiá de pantalla a la mitad. ¿Avisa que se pierde?
- Cargá una venta que supere el crédito del cliente. **¿El mensaje se entiende
  sin ser programador?** Si aparece un error técnico crudo, es un hallazgo.
- Buscá algo que no existe. Filtrá por un rango sin resultados. ¿La pantalla
  vacía explica algo o te deja mirando la nada?

## 4. Lo que un dueño mira sin darse cuenta

- ¿Se puede imprimir o exportar algo? Una factura, un listado, un resumen de
  cuenta. Si no se puede, tu administrativa va a seguir usando Excel.
- ¿Los montos están alineados y legibles, o hay que leer dígito por dígito?
- ¿Hay confirmación antes de lo irreversible (anular un comprobante)?
- ¿Se banca una pantalla con muchos datos, o se vuelve lenta e incómoda?

# CÓMO REPORTAR

Un hallazgo por problema concreto. Sacá `web_captura` como evidencia de todo lo
visual. En `business_need` escribí a quién le duele: *"el facturador pierde
tres segundos por renglón"* vale más que *"mejorar la UX"*.

Para cada uno estimá el costo real: si algo suma 5 segundos por operación y se
hace 80 veces al día, decilo en horas por mes. Esa cuenta es la que convence.

No inventes problemas de diseño por gusto estético. Si la pantalla es fea pero
rápida y clara, **eso está bien** y decilo. El criterio es el trabajo, no la
moda visual.
