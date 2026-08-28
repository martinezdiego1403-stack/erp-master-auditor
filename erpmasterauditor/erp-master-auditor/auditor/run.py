"""
CLI del ERP MASTER AUDITOR.

    python -m auditor.run doctor                  # probar la conexion con la consola (sin agente)
    python -m auditor.run list                    # listar misiones
    python -m auditor.run mission 01              # correr una mision
    python -m auditor.run full                    # correr toda la auditoria + sintesis
    python -m auditor.run report                  # regenerar el reporte de la ultima corrida
    python -m auditor.run report --compare out/run-20260801-101500
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from .config import Config, load_config
from .driver import ConsoleDriver
from .findings import FindingStore
from .http_driver import HttpDriver
from .missions import Mission, load_all, resolve
from .report import build_report, compare_runs

PKG_ROOT = Path(__file__).resolve().parent.parent
MISSIONS_DIR = PKG_ROOT / "prompts" / "missions"
CHARTER_PATH = PKG_ROOT / "prompts" / "charter.md"
OUT_DIR = PKG_ROOT / "out"


# --------------------------------------------------------------------------
# Utilidades de corrida
# --------------------------------------------------------------------------
def new_run_dir() -> Path:
    d = OUT_DIR / f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    d.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "latest.txt").write_text(str(d), encoding="utf-8")
    return d


def latest_run_dir() -> Path:
    pointer = OUT_DIR / "latest.txt"
    if pointer.exists():
        p = Path(pointer.read_text(encoding="utf-8").strip())
        if p.exists():
            return p
    runs = sorted(OUT_DIR.glob("run-*"))
    if not runs:
        raise FileNotFoundError("No hay corridas en out/. Ejecuta una mision primero.")
    return runs[-1]


def _print(msg: str = "") -> None:
    print(msg, flush=True)


def make_driver(cfg: Config, transcript: Path | None):
    """El resto del arnes no distingue: los dos drivers exponen lo mismo."""
    if cfg.erp.mode == "http":
        return HttpDriver(cfg, transcript_path=transcript)
    return ConsoleDriver(cfg, transcript_path=transcript)


# --------------------------------------------------------------------------
# Ejecucion de una mision con el agente
# --------------------------------------------------------------------------
async def run_mission(cfg: Config, mission: Mission, run_dir: Path, store: FindingStore) -> float:
    """Corre una mision y devuelve lo que costo, para el tope de la corrida."""
    from claude_agent_sdk import ClaudeAgentOptions, query

    from .tools import build_server

    charter = CHARTER_PATH.read_text(encoding="utf-8")
    log_path = run_dir / f"{mission.key}.log.md"
    transcript = run_dir / f"{mission.key}.transcript.txt"

    driver = make_driver(cfg, transcript)

    # El navegador es caro de abrir: solo para las misiones que lo piden.
    web = None
    if mission.needs_browser and cfg.erp.web.enabled:
        from .web_driver import WebDriver, playwright_disponible
        ok, motivo = playwright_disponible()
        if ok:
            web = WebDriver(cfg, transcript_path=transcript,
                            capturas_dir=run_dir / "capturas")
        else:
            _print(f"  ! {mission.key} pide navegador y no esta disponible.\n{motivo}")
    elif mission.needs_browser:
        _print(f"  ! {mission.key} pide navegador pero erp.web.enabled = false.")

    server, allowed, _handlers = build_server(cfg, driver, store, run_dir, mission.key, web=web)

    tools = list(allowed)
    if cfg.source.root:
        tools += ["Read", "Grep", "Glob"]
        if cfg.source.enable_bash:
            tools.append("Bash")

    if cfg.agent.use_claude_code_preset:
        system_prompt = {"type": "preset", "preset": "claude_code", "append": charter}
    else:
        system_prompt = charter

    options_kwargs = dict(
        system_prompt=system_prompt,
        mcp_servers={"erp": server},
        allowed_tools=tools,
        permission_mode=cfg.agent.permission_mode,
        max_turns=cfg.limits.max_turns,
        cwd=cfg.source.root or str(PKG_ROOT),
    )
    modelo = mission.model or cfg.agent.model
    if modelo:
        options_kwargs["model"] = modelo
    options = ClaudeAgentOptions(**options_kwargs)

    prompt = _mission_prompt(mission, run_dir, store, cfg, web is not None)

    _print(f"\n{'='*70}\n  MISION {mission.key} — {mission.title}\n  modo: {mission.mode}"
           + (f"\n  modelo: {modelo}" if modelo else "")
           + (f"\n  navegador: si" if web is not None else "")
           + f"\n{'='*70}\n")

    parts: list[str] = []
    costo = 0.0
    try:
        if not mission.no_console:
            driver.start(reset_db=mission.reset_db)
        if web is not None:
            _print(await web.start())
        async for message in query(prompt=prompt, options=options):
            chunk = _render(message)
            if chunk:
                parts.append(chunk)
                _print(chunk)
            total = getattr(message, "total_cost_usd", None)
            if total is not None:
                costo = float(total)
    except KeyboardInterrupt:
        _print("\n[interrumpido por el usuario]")
    except Exception as exc:  # noqa: BLE001
        parts.append(f"\n\n**ERROR EN LA MISION:** {type(exc).__name__}: {exc}")
        _print(f"\n!! ERROR: {type(exc).__name__}: {exc}")
    finally:
        driver.stop()
        if web is not None:
            await web.stop()

    log_path.write_text(
        f"# {mission.title}\n\n_modo: {mission.mode} · {datetime.now():%Y-%m-%d %H:%M}_\n\n"
        + "\n".join(parts),
        encoding="utf-8",
    )
    _print(f"\n-> log: {log_path}")
    _print(f"-> hallazgos acumulados: {len(store.items)}")
    return costo


ADAPTADOR_HTTP = """
## Como es este ERP (leelo antes que la mision)

