"""Carga y validacion de la configuracion del auditor."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class HttpUser:
    """Una identidad con la que el auditor puede entrar al ERP."""
    alias: str
    email: str
    password: str


@dataclass
class HttpConfig:
    """Modo HTTP: el ERP es una app web con API REST en vez de una consola."""
    base_url: str = ""
    login_path: str = "/auth/login"
    token_field: str = "accessToken"
    health_path: str = "/openapi/v1.json"
    users: list[HttpUser] = field(default_factory=list)
    timeout_seconds: int = 30
    max_response_chars: int = 6000
    allowed_methods: list[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "PATCH"])


@dataclass
class WebLogin:
    """Como entrar por la pantalla de login, no por la API."""
    email: str = ""
    password: str = ""
    selector_email: str = "input[type=email]"
    selector_password: str = "input[type=password]"
    selector_submit: str = "button[type=submit]"


@dataclass
class WebConfig:
    """Auditoria de la interfaz con navegador (Playwright). Opcional."""
    enabled: bool = False
    base_url: str = ""
    login: WebLogin | None = None
    headless: bool = True
    width: int = 1440
    height: int = 900
    timeout_ms: int = 15000
    espera_ms: int = 600
    max_chars: int = 6000


@dataclass
class ErpConfig:
    command: list[str] = field(default_factory=list)
    cwd: str | None = None
    # console -> se maneja por stdin/stdout (backend pipe o pty)
    # http    -> se maneja por su API REST (app web)
    mode: str = "console"
    backend: str = "pipe"
    encoding: str = "utf-8"
    env: dict[str, str] = field(default_factory=dict)
    quiet_ms: int = 400
    max_wait_ms: int = 8000
    ready_pattern: str | None = None
    rows: int = 40
    cols: int = 140
    http: HttpConfig = field(default_factory=HttpConfig)
    web: WebConfig = field(default_factory=WebConfig)


@dataclass
class ResetConfig:
    command: list[str] | None = None
    timeout_seconds: int = 180


@dataclass
class DatabaseConfig:
    enabled: bool = False
    kind: str = "sqlite"
    connection_string: str = ""
    max_rows: int = 200


@dataclass
class SourceConfig:
    root: str | None = None
    enable_bash: bool = False


@dataclass
class Limits:
    max_inputs_per_mission: int = 250
    max_session_seconds: int = 1200
    max_turns: int = 200
    # Tope de gasto acumulado de una corrida completa. Al superarlo no se
    # arranca la mision siguiente. 0 = sin tope.
    max_cost_usd: float = 0.0


@dataclass
class AgentConfig:
    model: str | None = None
    use_claude_code_preset: bool = True
    permission_mode: str = "bypassPermissions"


@dataclass
class Config:
    erp: ErpConfig
    reset: ResetConfig
    database: DatabaseConfig
    source: SourceConfig
    limits: Limits
    agent: AgentConfig
    blocked_input_patterns: list[str] = field(default_factory=list)
    root: Path = field(default_factory=Path.cwd)

    @property
    def blocked_regexes(self) -> list[re.Pattern[str]]:
        return [re.compile(p) for p in self.blocked_input_patterns]


def _sub(d: dict[str, Any] | None, key: str) -> dict[str, Any]:
    return dict((d or {}).get(key) or {})


_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand(value: Any) -> Any:
    """Reemplaza ${VAR} y ${VAR:-default} con variables de entorno.

    Permite que las contraseñas y cadenas de conexión vivan en el entorno y no
    en un archivo de texto. Si la variable no existe y no hay default, se deja
    el literal para que el error sea evidente al conectar.
    """
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, str):
        return _ENV_RE.sub(
            lambda m: os.environ.get(m.group(1), m.group(2) if m.group(2) is not None else m.group(0)),
            value,
        )
    return value


def load_config(path: str | Path) -> Config:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Copia config.example.yaml a config.yaml y ajustalo."
        )
    raw: dict[str, Any] = _expand(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

    erp_raw = _sub(raw, "erp")
    mode = str(erp_raw.get("mode", "console")).lower()
    if mode not in ("console", "http"):
        raise ValueError("config: erp.mode debe ser 'console' o 'http'")

    http_raw = _sub(erp_raw, "http")
    http = HttpConfig(
        base_url=str(http_raw.get("base_url", "")).rstrip("/"),
        login_path=str(http_raw.get("login_path", "/auth/login")),
        token_field=str(http_raw.get("token_field", "accessToken")),
        health_path=str(http_raw.get("health_path", "/openapi/v1.json")),
        users=[
            HttpUser(
                alias=str(u.get("alias") or u.get("email", "")),
                email=str(u.get("email", "")),
                password=str(u.get("password", "")),
            )
            for u in (http_raw.get("users") or [])
        ],
        timeout_seconds=int(http_raw.get("timeout_seconds", 30)),
        max_response_chars=int(http_raw.get("max_response_chars", 6000)),
        allowed_methods=[str(m).upper() for m in (http_raw.get("allowed_methods")
                                                  or ["GET", "POST", "PUT", "PATCH"])],
    )

    web_raw = _sub(erp_raw, "web")
    login_raw = _sub(web_raw, "login")
    web = WebConfig(
        enabled=bool(web_raw.get("enabled", False)),
        base_url=str(web_raw.get("base_url", "")).rstrip("/"),
        login=WebLogin(
            email=str(login_raw.get("email", "")),
            password=str(login_raw.get("password", "")),
            selector_email=str(login_raw.get("selector_email", "input[type=email]")),
            selector_password=str(login_raw.get("selector_password", "input[type=password]")),
            selector_submit=str(login_raw.get("selector_submit", "button[type=submit]")),
        ) if login_raw else None,
        headless=bool(web_raw.get("headless", True)),
        width=int(web_raw.get("width", 1440)),
        height=int(web_raw.get("height", 900)),
        timeout_ms=int(web_raw.get("timeout_ms", 15000)),
        espera_ms=int(web_raw.get("espera_ms", 600)),
        max_chars=int(web_raw.get("max_chars", 6000)),
    )
    if web.enabled and not web.base_url:
        raise ValueError("config: erp.web.enabled = true pero falta erp.web.base_url")

    if mode == "console" and not erp_raw.get("command"):
        raise ValueError("config: falta erp.command (como se lanza el ERP)")
    if mode == "http":
        if not http.base_url:
            raise ValueError("config: en modo http falta erp.http.base_url")
        if not http.users:
            raise ValueError("config: en modo http falta al menos un usuario en erp.http.users")

    erp = ErpConfig(
        command=[str(c) for c in (erp_raw.get("command") or [])],
        cwd=erp_raw.get("cwd"),
        mode=mode,
        http=http,
        web=web,
        backend=str(erp_raw.get("backend", "pipe")).lower(),
        encoding=erp_raw.get("encoding", "utf-8"),
        env={str(k): str(v) for k, v in (erp_raw.get("env") or {}).items()},
        quiet_ms=int(erp_raw.get("quiet_ms", 400)),
        max_wait_ms=int(erp_raw.get("max_wait_ms", 8000)),
        ready_pattern=erp_raw.get("ready_pattern"),
        rows=int(erp_raw.get("rows", 40)),
        cols=int(erp_raw.get("cols", 140)),
    )
    if erp.backend not in ("pipe", "pty"):
        raise ValueError("config: erp.backend debe ser 'pipe' o 'pty'")

    reset_raw = _sub(raw, "reset")
    reset = ResetConfig(
        command=[str(c) for c in reset_raw["command"]] if reset_raw.get("command") else None,
        timeout_seconds=int(reset_raw.get("timeout_seconds", 180)),
    )

    db_raw = _sub(raw, "database")
    database = DatabaseConfig(
        enabled=bool(db_raw.get("enabled", False)),
        kind=str(db_raw.get("kind", "sqlite")).lower(),
        connection_string=str(db_raw.get("connection_string", "")),
        max_rows=int(db_raw.get("max_rows", 200)),
    )

    src_raw = _sub(raw, "source")
    source = SourceConfig(
        root=src_raw.get("root"),
        enable_bash=bool(src_raw.get("enable_bash", False)),
    )

    lim_raw = _sub(raw, "limits")
    limits = Limits(
        max_inputs_per_mission=int(lim_raw.get("max_inputs_per_mission", 250)),
        max_session_seconds=int(lim_raw.get("max_session_seconds", 1200)),
        max_turns=int(lim_raw.get("max_turns", 200)),
        max_cost_usd=float(lim_raw.get("max_cost_usd", 0) or 0),
    )

    ag_raw = _sub(raw, "agent")
    agent = AgentConfig(
        model=ag_raw.get("model"),
        use_claude_code_preset=bool(ag_raw.get("use_claude_code_preset", True)),
        permission_mode=str(ag_raw.get("permission_mode", "bypassPermissions")),
    )

    return Config(
        erp=erp,
        reset=reset,
        database=database,
        source=source,
        limits=limits,
        agent=agent,
        blocked_input_patterns=[str(p) for p in (raw.get("blocked_input_patterns") or [])],
        root=path.parent,
    )


def resolved_env(cfg: ErpConfig) -> dict[str, str]:
    env = dict(os.environ)
    env.update(cfg.env)
    return env
