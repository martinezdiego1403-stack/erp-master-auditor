# Auditar un ERP web (modo HTTP + navegador)

El auditor nació para ERPs de consola: lanza el ERP como proceso hijo y le
tipea por stdin. **Abasto ERP es una app web** (React + API REST), así que no
hay consola donde engancharse.

Se agregaron dos transportes nuevos. El criterio no cambia: el charter, las
misiones, el scoring, el reporte y la auditoría continua funcionan igual.

| | `mode: console` | `mode: http` | `erp.web` (navegador) |
|---|---|---|---|
| Qué maneja | stdin / stdout | la API REST | la interfaz real |
| Herramientas | `erp_send`, `erp_read`, `erp_send_key`, `erp_screen` | `erp_api`, `erp_login` | `web_ir`, `web_clic`, `web_escribir`, `web_tecla`, `web_leer`, `web_captura` |
| Sirve para | ERPs de terminal | reglas de negocio, datos, permisos | UX, teclado, lo que ve el usuario |
| Costo de arranque | bajo | bajo | alto (abre Chromium) |

Sin cambios: `erp_start`, `erp_status`, `erp_stop`, `db_query`, `record_map`,
`report_finding`, `emit_regression_test`, límites, transcript y guardas.

## Credenciales: fuera del archivo

`config.yaml` acepta `${VAR}` y `${VAR:-default}`, que se expanden con el
entorno al cargar. Las contraseñas no viven en el archivo:

```powershell
$env:ABASTO_EMAIL            = "tu@mail.com"
$env:ABASTO_PASSWORD         = "tu-clave"
$env:ABASTO_AUDITOR_PASSWORD = "clave-de-los-usuarios-auditores"
$env:PG_PASSWORD             = "clave-de-postgres"
```

## Configurar

```yaml
erp:
  mode: http
  http:
    base_url: "http://localhost:5180/api"
    login_path: "/auth/login"
    token_field: "accessToken"
    # Absoluto si el documento cuelga de la raíz y no de /api.
    health_path: "http://localhost:5180/openapi/v1.json"
    users:                      # el primero arranca cada misión
      - { alias: admin,    email: "${ABASTO_EMAIL}", password: "${ABASTO_PASSWORD}" }
      - { alias: deposito, email: "...",             password: "${ABASTO_AUDITOR_PASSWORD}" }
    allowed_methods: ["GET", "POST", "PUT"]   # sin DELETE

  web:                          # auditoría de interfaz (opcional)
    enabled: true
    base_url: "http://localhost:5173"
    headless: true
    login:
      email: "${ABASTO_EMAIL}"
      password: "${ABASTO_PASSWORD}"
      selector_email: "input[type=email]"
      selector_password: "input[type=password]"
      selector_submit: "button[type=submit]"

limits:
  max_cost_usd: 25.0            # no arranca la misión siguiente si se pasó
```

## Verificar sin gastar tokens

```powershell
python -m auditor.run doctor
python -m auditor.run doctor --send "GET /articulos?tamano=3"
python -m auditor.run doctor --web      # abre la interfaz, entra y saca captura
```

## El navegador

Requiere Playwright:

```powershell
pip install playwright
python -m playwright install chromium
```

Sólo se abre en las misiones que declaran `needs_browser: true` en su front
matter — hoy la **11 (interfaz web)**. Darle herramientas de navegador a una
misión que no lo necesita es quemarle turnos y plata.

Cada acción devuelve **lo que se ve** más **el inventario de controles
disponibles**, así el agente no tiene que adivinar selectores. Los errores de
consola del navegador se marcan aparte porque son hallazgos por sí mismos.

`objetivo` acepta: `texto:Emitir`, `rol:button/Guardar`, `label:Cliente`,
`placeholder:Buscar`, o un selector CSS.

## Control de gasto

- `limits.max_cost_usd` corta entre misiones (adentro de una, el costo sólo se
  conoce al terminar).
- Cada misión puede fijar su propio `model:` en el front matter: descubrimiento
  con uno más barato, síntesis con el mejor.
- `mission` y `full` imprimen el costo de cada misión y el acumulado.

## Verificación en la base

`db_query` es de sólo lectura y soporta PostgreSQL (`pip install
"psycopg[binary]"`). **La base es multiempresa**: toda consulta tiene que
filtrar por el `TenantId` de la sesión. El adaptador que se inyecta en cada
misión ya se lo advierte al agente.

## Traducción del vocabulario

Las misiones dicen "navegá el menú" y "la pantalla muestra". `run.py` inyecta
`ADAPTADOR_HTTP` (y `ADAPTADOR_WEB` cuando hay navegador) al principio de cada
prompt: traduce el vocabulario, fija las reglas del modo web y manda leer
`docs/DECISIONES.md` y `docs/HANDOFF.md` para no gastar presupuesto
redescubriendo lo que ya se sabe que falta.

Por eso **no hizo falta reescribir los 13 archivos de misión**: si mañana
cambia el criterio, se cambia en el charter y sirve para los tres transportes.

## Lo que sigue sin cubrir

- **Concurrencia.** Un solo auditor a la vez: no detecta lo que pasa cuando dos
  usuarios facturan el mismo artículo al mismo tiempo.
- **Impresión y PDF.** Si el ERP genera comprobantes imprimibles, el agente ve
  que se descargó algo pero no puede leer el contenido.
- **Rendimiento real.** Mide con datos de demo en localhost, no con 200.000
  comprobantes y latencia de red.