Este ERP **no es de consola**: es una aplicacion web con una API REST. El
charter y la mision estan escritos pensando en menus y pantallas de texto;
traducilo asi:

| Donde dice | Aca es |
|---|---|
| "navegar el menu", "elegir la opcion" | llamar el endpoint con `erp_api` |
| "la pantalla muestra" | el JSON que devuelve la API |
| "tipear en el campo" | mandar el campo en el `body` del pedido |
| "entrar con otro usuario" | `erp_login` con el alias del rol |

Lo que **no** cambia: el criterio. Segui siendo el dueño de la distribuidora
con 30 años de oficio. Que un pedido se cargue por API en vez de por pantalla
no lo hace correcto: importa igual que el stock se descuente, que el total
cierre, que la cuenta corriente refleje la operacion y que el sistema no te
deje hacer un disparate.

Reglas practicas:

- El listado de endpoints que viste al arrancar es el mapa del sistema. Si algo
  que el negocio necesita **no esta en esa lista**, eso es un hallazgo de tipo
  FALTANTE, y de los importantes.
- Un HTTP 4xx **no es un error de la herramienta**: es la respuesta del ERP.
  Muchas veces es correcta (rechazar una venta sin stock) y muchas veces es el
  hallazgo (rechazar algo valido, o aceptar algo que deberia rechazar).
- Verifica en la base con `db_query`, no le creas solo a la respuesta. Ojo: la
  base es multiempresa, filtra siempre por el `TenantId` de tu sesion o vas a
  estar mirando datos de otra empresa.
- La interfaz web que usa el usuario final esta en `frontend/` del codigo
  fuente. Si auditas usabilidad (teclas, cantidad de pasos, que ve el usuario),
  leela con Read/Grep en vez de suponer: la API no te dice como se ve.
- No existen endpoints de borrado. Si un circuito necesita deshacer algo,
  fijate si hay anulacion; si no la hay, es un hallazgo.

## Antes de empezar: leete el alcance declarado

En el codigo fuente hay dos documentos que dicen que decidieron construir y que
dejaron afuera **a proposito**:

- `docs/DECISIONES.md` — las decisiones de producto, con su justificacion.
- `docs/HANDOFF.md` — que esta hecho y que falta.

Leelos con Read antes de explorar. Sirven para dos cosas:

1. **No quemar presupuesto** redescubriendo que un modulo no existe. Si algo
   figura como fuera de alcance, verificalo rapido y reportalo como FALTANTE
   con su impacto de negocio; no le dediques media mision.
2. **Discutir las decisiones**, que es donde mas valor aportas. Una cosa es que
   un modulo falte por olvido y otra que lo hayan sacado por una razon. Si la
   razon te parece equivocada desde el negocio, decilo con argumentos: para eso
   te contrataron. Que este escrito no lo hace correcto.
"""


ADAPTADOR_WEB = """
## Tenes navegador en esta mision

Ademas de la API tenes las herramientas `web_*`, que manejan la interfaz real
con un navegador: `web_ir`, `web_clic`, `web_escribir`, `web_tecla`,
`web_leer`, `web_captura`.

Usalas para juzgar lo que la API no puede mostrarte:

- **Cuanto cuesta hacer el trabajo.** Conta clicks y teclas para facturar una
  venta tipica. Un empleado hace eso 80 veces por dia.
