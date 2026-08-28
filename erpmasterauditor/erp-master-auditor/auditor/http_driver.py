"""
Driver HTTP: maneja un ERP web a traves de su API REST.

Es el equivalente del ConsoleDriver para sistemas que no tienen consola.
Donde el driver de consola tipea en stdin y lee stdout, este hace pedidos
HTTP y lee respuestas. El resto del arnes (limites, transcript, guardas,
hallazgos, reporte) es identico, porque solo cambia el transporte.

Mantiene una sesion con token: el auditor puede cambiar de identidad para
verificar permisos, que es justamente lo que pide la mision de seguridad.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config, HttpUser


class HttpDriver:
    """Misma superficie que ConsoleDriver, pero contra una API REST."""

    def __init__(self, cfg: Config, transcript_path: Path | None = None) -> None:
        self.cfg = cfg
        self.http = cfg.erp.http
        self.transcript_path = transcript_path
        self.inputs_sent = 0
        self.started_at: float | None = None
        self._blocked = cfg.blocked_regexes
        self._token: str | None = None
        self._identidad: str | None = None
        self._alive = False
        if transcript_path:
            transcript_path.parent.mkdir(parents=True, exist_ok=True)

    # -- transcript ---------------------------------------------------------
    def _log(self, marker: str, body: str) -> None:
        if not self.transcript_path:
            return
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        with self.transcript_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n--- [{stamp}] {marker} ---\n{body}\n")

    # -- ciclo de vida ------------------------------------------------------
    def start(self, reset_db: bool = False) -> str:
        if reset_db:
            self.reset_database()
        self.inputs_sent = 0
        self.started_at = time.monotonic()
        self._log("START", f"{self.http.base_url} ({len(self.http.users)} usuarios)")

        partes: list[str] = [f"ERP web en {self.http.base_url}"]

        disponible, detalle = self._health()
        self._alive = disponible
        partes.append(detalle)
        if not disponible:
            return "\n".join(partes)

        # Entra con el primer usuario configurado (normalmente el administrador).
        partes.append(self.login(self.http.users[0].alias))
        partes.append(
            "\nIdentidades disponibles para `erp_login`: "
            + ", ".join(f"{u.alias}" for u in self.http.users)
        )
        return "\n".join(partes)

    def _health(self) -> tuple[bool, str]:
        """Confirma que la API responde y lista los endpoints que expone."""
        try:
            status, body = self._raw("GET", self.http.health_path, None, con_token=False)
        except Exception as exc:  # noqa: BLE001
            return False, (
                f"LA API NO RESPONDE ({type(exc).__name__}: {exc}). "
                "Verifica que el ERP este levantado antes de auditar."
            )
        if status >= 400:
            return True, f"La API responde (HTTP {status} en {self.http.health_path})."

        try:
            doc = json.loads(body)
            rutas = sorted(doc.get("paths", {}).keys())
        except Exception:  # noqa: BLE001
            return True, f"La API responde (HTTP {status})."

        lineas = [f"La API responde. {len(rutas)} endpoints publicados:"]
        for ruta in rutas:
            metodos = ",".join(m.upper() for m in doc["paths"][ruta].keys())
            lineas.append(f"  {metodos:<18} {ruta}")
        return True, "\n".join(lineas)

    def reset_database(self) -> str:
        cmd = self.cfg.reset.command
        if not cmd:
            return "reset no configurado (reset.command = null)"
        proc = subprocess.run(
            cmd, cwd=self.cfg.erp.cwd, capture_output=True, text=True,
            timeout=self.cfg.reset.timeout_seconds,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        self._log("RESET-DB", out[-4000:])
        return f"reset rc={proc.returncode}\n{out[-2000:]}"

    def stop(self) -> None:
        self._log("STOP", f"pedidos={self.inputs_sent}")
        self._token = None
        self._identidad = None

    # -- limites ------------------------------------------------------------
    def budget_status(self) -> tuple[bool, str]:
        if self.inputs_sent >= self.cfg.limits.max_inputs_per_mission:
            return False, (
                f"LIMITE ALCANZADO: {self.inputs_sent} pedidos en esta mision. "
                "Cerra la mision y reporta lo que tengas."
            )
        if self.started_at is not None:
            elapsed = time.monotonic() - self.started_at
            if elapsed >= self.cfg.limits.max_session_seconds:
                return False, (
                    f"LIMITE ALCANZADO: {int(elapsed)}s de sesion. "
                    "Cerra la mision y reporta lo que tengas."
                )
        return True, ""

    def check_input(self, text: str) -> str | None:
        for rx in self._blocked:
            if rx.search(text):
                return f"PEDIDO BLOQUEADO por la guarda de seguridad ({rx.pattern}). No se envio nada."
        return None

    # -- sesion -------------------------------------------------------------
    def _usuario(self, alias: str) -> HttpUser | None:
        alias = (alias or "").strip().lower()
        for u in self.http.users:
            if u.alias.lower() == alias or u.email.lower() == alias:
                return u
        return None

    def login(self, alias: str) -> str:
        """Cambia la identidad de la sesion. Clave para auditar permisos."""
        user = self._usuario(alias)
        if user is None:
            disponibles = ", ".join(u.alias for u in self.http.users)
            return f"No hay un usuario con alias '{alias}'. Disponibles: {disponibles}"

        try:
            status, body = self._raw(
                "POST", self.http.login_path,
                {"email": user.email, "password": user.password},
                con_token=False,
            )
        except Exception as exc:  # noqa: BLE001
            return f"ERROR AL INICIAR SESION: {type(exc).__name__}: {exc}"

        if status >= 400:
            return f"LOGIN RECHAZADO (HTTP {status}): {body[:500]}"

        try:
            datos = json.loads(body)
        except Exception:  # noqa: BLE001
            return f"LOGIN respondio algo que no es JSON: {body[:300]}"

        token = datos.get(self.http.token_field)
        if not token:
            return f"LOGIN sin '{self.http.token_field}' en la respuesta: {body[:300]}"

        self._token = token
        self._identidad = user.alias
        usuario = datos.get("usuario") or {}
        self._log("LOGIN", f"{user.alias} -> {usuario}")
        return (
            f"Sesion iniciada como '{user.alias}'"
            + (f" — {usuario.get('nombre')} ({usuario.get('rol')}) "
               f"en {usuario.get('tenant')}" if usuario else "")
        )

    # -- io -----------------------------------------------------------------
    def request(self, method: str, path: str, body: Any = None) -> str:
        ok, msg = self.budget_status()
        if not ok:
            return msg

        method = (method or "GET").upper()
        if method not in self.http.allowed_methods:
            return (
                f"METODO {method} NO PERMITIDO en esta auditoria. "
                f"Permitidos: {', '.join(self.http.allowed_methods)}."
            )

        cuerpo_txt = json.dumps(body, ensure_ascii=False) if body is not None else ""
        bloqueado = self.check_input(f"{method} {path} {cuerpo_txt}")
        if bloqueado:
            self._log("BLOCKED", f"{method} {path}")
            return bloqueado

        self.inputs_sent += 1
        self._log("IN", f"{method} {path}\n{cuerpo_txt[:2000]}")

        try:
            status, texto = self._raw(method, path, body)
        except Exception as exc:  # noqa: BLE001
            salida = f"ERROR DE RED: {type(exc).__name__}: {exc}"
            self._log("OUT", salida)
            return salida

        texto = self._formatear(texto)
        if len(texto) > self.http.max_response_chars:
            texto = texto[: self.http.max_response_chars] + "\n… [respuesta truncada]"

        salida = f"HTTP {status}\n{texto}"
        self._log("OUT", salida)
        return salida

    def _formatear(self, texto: str) -> str:
        """JSON indentado: el agente lee mucho mejor una respuesta formateada."""
        try:
            return json.dumps(json.loads(texto), ensure_ascii=False, indent=1)
        except Exception:  # noqa: BLE001
            return texto

    def _raw(self, method: str, path: str, body: Any, con_token: bool = True) -> tuple[int, str]:
        url = path if path.startswith("http") else f"{self.http.base_url}/{path.lstrip('/')}"
        datos = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=datos, method=method)
        req.add_header("Accept", "application/json")
        if datos is not None:
            req.add_header("Content-Type", "application/json")
        if con_token and self._token:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=self.http.timeout_seconds) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            # Un 4xx no es una excepcion para el auditor: es informacion.
            return exc.code, exc.read().decode("utf-8", errors="replace")

    # -- compatibilidad con el arnes ---------------------------------------
    def status(self) -> str:
        elapsed = int(time.monotonic() - self.started_at) if self.started_at else 0
        return (
            f"modo=http api={self.http.base_url} vivo={self._alive} "
            f"identidad={self._identidad or 'sin sesion'} "
            f"pedidos={self.inputs_sent}/{self.cfg.limits.max_inputs_per_mission} "
            f"tiempo={elapsed}s/{self.cfg.limits.max_session_seconds}s"
        )
