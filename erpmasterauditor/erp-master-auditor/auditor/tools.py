"""
Herramientas MCP in-process que el auditor usa para manejar el ERP.

Se definen dentro de una factory para que cada tool cierre sobre el driver,
el store de hallazgos y la config de la corrida. El SDK trata las tools como
funciones sin estado, asi que el estado vivo (el proceso del ERP) vive aca
afuera, en el ConsoleDriver, y las tools solo lo tocan.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import db
from .config import Config
from .driver import ConsoleDriver
from .findings import FindingStore

SERVER_NAME = "erp"


def _text(body: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": body}]}


def _ps_slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", "", text.title())
    return text[:48] or "Regresion"


def build_server(
    cfg: Config,
    driver: ConsoleDriver,
    store: FindingStore,
    run_dir: Path,
    mission_name: str,
    web=None,
):
    """Devuelve (server, allowed_tool_names, handlers) — handlers permite testear
    las tools sin levantar el agente.

    Segun cfg.erp.mode se exponen las herramientas de consola (erp_send/erp_read)
    o las de API REST (erp_api/erp_login). El resto es igual en los dos modos."""

    tests_dir = run_dir / "regression"
    map_path = run_dir / "system_map.md"
    es_http = cfg.erp.mode == "http"

    # ---------------------------------------------------------------- consola
    @tool(
        "erp_start",
        "Arranca (o reinicia) el ERP en una consola limpia. Devuelve la primera "
        "pantalla. Usar reset_db=1 para dejar la base en estado conocido antes "
        "de un escenario que necesita datos predecibles.",
        {"reset_db": int},
    )
    async def erp_start(args: dict[str, Any]) -> dict[str, Any]:
        reset = bool(args.get("reset_db"))
        try:
            out = driver.start(reset_db=reset)
        except Exception as exc:  # noqa: BLE001
            return _text(f"FALLO AL ARRANCAR EL ERP: {type(exc).__name__}: {exc}")
        return _text(out)

    @tool(
        "erp_send",
        "Escribe una linea de texto en la consola del ERP (agrega Enter) y "
        "devuelve lo que el ERP imprime a continuacion. Es la forma normal de "
        "elegir opciones de menu y completar campos.",
        {"text": str, "wait_ms": int},
    )
    async def erp_send(args: dict[str, Any]) -> dict[str, Any]:
        try:
            return _text(driver.send(str(args.get("text", "")), wait_ms=args.get("wait_ms")))
        except Exception as exc:  # noqa: BLE001
            return _text(f"ERROR AL ENVIAR: {type(exc).__name__}: {exc}")

    @tool(
        "erp_send_key",
        "Envia una tecla especial sin Enter (enter, esc, up, down, left, right, "
        "tab, backspace, f1..f12, pageup, pagedown, ctrl+c). Solo tiene efecto "
        "real con backend 'pty'.",
        {"key": str, "wait_ms": int},
    )
    async def erp_send_key(args: dict[str, Any]) -> dict[str, Any]:
        try:
            return _text(driver.send_key(str(args.get("key", "")), wait_ms=args.get("wait_ms")))
        except Exception as exc:  # noqa: BLE001
            return _text(f"ERROR AL ENVIAR TECLA: {type(exc).__name__}: {exc}")

    @tool(
        "erp_read",
        "Lee salida adicional sin enviar nada. Util cuando el ERP tarda "
        "(un proceso largo, un reporte) o cuando sospechas que quedo output pendiente.",
        {"wait_ms": int},
    )
    async def erp_read(args: dict[str, Any]) -> dict[str, Any]:
        return _text(driver.read(wait_ms=args.get("wait_ms")))

    @tool(
        "erp_screen",
        "Devuelve la pantalla visible reconstruida (solo backend 'pty' con pyte). "
        "Util para auditar UX en pantallas que se redibujan.",
        {},
    )
    async def erp_screen(_: dict[str, Any]) -> dict[str, Any]:
        return _text(driver.screen())

    @tool(
        "erp_status",
        "Estado de la sesion: si el ERP sigue vivo, su exit code, y cuanto "
        "presupuesto de inputs y de tiempo queda en esta mision.",
        {},
    )
    async def erp_status(_: dict[str, Any]) -> dict[str, Any]:
        return _text(driver.status())

    @tool("erp_stop", "Cierra el proceso del ERP.", {})
    async def erp_stop(_: dict[str, Any]) -> dict[str, Any]:
        driver.stop()
        return _text("ERP detenido.")

    # ------------------------------------------------------------------- api
    @tool(
        "erp_api",
        "Llama un endpoint de la API del ERP y devuelve el codigo HTTP y la "
        "respuesta. Es la forma de usar el sistema: listar, crear y modificar "
        "igual que lo haria la pantalla web. path es relativo (ej: /articulos, "
        "/ventas/facturas). body es el JSON del pedido (solo para POST/PUT). "
        "Un 4xx no es un error de la herramienta: es como responde el ERP, y "
        "suele ser justamente lo que hay que auditar.",
        {"method": str, "path": str, "body": dict},
    )
    async def erp_api(args: dict[str, Any]) -> dict[str, Any]:
        return _text(driver.request(
            str(args.get("method", "GET")),
            str(args.get("path", "")),
            args.get("body"),
        ))

    @tool(
        "erp_login",
        "Cambia la identidad de la sesion por la del alias indicado. Sirve para "
        "verificar que cada rol solo pueda hacer lo suyo: entra como un rol y "
        "proba llegar a algo que no le corresponde.",
        {"alias": str},
    )
    async def erp_login(args: dict[str, Any]) -> dict[str, Any]:
        return _text(driver.login(str(args.get("alias", ""))))

    # ------------------------------------------------------- interfaz web
    @tool(
        "web_ir",
        "Abre una pantalla de la interfaz web (ruta relativa, ej: /facturar, "
        "/clientes) y devuelve lo que se ve y con que se puede interactuar. "
        "Es la vista del usuario real, no la de la API.",
        {"ruta": str},
    )
    async def web_ir(args: dict[str, Any]) -> dict[str, Any]:
        return _text(await web.ir(str(args.get("ruta", "/"))))

    @tool(
        "web_clic",
        "Hace clic en un elemento. objetivo acepta 'texto:Emitir', "
        "'rol:button/Guardar', 'label:Cliente', 'placeholder:Buscar' o un "
        "selector CSS. Devuelve la pantalla resultante.",
        {"objetivo": str},
    )
    async def web_clic(args: dict[str, Any]) -> dict[str, Any]:
        return _text(await web.clic(str(args.get("objetivo", ""))))

    @tool(
        "web_escribir",
        "Escribe un valor en un campo. Mismo formato de 'objetivo' que web_clic.",
        {"objetivo": str, "valor": str},
    )
    async def web_escribir(args: dict[str, Any]) -> dict[str, Any]:
        return _text(await web.escribir(str(args.get("objetivo", "")), str(args.get("valor", ""))))

    @tool(
        "web_tecla",
        "Presiona una tecla (Enter, Escape, Tab, F10, Control+k, ArrowDown...). "
        "Sirve para auditar si el sistema se puede operar sin mouse.",
        {"tecla": str},
    )
    async def web_tecla(args: dict[str, Any]) -> dict[str, Any]:
        return _text(await web.tecla(str(args.get("tecla", ""))))

    @tool(
        "web_leer",
        "Vuelve a leer la pantalla actual sin hacer nada. Util despues de una "
        "accion que tarda, o para ver que hay antes de decidir el proximo paso.",
        {},
    )
    async def web_leer(_: dict[str, Any]) -> dict[str, Any]:
        return _text(await web.leer())

    @tool(
        "web_captura",
        "Guarda una captura de la pantalla actual en la carpeta de la corrida. "
        "Usala como evidencia de un hallazgo visual.",
        {"nombre": str},
    )
    async def web_captura(args: dict[str, Any]) -> dict[str, Any]:
        return _text(await web.captura(str(args.get("nombre", "pantalla"))))

    @tool("web_status", "Estado del navegador y presupuesto restante de la mision.", {})
    async def web_status(_: dict[str, Any]) -> dict[str, Any]:
        return _text(web.status())

    # ---------------------------------------------------------------- datos
    @tool(
        "db_query",
        "Ejecuta un SELECT de solo lectura contra la base del ERP para verificar "
        "que lo que la consola dijo que paso, realmente quedo en los datos "
        "(stock, totales, cuenta corriente, asientos). Solo SELECT/WITH.",
        {"sql": str, "max_rows": int},
    )
    async def db_query(args: dict[str, Any]) -> dict[str, Any]:
        return _text(db.run_query(cfg.database, str(args.get("sql", "")), args.get("max_rows")))

    # ---------------------------------------------------------------- salida
    @tool(
        "record_map",
        "Registra un pedazo del mapa del sistema (modulos descubiertos, flujo de "
        "dependencias, arquitectura, integraciones). Se acumula en system_map.md. "
        "kind: modulos | dependencias | arquitectura | integraciones | datos | notas.",
        {"kind": str, "content": str},
    )
    async def record_map(args: dict[str, Any]) -> dict[str, Any]:
        kind = str(args.get("kind", "notas")).strip().lower()
        content = str(args.get("content", "")).strip()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        with map_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## {kind.upper()} — {mission_name} ({stamp})\n\n{content}\n")
        return _text(f"Registrado en system_map.md ({kind}, {len(content)} chars).")

    @tool(
        "report_finding",
        "Registra un hallazgo estructurado. Un hallazgo por problema concreto. "
        "evidence_level debe reflejar honestamente que tan probado esta: "
        "CONFIRMADO (lo reproduje), PARCIAL, NO_CONFIRMADO, FALTANTE. "
        "impact/urgency/risk/complexity van de 1 a 5; la prioridad se calcula sola.",
        {
            "module": str,
            "title": str,
            "type": str,
            "status": str,
            "evidence_level": str,
            "business_need": str,
            "expected": str,
            "observed": str,
            "repro_steps": list,
            "evidence": list,
            "impact": int,
            "urgency": int,
            "risk": int,
            "complexity": int,
            "proposed_solution": str,
            "acceptance_criteria": list,
            "affected_user": str,
            "category": str,
            "automation": str,
        },
    )
    async def report_finding(args: dict[str, Any]) -> dict[str, Any]:
        f = store.add(mission_name, args)
        return _text(
            f"Hallazgo {f.id} registrado — {f.module} / {f.priority} "
            f"(severidad {f.severity_score}{', QUICK WIN' if f.quick_win else ''}). "
            f"Total en esta corrida: {len(store.items)}."
        )

    @tool(
        "emit_regression_test",
        "Convierte un hallazgo reproducible en un test Pester determinista, para "
        "que ese bug no vuelva nunca. Usalo SOLO con hallazgos CONFIRMADOS y con "
        "pasos exactos. inputs = lista de textos a enviar en orden. "
        "expect_pattern = regex que la salida final DEBERIA cumplir cuando este arreglado. "
        "forbid_pattern = regex que NO deberia aparecer (opcional). "
        "En modo http cada elemento de inputs es una llamada con la forma "
        "'METODO /ruta' o 'METODO /ruta {json del cuerpo}', por ejemplo: "
        "'POST /ventas/facturas {\"clienteId\":\"...\",\"renglones\":[]}'.",
        {
            "finding_id": str,
            "title": str,
            "inputs": list,
            "expect_pattern": str,
            "forbid_pattern": str,
            "reset_db": int,
        },
    )
    async def emit_regression_test(args: dict[str, Any]) -> dict[str, Any]:
        tests_dir.mkdir(parents=True, exist_ok=True)
        fid = str(args.get("finding_id") or "F-XXXX").strip()
        title = str(args.get("title") or "Regresion").strip()
        inputs = [str(i) for i in (args.get("inputs") or [])]
        expect = str(args.get("expect_pattern") or "").strip()
        forbid = str(args.get("forbid_pattern") or "").strip()
        reset = bool(args.get("reset_db"))

        if not inputs:
            return _text("No se genero el test: 'inputs' vacio. Necesito la secuencia exacta.")

        name = f"{fid}.{_ps_slug(title)}.Tests.ps1"
        path = tests_dir / name

        def ps(s: str) -> str:
            return s.replace("'", "''")

        cabecera = [
            "# Generado automaticamente por ERP MASTER AUDITOR",
            f"# Hallazgo: {fid} — {title}",
            f"# Mision: {mission_name}",
            "",
        ]

        if es_http:
            lines = cabecera + [
                "BeforeAll {",
                "    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\\..\\..')).Path",
                "    $cfg = Get-Content (Join-Path $repoRoot 'tests\\erp.test.config.json') -Raw | ConvertFrom-Json",
                "    $script:Base = $cfg.BaseUrl",
                "    $login = Invoke-RestMethod \"$script:Base$($cfg.LoginPath)\" -Method Post `",
                "        -ContentType 'application/json' `",
                "        -Body (@{ email = $cfg.Users[0].Email; password = $cfg.Users[0].Password } | ConvertTo-Json)",
                "    $script:H = @{ Authorization = \"Bearer $($login.accessToken)\" }",
                "}",
                "",
                f"Describe '{ps(fid)} — {ps(title)}' -Tag 'regresion' {{",
                f"    It 'no vuelve a fallar: {ps(title)}' {{",
                "        $salida = ''",
            ]
            if reset and cfg.reset.command:
                lines.append(f"        & '{ps(cfg.reset.command[0])}' "
                             + " ".join(f"'{ps(a)}'" for a in cfg.reset.command[1:]) + " | Out-Null")
            for i in inputs:
                partes = i.strip().split(None, 2)
                metodo = partes[0].upper() if partes else "GET"
                ruta = partes[1] if len(partes) > 1 else "/"
                cuerpo = partes[2] if len(partes) > 2 else ""
                cuerpo_ps = f" -Body '{ps(cuerpo)}'" if cuerpo else ""
                lines += [
                    "        try {",
                    f"            $salida = Invoke-RestMethod \"$script:Base{ps(ruta)}\" "
                    f"-Method {metodo} -Headers $script:H "
                    f"-ContentType 'application/json'{cuerpo_ps} | ConvertTo-Json -Depth 8",
                    "        } catch { $salida = $_.ErrorDetails.Message }",
                ]
            if expect:
                lines.append(f"        $salida | Should -Match '{ps(expect)}'")
            if forbid:
                lines.append(f"        $salida | Should -Not -Match '{ps(forbid)}'")
            lines += ["    }", "}", ""]
        else:
            lines = cabecera + [
                "BeforeAll {",
                "    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\\..\\..')).Path",
                "    Import-Module (Join-Path $repoRoot 'tests\\ERPConsole.psm1') -Force",
                "    $script:Cfg = Get-ErpTestConfig",
                "}",
                "",
                f"Describe '{ps(fid)} — {ps(title)}' -Tag 'regresion' {{",
                f"    It 'no vuelve a fallar: {ps(title)}' {{",
            ]
            if reset:
                lines.append("        Reset-ErpTestData -Config $script:Cfg")
            lines += [
                "        $s = Start-ErpSession -Config $script:Cfg",
                "        try {",
                "            $out = Read-ErpOutput -Session $s",
            ]
            for i in inputs:
                lines.append(f"            $out = Send-ErpInput -Session $s -Text '{ps(i)}'")
            if expect:
                lines.append(f"            $out | Should -Match '{ps(expect)}'")
            if forbid:
                lines.append(f"            $out | Should -Not -Match '{ps(forbid)}'")
            lines += [
                "        }",
                "        finally { Stop-ErpSession -Session $s }",
                "    }",
                "}",
                "",
            ]
        path.write_text("\n".join(lines), encoding="utf-8")

        meta = tests_dir / "index.jsonl"
        with meta.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"finding_id": fid, "title": title, "file": name, "inputs": inputs,
                 "expect": expect, "forbid": forbid, "reset_db": reset},
                ensure_ascii=False) + "\n")

        return _text(
            f"Test de regresion generado: regression/{name}. "
            "Recorda que este test refleja el comportamiento CORRECTO esperado: "
            "va a fallar hasta que el bug este arreglado."
        )

    # Solo se exponen las herramientas del transporte que corresponde: darle al
    # agente `erp_send` contra una app web lo unico que logra es que pierda
    # turnos intentando tipear en algo que no existe.
    comunes = [erp_start, erp_status, erp_stop, db_query, record_map,
               report_finding, emit_regression_test]
    nombres_comunes = ["erp_start", "erp_status", "erp_stop", "db_query",
                       "record_map", "report_finding", "emit_regression_test"]

    if es_http:
        tools = [erp_api, erp_login] + comunes
        names = ["erp_api", "erp_login"] + nombres_comunes
    else:
        tools = [erp_send, erp_send_key, erp_read, erp_screen] + comunes
        names = ["erp_send", "erp_send_key", "erp_read", "erp_screen"] + nombres_comunes

    # El navegador solo se ofrece si la mision lo pidio y esta disponible: darle
    # herramientas que no funcionan es la forma mas rapida de quemarle turnos.
    if web is not None:
        tools += [web_ir, web_clic, web_escribir, web_tecla, web_leer, web_captura, web_status]
        names += ["web_ir", "web_clic", "web_escribir", "web_tecla", "web_leer",
                  "web_captura", "web_status"]

    server = create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=tools)
    allowed = [f"mcp__{SERVER_NAME}__{n}" for n in names]
    handlers = {t.name: t.handler for t in tools}
    return server, allowed, handlers