- **Si se puede trabajar sin mouse.** Proba operar la pantalla de facturacion
  solo con teclado. Si hay que soltar el teclado para cada renglon, es un
  problema serio de productividad, no un detalle estetico.
- **Si lo que se ve coincide con el dato.** Compara un total en pantalla con lo
  que devuelve la API y con lo que hay en la base. Que los tres coincidan no
  es obvio.
- **Si los errores se entienden.** Un mensaje tecnico crudo frente a un
  empleado de deposito es un hallazgo de UX.
- **Que pasa cuando algo sale mal.** Cerra la pantalla a mitad de una carga,
  mandala con campos vacios, poné cantidades absurdas.

Reglas:

- Despues de cada accion te devuelvo lo que se ve **y** la lista de controles
  disponibles: usala para elegir el proximo `objetivo` en vez de adivinar.
- Los errores de consola del navegador aparecen marcados: son hallazgos.
- Sacá `web_captura` como evidencia de los hallazgos visuales.
- Si un elemento que deberia existir no aparece, eso ya es un hallazgo: no
  pierdas turnos buscandolo de mil formas.
"""


def _mission_prompt(mission: Mission, run_dir: Path, store: FindingStore, cfg: Config,
                    con_navegador: bool = False) -> str:
    header = [
        f"# MISION: {mission.title}",
        f"**Modo de operacion:** {mission.mode}",
        "",
    ]
    if cfg.erp.mode == "http":
        header += [ADAPTADOR_HTTP, ""]
    if con_navegador:
        header += [ADAPTADOR_WEB, ""]

    map_path = run_dir / "system_map.md"
    if map_path.exists() and not mission.key.startswith("00"):
        header += [
            "## Mapa del sistema (descubierto en fases anteriores de esta auditoria)",
            "",
            map_path.read_text(encoding="utf-8")[:20000],
            "",
        ]

    if mission.no_console:
        header += [
            "## Hallazgos acumulados en esta auditoria",
            "",
            "```json",
            json.dumps([f.to_dict() for f in store.sorted_items()], ensure_ascii=False, indent=1)[:120000],
            "```",
            "",
        ]
    elif store.items:
        header += [
            "## Hallazgos ya registrados en misiones anteriores (no los repitas)",
            "",
            "\n".join(
                f"- {f.id} [{f.priority}] {f.module}: {f.title}"
                for f in store.sorted_items()[:120]
            ),
            "",
        ]

    footer = [
        "",
        "---",
        "",
        "Empeza ahora. " + (
            "No uses herramientas de consola en esta mision: sintetiza la evidencia que ya tenes "
            "y escribi el documento final completo como tu respuesta."
            if mission.no_console else
            (
                "El ERP web ya esta disponible y con sesion iniciada. Usa `erp_api` para operarlo "
                "(el listado de endpoints salio al arrancar) y `erp_login` para cambiar de rol. "
                "Recorda registrar cada hallazgo con `report_finding` a medida que lo encontras, "
                "no al final."
                if cfg.erp.mode == "http" else
                "El ERP ya esta arrancado y esperando en su primera pantalla; usa `erp_read` si necesitas "
                "volver a verla. Recorda registrar cada hallazgo con `report_finding` a medida que lo "
                "encontras, no al final."
            )
        ),
    ]
    return "\n".join(header + [mission.body] + footer)


def _render(message) -> str:
    """Extrae texto legible de un mensaje del SDK, sin depender de su version."""
    out: list[str] = []
    content = getattr(message, "content", None)
    if isinstance(content, list):
        for block in content:
            text = getattr(block, "text", None)
            if text:
                out.append(text)
                continue
            name = getattr(block, "name", None)
            if name:
                raw = getattr(block, "input", {}) or {}
                short = {k: (str(v)[:120]) for k, v in list(raw.items())[:4]}
                out.append(f"  · {name}({', '.join(f'{k}={v}' for k, v in short.items())})")
    elif isinstance(content, str):
        out.append(content)

    total = getattr(message, "total_cost_usd", None)
    if total is not None:
        turns = getattr(message, "num_turns", "?")
        out.append(f"\n[fin de mision · turnos: {turns} · costo: US${total:.4f}]")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Comandos
# --------------------------------------------------------------------------
def cmd_list(_: argparse.Namespace) -> None:
    for m in load_all(MISSIONS_DIR):
        flags = []
        if m.reset_db:
            flags.append("reset-db")
        if m.no_console:
            flags.append("sin-consola")
        tail = f"  [{', '.join(flags)}]" if flags else ""
        _print(f"  {m.key:<28} {m.title}{tail}")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Verifica la conexion con el ERP sin gastar tokens."""
    cfg = load_config(args.config)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if cfg.erp.mode == "http":
        _print(f"modo    : http")
        _print(f"api     : {cfg.erp.http.base_url}")
        _print(f"usuarios: {', '.join(u.alias for u in cfg.erp.http.users)}")
    else:
        _print(f"comando : {' '.join(cfg.erp.command)}")
        _print(f"cwd     : {cfg.erp.cwd}")
        _print(f"backend : {cfg.erp.backend}   encoding: {cfg.erp.encoding}")
    _print("-" * 70)

    driver = make_driver(cfg, OUT_DIR / "doctor.transcript.txt")
    try:
        first = driver.start(reset_db=False)
    except Exception as exc:  # noqa: BLE001
        _print(f"FALLO AL ARRANCAR: {type(exc).__name__}: {exc}")
        return

    _print("PRIMERA PANTALLA:" if cfg.erp.mode != "http" else "ESTADO INICIAL:")
    _print(first)
    _print("-" * 70)

    for text in args.send:
        _print(f">>> {text}")
        if cfg.erp.mode == "http":
            # "GET /articulos" o "POST /clientes {json}"
            partes = text.strip().split(None, 2)
            cuerpo = json.loads(partes[2]) if len(partes) > 2 else None
            _print(driver.request(partes[0], partes[1] if len(partes) > 1 else "/", cuerpo))
        else:
            _print(driver.send(text))
        _print("-" * 70)

    _print(driver.status())
    driver.stop()

    if args.web:
        _print("\n" + "=" * 70)
        _print("NAVEGADOR")
        _print("=" * 70)
        _probar_navegador(cfg)

    _print("\nDiagnostico:")
    if cfg.erp.mode == "http":
        if "NO RESPONDE" in first:
            _print("  ! La API no responde. Levanta el ERP antes de auditar.")
        elif "LOGIN RECHAZADO" in first or "sin '" in first:
            _print("  ! La API responde pero el login fallo: revisa erp.http.users.")
        else:
            _print("  OK: la API responde y la sesion se inicio. Ya podes correr misiones.")
    elif not first.strip() or first.startswith("[sin salida"):
        _print("  ! No llego salida. Revisa: (a) que el comando sea correcto,")
        _print("    (b) que el ERP escriba a stdout y no directamente al buffer de consola,")
        _print("    (c) si usa Console.ReadKey o redibuja pantalla -> pasa a backend: pty.")
    elif "?" in first and cfg.erp.encoding == "utf-8":
        _print("  ! Aparecen '?' o caracteres raros: proba encoding cp850 o cp1252,")
        _print("    o forza UTF-8 en el ERP al arrancar.")
    else:
        _print("  OK: el ERP responde. Ya podes correr misiones.")


