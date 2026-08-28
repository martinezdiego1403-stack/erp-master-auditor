# ERP MASTER AUDITOR

Agente híbrido de auditoría para ERPs de consola.

Dos mitades que se alimentan entre sí:

- **Exploración (IA).** Un agente construido con el Claude Agent SDK maneja tu ERP como lo haría un empleado —tipeando en la consola y leyendo lo que responde— con el criterio de un auditor de ERP de distribución. Descubre casos que vos no escribiste como test.
- **Regresión (determinística).** Cada bug confirmado que encuentra el agente se convierte automáticamente en un test Pester. Esos tests corren después en cada commit, sin IA, sin costo y sin variabilidad.

El ciclo es: el agente explora → encuentra → genera el test → el test protege para siempre.

---

## Índice

1. [Cómo funciona el enganche a la consola](#1-cómo-funciona-el-enganche-a-la-consola)
2. [Instalación](#2-instalación)
3. [Conectarlo a tu ERP](#3-conectarlo-a-tu-erp)
4. [Los cinco problemas clásicos de enchufado](#4-los-cinco-problemas-clásicos-de-enchufado)
5. [Correr la auditoría](#5-correr-la-auditoría)
6. [Qué produce](#6-qué-produce)
7. [La capa Pester](#7-la-capa-pester)
8. [Auditoría continua](#8-auditoría-continua)
9. [Personalizar el agente](#9-personalizar-el-agente)
10. [Seguridad](#10-seguridad)

---

## 1. Cómo funciona el enganche a la consola

El agente **no vive dentro** de tu ERP. Corre aparte, lanza tu ERP como proceso hijo y le habla por stdin/stdout:

```
┌──────────────────────────────────────────────────────┐
│  Agente (Claude Agent SDK, Python)                    │
│  system prompt = prompts/charter.md                   │
│  objetivo      = prompts/missions/NN_*.md             │
└──────────────┬────────────────────────────────────────┘
               │ tools MCP in-process
   ┌───────────┴──────────────────────────────┐
   │ erp_send / erp_read / erp_send_key       │
   │ db_query        (verificación en datos)  │
   │ Read/Grep/Glob  (auditoría de código)    │
   │ report_finding / emit_regression_test    │
   └───────────┬──────────────────────────────┘
               │ stdin / stdout  (o ConPTY)
   ┌───────────┴──────────────┐
   │  Tu ERP (.NET / PS)      │
   └──────────────────────────┘
```

El problema técnico central es que una app interactiva no avisa cuándo terminó de escribir. El driver lo resuelve con una heurística de **quiet period**: lee hasta que pasan N ms sin bytes nuevos, o hasta que aparece el patrón del prompt (`ready_pattern`), lo que ocurra primero, con un techo duro de espera. Esto es lo que hace que funcione con prompts sin salto de línea (`Opción: `), que es exactamente donde fallan las implementaciones ingenuas basadas en `ReadLine()`.

Hay dos backends:

| | `pipe` | `pty` |
|---|---|---|
| Mecanismo | stdin/stdout redirigidos | consola real emulada (ConPTY, vía `pywinpty`) |
| Sirve si el ERP usa | `Read-Host`, `Console.ReadLine()` | `Console.ReadKey()`, colores, redibujado de pantalla |
| Dependencias | ninguna | `pip install pywinpty pyte` |
| Velocidad | mayor | menor |

**Empezá con `pipe`.** Pasate a `pty` sólo si `doctor` te muestra que no funciona.

---

## 2. Instalación

En la máquina donde corre el ERP (o una con acceso a él):

```powershell
# Python 3.10+
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Node 18+ (el SDK lo necesita por debajo)
node --version

# Credenciales
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

Para la capa de regresión: PowerShell 7 recomendado y Pester 5+.

```powershell
Install-Module Pester -Force -SkipPublisherCheck -MinimumVersion 5.0
```

---

## 3. Conectarlo a tu ERP

### Paso 1 — Configurar

```powershell
Copy-Item config.example.yaml config.yaml
```

Editá `config.yaml`. Lo único obligatorio es cómo se lanza tu ERP:

```yaml
erp:
  # Script PowerShell
  command: ["pwsh", "-NoLogo", "-NoProfile", "-File", "C:\\ERP\\ERP.ps1"]
  # o ejecutable .NET
  # command: ["C:\\ERP\\bin\\Release\\net8.0\\ERP.exe"]
  # o dotnet
  # command: ["dotnet", "C:\\ERP\\bin\\Release\\net8.0\\ERP.dll"]
  cwd: "C:\\ERP"
  backend: pipe
  encoding: utf-8
  env:
    ERP_ENV: "test"        # ¡que apunte a la base de prueba!
```

> **`-NoProfile` importa.** Si el perfil de PowerShell del usuario imprime algo al arrancar, esa basura entra al stream y confunde al agente.

### Paso 2 — Verificar la conexión antes de gastar un solo token

Éste es el paso que se saltea todo el mundo y por el que después no funciona nada:

```powershell
python -m auditor.run doctor
```

Deberías ver la primera pantalla de tu ERP. Si la ves, ya está: el enganche funciona.

Probá también una secuencia de inputs, para confirmar que el ERP responde a lo que le mandás:

```powershell
python -m auditor.run doctor --send 1 2 C1
```

`doctor` no usa el modelo. Es gratis. Usalo todas las veces que haga falta hasta que la salida se vea bien.

### Paso 3 — Afinar la lectura

Con la salida a la vista, ajustá dos cosas en `config.yaml`:

**`ready_pattern`** — si tu ERP siempre termina pidiendo algo con el mismo texto, ponelo como regex:

```yaml
ready_pattern: "Opci(o|ó)n:\\s*$"
```

Esto corta la lectura apenas aparece el prompt, en vez de esperar el quiet period. Reduce el tiempo de cada misión de forma notable.

**`quiet_ms`** — subilo si tu ERP tarda en imprimir (por ejemplo 800 ms si consulta base en cada pantalla). Bajalo a 200 ms si es instantáneo.

### Paso 4 — Base de datos (opcional pero muy recomendable)

```yaml
database:
  enabled: true
  kind: sqlserver
  connection_string: "Driver={ODBC Driver 18 for SQL Server};Server=localhost;Database=ERP_TEST;Trusted_Connection=yes;TrustServerCertificate=yes;"
```

Sin esto, el agente sólo puede creerle a la pantalla. Con esto, puede verificar que el stock se descontó de verdad, que el total facturado coincide con la suma de líneas y que la cuenta corriente cerró. **La mayoría de los hallazgos que valen la pena de un ERP salen de acá.** El acceso es de sólo lectura y está bloqueado por código: cualquier cosa que no sea `SELECT`/`WITH` se rechaza.

### Paso 5 — Reset de datos (opcional)

```yaml
reset:
  command: ["pwsh", "-NoProfile", "-File", "C:\\ERP\\tools\\Reset-TestDb.ps1"]
```

Un script tuyo que deje la base en un estado conocido (unos clientes, unos productos con stock, un proveedor). Varias misiones lo invocan antes de empezar. Sin reset funciona igual, pero los resultados son menos comparables entre corridas.

---

## 4. Los cinco problemas clásicos de enchufado

Si `doctor` no muestra lo que esperás, es casi seguro uno de estos:

### 4.1 No sale nada

El ERP escribe directo al buffer de consola en vez de a stdout. Pasa con `Console.Write` sobre un handle propio, con librerías de UI de consola, o con `Write-Host` en configuraciones raras.

→ Probá `backend: pty`.

### 4.2 Acentos rotos (`Opci?n`, `Art¡culo`)

Desajuste de code page. Windows suele usar CP850 o CP1252 en consola mientras el ERP escribe UTF-8, o al revés.

→ Probá `encoding: cp850`, después `cp1252`. La solución de fondo es forzar UTF-8 en el arranque de tu ERP:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8
```

### 4.3 El ERP explota apenas arranca

Si tu ERP usa `Console.ReadKey()` o `[Console]::CursorTop`, con stdin redirigido tira:

> *Cannot read keys when either application does not have a console or when console input has been redirected.*

→ `backend: pty` (`pip install pywinpty pyte`). Con ConPTY hay una consola real y esas APIs funcionan.

### 4.4 El ERP responde "opción inválida" a todo

Tu ERP espera una tecla suelta, no una línea con Enter.

→ `backend: pty`, y el agente usa `erp_send_key` en vez de `erp_send`.

### 4.5 Todo va lentísimo

Cada lectura está esperando el `max_wait_ms` completo porque nunca se cumple la condición de corte.

→ Configurá `ready_pattern`. Es la diferencia entre 8 segundos y 300 ms por interacción.

---

## 5. Correr la auditoría

```powershell
# ver las misiones disponibles
python -m auditor.run list

# arrancar por el descubrimiento (siempre primero)
python -m auditor.run mission 00

# seguir sumando misiones a la misma corrida
python -m auditor.run mission 01 --append
python -m auditor.run mission 07 --append

# o la auditoría completa de una vez
python -m auditor.run full

# un subconjunto
python -m auditor.run full --only 00,01,03,07,99
```

Las misiones son archivos markdown en `prompts/missions/`. Cada una tiene un objetivo acotado, porque un agente con un objetivo difuso ("probá todo") explora mal:

| | Misión | Qué busca |
|---|---|---|
| 00 | Descubrimiento | El mapa real: módulos, datos, dependencias |
| 01 | Lunes 08:00 | Una jornada normal de punta a punta |
| 02 | Día caótico | Las 14 cosas que salen mal cada semana |
| 03 | Ventas | Circuito comercial y cuenta corriente |
| 04 | Compras e inventario | La ecuación de stock, costos |
| 05 | Logística | Picking → packing → despacho → entrega |
| 06 | Finanzas | Las seis preguntas del dueño |
| 07 | Edge cases | Romperlo a propósito |
| 08 | Seguridad | Permisos, trazabilidad, fraude interno |
| 09 | UX y escalabilidad | Costo en teclas, dónde está el techo |
| 10 | Reportes, CRM, IA | ¿Sirve para decidir? |
| 99 | Síntesis | Maturity Score, veredicto, roadmap |

**Empezá siempre por la 00.** Su mapa se inyecta en el prompt de todas las siguientes: sin él, cada misión pierde la mitad de su presupuesto redescubriendo el menú.

**La 99 no toca la consola.** Recibe todos los hallazgos acumulados y escribe el veredicto.

---

## 6. Qué produce

Cada corrida crea `out/run-AAAAMMDD-HHMMSS/`:

```
REPORT.md                 reporte completo (tablero + matriz QA + backlog + veredicto)
findings.jsonl            hallazgos estructurados, uno por línea
system_map.md             mapa del sistema descubierto
NN_mision.log.md          razonamiento del agente en cada misión
NN_mision.transcript.txt  la conversación literal con la consola, input por input
regression/*.Tests.ps1    tests Pester generados
```

El transcript es tu mejor herramienta cuando algo se ve raro: muestra exactamente qué se tipeó y qué respondió el ERP, con timestamps.

Cada hallazgo lleva impacto, urgencia, riesgo y complejidad de 1 a 5; la prioridad (`CRÍTICO`/`ALTO`/`MEDIO`/`BAJO`) se calcula con una severidad ponderada donde impacto y riesgo pesan más que urgencia. Los *quick wins* (alta severidad, baja complejidad) salen destacados aparte.

---

## 7. La capa Pester

### Configurar

```powershell
python -m auditor.run export-pester-config
```

Genera `tests/erp.test.config.json` a partir de tu `config.yaml`, para no mantener la misma información en dos lados.

### Correr

```powershell
# tests base + los generados por el agente
.\tests\Invoke-Regression.ps1

# sólo los de negocio
.\tests\Invoke-Regression.ps1 -Tag negocio

# en CI (código de salida + NUnitXml)
.\tests\Invoke-Regression.ps1 -CI
```

`tests/Smoke.Tests.ps1` trae tres tests base que conviene ajustar a tu ERP hoy mismo: que arranque, que responda, y que no tire una excepción sin manejar ante entrada inválida. Si ésos fallan, el arnés no está bien conectado y no tiene sentido correr al agente todavía.

### El ciclo completo

1. El agente encuentra un bug y lo confirma.
2. Llama a `emit_regression_test` con la secuencia exacta y el patrón de lo que *debería* pasar.
3. Se genera `regression/F-0001.LoQueSea.Tests.ps1`.
4. **Ese test falla**, porque describe el comportamiento correcto y el bug todavía existe.
5. Arreglás el bug. El test pasa.
6. El test queda para siempre en la suite.

Los tests generados quedan en la carpeta de la corrida. Los que quieras conservar de forma permanente, movelos a `tests/` y versionalos.

### En CI

```yaml
- run: pwsh -File ./tests/Invoke-Regression.ps1 -CI
```

La parte de IA no va en CI: es cara, lenta y no determinística. Corré la auditoría completa por sprint o por release, y dejá los tests Pester en cada commit.

---

## 8. Auditoría continua

```powershell
python -m auditor.run report --compare out\run-20260801-101500
```

Genera `CONTINUOUS_AUDIT.md` comparando dos corridas: qué se solucionó, qué persiste, qué apareció nuevo y qué regresiones hay. El emparejamiento se hace por *fingerprint* (módulo + título normalizados), así que sobrevive a cambios de redacción y de numeración.

Una advertencia honesta: que un hallazgo desaparezca sólo significa que no volvió a aparecer. Si la misión que lo detectó no corrió, también desaparece. La prueba positiva de que un bug está arreglado es su test de regresión pasando, no su ausencia del reporte.

---

## 9. Personalizar el agente

**El charter** (`prompts/charter.md`) es la identidad y el criterio: las 36 secciones, la regla de evidencia, la regla de honestidad. Va como system prompt en todas las misiones. Editalo si tu ERP apunta a un rubro distinto (una farmacia y una distribuidora de bebidas no tienen los mismos casos borde).

**Las misiones** (`prompts/missions/*.md`) son los objetivos. Agregar una es crear un archivo:

```markdown
---
title: "Auditoría del módulo de comisiones"
mode: "AUDIT MODE + TEST MODE"
reset_db: true
---

# OBJETIVO
...
```

Aparece sola en `list` y en `full`. El orden lo da el prefijo numérico.

**Los límites** (`config.yaml → limits`) controlan cuánto puede explorar antes de que se le pida cerrar. `max_inputs_per_mission: 250` y `max_session_seconds: 1200` son un punto de partida razonable; el agente ve su presupuesto restante en `erp_status` y cierra ordenadamente cuando se agota.

**El demo.** `examples/fake_erp.py` es un ERP de juguete con dos bugs plantados a propósito (no valida stock, y aplica el descuento como monto fijo en vez de porcentaje). Sirve para probar todo el arnés antes de apuntarlo a tu sistema:

```powershell
python -m auditor.run --config examples/config.demo.yaml doctor --send 1 2 C1 P2 5 10
```

---

## 10. Seguridad

**Nunca contra producción.** Usá siempre una base de prueba. El agente crea pedidos, ajusta stock y cierra cajas: eso es el punto.

Las protecciones que ya vienen:

- `blocked_input_patterns` en `config.yaml` bloquea inputs peligrosos antes de que lleguen al ERP. Si la guarda se dispara, además es señal de que el agente se desvió del objetivo.
- `db_query` es de sólo lectura por código: se rechaza todo lo que no sea una única sentencia `SELECT`/`WITH`.
- `source.enable_bash: false` por defecto — el agente lee código pero no ejecuta comandos.
- Límites de inputs y de tiempo por misión.

`permission_mode: bypassPermissions` es necesario para que corra desatendido: sin eso, cada llamada a herramienta pediría confirmación. Es aceptable **porque** el conjunto de herramientas está acotado a las que definimos y el ambiente es de prueba. Si te incomoda, poné `acceptEdits` y aprobá a mano las primeras corridas hasta agarrar confianza.

`config.yaml` y `tests/erp.test.config.json` están en `.gitignore`: pueden contener cadenas de conexión.