def _probar_navegador(cfg: Config) -> None:
    """Abre la interfaz, entra y muestra la pantalla. Sin agente, sin costo."""
    if not cfg.erp.web.enabled:
        _print("  erp.web.enabled = false: la auditoria de interfaz esta apagada.")
        return

    from .web_driver import WebDriver, playwright_disponible

    ok, motivo = playwright_disponible()
    if not ok:
        _print(f"  ! {motivo}")
        return

    web = WebDriver(cfg, transcript_path=OUT_DIR / "doctor.transcript.txt",
                    capturas_dir=OUT_DIR / "doctor-capturas")

    async def correr():
        try:
            _print(await web.start())
            _print("-" * 70)
            _print(await web.captura("doctor-inicio"))
            _print(web.status())
        finally:
            await web.stop()

    asyncio.run(correr())


def cmd_export_pester(args: argparse.Namespace) -> None:
    """Genera tests/erp.test.config.json a partir de config.yaml, para no duplicar datos."""
    cfg = load_config(args.config)
    reset_cmd, *reset_args = (cfg.reset.command or [None])

    if cfg.erp.mode == "http":
        data = {
            "Mode": "http",
            "BaseUrl": cfg.erp.http.base_url,
            "LoginPath": cfg.erp.http.login_path,
            "Users": [
                {"Alias": u.alias, "Email": u.email, "Password": u.password}
                for u in cfg.erp.http.users
            ],
            "ResetCommand": reset_cmd,
            "ResetArguments": reset_args,
        }
        out = PKG_ROOT / "tests" / "erp.test.config.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        _print(f"-> {out}")
        _print("  ! Contiene credenciales: verifica que tests/ este en .gitignore.")
        return

    command, *arguments = cfg.erp.command
    data = {
        "Command": command,
        "Arguments": arguments,
        "WorkingDirectory": cfg.erp.cwd,
        "Encoding": cfg.erp.encoding,
        "QuietMs": cfg.erp.quiet_ms,
        "MaxWaitMs": cfg.erp.max_wait_ms,
        "ReadyPattern": cfg.erp.ready_pattern,
        "Environment": cfg.erp.env,
        "ResetCommand": reset_cmd,
        "ResetArguments": reset_args,
    }
    out = PKG_ROOT / "tests" / "erp.test.config.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _print(f"-> {out}")
    if cfg.erp.backend == "pty":
        _print(
            "  ! Tu config usa backend 'pty'. El arnes de Pester usa pipes: los tests "
            "generados sirven igual si el ERP acepta entrada por linea, pero no van a "
            "reproducir flujos que dependan de Console.ReadKey."
        )


def cmd_mission(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    mission = resolve(MISSIONS_DIR, args.name)
    run_dir = Path(args.run_dir) if args.run_dir else (
        latest_run_dir() if args.append else new_run_dir()
    )
    store = FindingStore(run_dir / "findings.jsonl")
    costo = asyncio.run(run_mission(cfg, mission, run_dir, store))
    build_report(run_dir, store)
    _print(f"-> costo de esta mision: US${costo:.4f}")
    _print(f"-> reporte: {run_dir / 'REPORT.md'}")


def cmd_full(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    run_dir = new_run_dir()
    store = FindingStore(run_dir / "findings.jsonl")
    missions = load_all(MISSIONS_DIR)
    if args.only:
        keep = {o.strip() for o in args.only.split(",")}
        missions = [m for m in missions if m.key in keep or m.order in keep]

    tope = cfg.limits.max_cost_usd
    _print(f"Corrida completa en {run_dir} — {len(missions)} misiones"
           + (f" · tope de gasto US${tope:.2f}" if tope else " · sin tope de gasto"))

    acumulado = 0.0
    for mission in missions:
        # El tope se controla entre misiones: adentro de una, el costo solo se
        # conoce al terminar.
        if tope and acumulado >= tope:
            _print(f"\n!! TOPE DE GASTO ALCANZADO (US${acumulado:.2f} de US${tope:.2f}). "
                   f"No se corre {mission.key} ni las siguientes.")
            break
        acumulado += asyncio.run(run_mission(cfg, mission, run_dir, store))
        _print(f"-> gasto acumulado de la corrida: US${acumulado:.4f}")

    build_report(run_dir, store)
    _print(f"\n{'='*70}\nAUDITORIA COMPLETA"
           f"\n  gasto total: US${acumulado:.4f}"
           f"\n  reporte: {run_dir / 'REPORT.md'}\n{'='*70}")


def cmd_report(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir) if args.run_dir else latest_run_dir()
    store = FindingStore(run_dir / "findings.jsonl")
    build_report(run_dir, store)
    _print(f"-> {run_dir / 'REPORT.md'}")
    if args.compare:
        out = compare_runs(Path(args.compare), run_dir)
        (run_dir / "CONTINUOUS_AUDIT.md").write_text(out, encoding="utf-8")
        _print(f"-> {run_dir / 'CONTINUOUS_AUDIT.md'}")
        _print(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="auditor", description="ERP MASTER AUDITOR")
    parser.add_argument("--config", default=str(PKG_ROOT / "config.yaml"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="listar misiones")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("doctor", help="probar la conexion con el ERP, sin agente")
    p.add_argument("--send", nargs="*", default=[], help="inputs de prueba a enviar en orden")
    p.add_argument("--web", action="store_true",
                   help="ademas, abrir la interfaz con el navegador y sacar una captura")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("export-pester-config", help="generar tests/erp.test.config.json desde config.yaml")
    p.set_defaults(func=cmd_export_pester)

    p = sub.add_parser("mission", help="correr una mision")
    p.add_argument("name")
    p.add_argument("--append", action="store_true", help="sumar a la ultima corrida en vez de crear una nueva")
    p.add_argument("--run-dir", default=None)
    p.set_defaults(func=cmd_mission)

    p = sub.add_parser("full", help="correr la auditoria completa")
    p.add_argument("--only", default=None, help="lista separada por comas de misiones a incluir")
    p.set_defaults(func=cmd_full)

    p = sub.add_parser("report", help="regenerar el reporte")
    p.add_argument("--run-dir", default=None)
    p.add_argument("--compare", default=None, help="corrida anterior para el modo auditoria continua")
    p.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        _print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
