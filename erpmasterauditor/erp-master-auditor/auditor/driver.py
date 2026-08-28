"""
Driver de consola: mantiene vivo el proceso del ERP y expone lectura/escritura
en un formato que un agente puede usar turno a turno.

Dos backends:

  PipeBackend  subprocess con stdin/stdout redirigidos. Simple y rapido.
               Sirve cuando el ERP lee con Read-Host / Console.ReadLine().

  PtyBackend   ConPTY real via pywinpty. Necesario cuando el ERP usa
               Console.ReadKey(), colores ANSI, o redibuja la pantalla,
               porque esas APIs fallan o se degradan con pipes redirigidos.

El problema central de manejar una app interactiva desde afuera es saber
"cuando termino de escribir". No hay senal explicita, asi que se usa una
heuristica de quiet period: se lee hasta que pasan N ms sin bytes nuevos,
o hasta que aparece el patron del prompt (ready_pattern), lo que ocurra
primero, con un techo duro de max_wait_ms.
"""
from __future__ import annotations

import codecs
import os
import queue
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .config import Config, ErpConfig, resolved_env

# Secuencias ANSI: CSI, OSC y escapes de dos caracteres.
ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b[@-Z\\-_]"
)

# Teclas especiales para el backend pty (y las que tengan sentido en pipe).
KEYS = {
    "enter": "\r",
    "tab": "\t",
    "esc": "\x1b",
    "backspace": "\x7f",
    "space": " ",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "pageup": "\x1b[5~",
    "pagedown": "\x1b[6~",
    "delete": "\x1b[3~",
    "insert": "\x1b[2~",
    "ctrl+c": "\x03",
    "f1": "\x1bOP", "f2": "\x1bOQ", "f3": "\x1bOR", "f4": "\x1bOS",
    "f5": "\x1b[15~", "f6": "\x1b[17~", "f7": "\x1b[18~", "f8": "\x1b[19~",
    "f9": "\x1b[20~", "f10": "\x1b[21~", "f11": "\x1b[23~", "f12": "\x1b[24~",
}


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


class ProcessDied(RuntimeError):
    """El proceso del ERP no esta vivo cuando se esperaba que lo estuviera."""


class Backend(Protocol):
    def start(self) -> None: ...
    def write(self, data: str) -> None: ...
    def drain(self) -> str: ...
    def is_alive(self) -> bool: ...
    def exit_code(self) -> int | None: ...
    def stop(self) -> None: ...


# --------------------------------------------------------------------------
# Backend de pipes
# --------------------------------------------------------------------------
class PipeBackend:
    def __init__(self, cfg: ErpConfig) -> None:
        self.cfg = cfg
        self.proc: subprocess.Popen[bytes] | None = None
        self._q: queue.Queue[str] = queue.Queue()
        self._decoder = codecs.getincrementaldecoder(cfg.encoding)("replace")
        self._reader: threading.Thread | None = None

    def start(self) -> None:
        self.stop()
        self._q = queue.Queue()
        self._decoder = codecs.getincrementaldecoder(self.cfg.encoding)("replace")
        creationflags = 0
        if os.name == "nt":
            # Evita que se abra una ventana de consola extra.
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            self.cfg.command,
            cwd=self.cfg.cwd,
            env=resolved_env(self.cfg),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=creationflags,
        )
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _pump(self) -> None:
        proc = self.proc
        assert proc is not None and proc.stdout is not None
        try:
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                self._q.put(self._decoder.decode(chunk))
        except (OSError, ValueError):
            pass
        finally:
            tail = self._decoder.decode(b"", final=True)
            if tail:
                self._q.put(tail)

    def write(self, data: str) -> None:
        if not self.proc or not self.proc.stdin:
            raise ProcessDied("El ERP no esta iniciado")
        if self.proc.poll() is not None:
            raise ProcessDied(f"El ERP termino con codigo {self.proc.returncode}")
        self.proc.stdin.write(data.encode(self.cfg.encoding, errors="replace"))
        self.proc.stdin.flush()

    def drain(self) -> str:
        out: list[str] = []
        while True:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return "".join(out)

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def exit_code(self) -> int | None:
        return self.proc.poll() if self.proc else None

    def stop(self) -> None:
        if not self.proc:
            return
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        except Exception:
            pass
        finally:
            for stream in (self.proc.stdin, self.proc.stdout):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass
            self.proc = None


# --------------------------------------------------------------------------
# Backend ConPTY (pywinpty)
# --------------------------------------------------------------------------
class PtyBackend:
    def __init__(self, cfg: ErpConfig) -> None:
        self.cfg = cfg
        self.pty = None
        self._q: queue.Queue[str] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._screen = None
        self._stream = None

    def start(self) -> None:
        try:
            from winpty import PtyProcess  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "backend 'pty' requiere pywinpty: pip install pywinpty"
            ) from exc

        self.stop()
        self._q = queue.Queue()
        self.pty = PtyProcess.spawn(
            list(self.cfg.command),
            cwd=self.cfg.cwd,
            env=resolved_env(self.cfg),
            dimensions=(self.cfg.rows, self.cfg.cols),
        )
        self._init_screen()
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _init_screen(self) -> None:
        try:
            import pyte  # type: ignore
        except ImportError:
            self._screen = None
            self._stream = None
            return
        self._screen = pyte.Screen(self.cfg.cols, self.cfg.rows)
        self._stream = pyte.Stream(self._screen)

    def _pump(self) -> None:
        pty = self.pty
        assert pty is not None
        try:
            while True:
                data = pty.read(4096)
                if not data:
                    if not pty.isalive():
                        break
                    time.sleep(0.02)
                    continue
                if isinstance(data, bytes):
                    data = data.decode(self.cfg.encoding, errors="replace")
                if self._stream is not None:
                    try:
                        self._stream.feed(data)
                    except Exception:
                        pass
                self._q.put(data)
        except EOFError:
            pass
        except Exception:
            pass

    def write(self, data: str) -> None:
        if not self.pty or not self.pty.isalive():
            raise ProcessDied("El ERP no esta iniciado o ya termino")
        self.pty.write(data)

    def drain(self) -> str:
        out: list[str] = []
        while True:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return "".join(out)

    def screen(self) -> str | None:
        if self._screen is None:
            return None
        return "\n".join(line.rstrip() for line in self._screen.display)

    def is_alive(self) -> bool:
        return self.pty is not None and self.pty.isalive()

    def exit_code(self) -> int | None:
        if self.pty is None:
            return None
        try:
            return self.pty.exitstatus
        except Exception:
            return None

    def stop(self) -> None:
        if not self.pty:
            return
        try:
            self.pty.terminate(force=True)
        except Exception:
            pass
        finally:
            self.pty = None


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
class ConsoleDriver:
    """Envuelve un backend con transcript, limites y guardas de input."""

    def __init__(self, cfg: Config, transcript_path: Path | None = None) -> None:
        self.cfg = cfg
        self.backend: Backend = (
            PtyBackend(cfg.erp) if cfg.erp.backend == "pty" else PipeBackend(cfg.erp)
        )
        self.transcript_path = transcript_path
        self.inputs_sent = 0
        self.started_at: float | None = None
        self._blocked = cfg.blocked_regexes
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
        self.backend.start()
        self.inputs_sent = 0
        self.started_at = time.monotonic()
        self._log("START", " ".join(self.cfg.erp.command))
        return self.read()

    def reset_database(self) -> str:
        cmd = self.cfg.reset.command
        if not cmd:
            return "reset no configurado (reset.command = null)"
        proc = subprocess.run(
            cmd,
            cwd=self.cfg.erp.cwd,
            capture_output=True,
            text=True,
            timeout=self.cfg.reset.timeout_seconds,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        self._log("RESET-DB", out[-4000:])
        return f"reset rc={proc.returncode}\n{out[-2000:]}"

    def stop(self) -> None:
        self._log("STOP", f"inputs={self.inputs_sent}")
        self.backend.stop()

    # -- limites ------------------------------------------------------------
    def budget_status(self) -> tuple[bool, str]:
        if self.inputs_sent >= self.cfg.limits.max_inputs_per_mission:
            return False, (
                f"LIMITE ALCANZADO: {self.inputs_sent} inputs enviados en esta mision. "
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

    # -- io -----------------------------------------------------------------
    def check_input(self, text: str) -> str | None:
        for rx in self._blocked:
            if rx.search(text):
                return f"INPUT BLOQUEADO por la guarda de seguridad ({rx.pattern}). No se envio nada."
        return None

    def send(self, text: str, wait_ms: int | None = None, newline: bool = True) -> str:
        ok, msg = self.budget_status()
        if not ok:
            return msg
        blocked = self.check_input(text)
        if blocked:
            self._log("BLOCKED", text)
            return blocked
        if not self.backend.is_alive():
            code = self.backend.exit_code()
            return (
                f"EL ERP NO ESTA CORRIENDO (exit code {code}). "
                "Usa erp_start para levantarlo de nuevo. "
                "Si termino inesperadamente, eso en si mismo es un hallazgo."
            )
        payload = text + ("\r\n" if newline else "")
        self.backend.write(payload)
        self.inputs_sent += 1
        self._log("IN", text)
        return self.read(wait_ms=wait_ms)

    def send_key(self, key: str, wait_ms: int | None = None) -> str:
        seq = KEYS.get(key.strip().lower())
        if seq is None:
            return f"Tecla desconocida: {key}. Disponibles: {', '.join(sorted(KEYS))}"
        return self.send(seq, wait_ms=wait_ms, newline=False)

    def read(self, wait_ms: int | None = None) -> str:
        """Lee hasta el quiet period, el ready_pattern o el techo de espera."""
        quiet = self.cfg.erp.quiet_ms / 1000.0
        max_wait = (wait_ms if wait_ms is not None else self.cfg.erp.max_wait_ms) / 1000.0
        ready = re.compile(self.cfg.erp.ready_pattern) if self.cfg.erp.ready_pattern else None

        chunks: list[str] = []
        deadline = time.monotonic() + max_wait
        last_data: float | None = None

        while True:
            piece = self.backend.drain()
            if piece:
                chunks.append(piece)
                last_data = time.monotonic()

            text = "".join(chunks)
            now = time.monotonic()

            if ready and text and ready.search(strip_ansi(text)):
                break
            if last_data is not None and now - last_data >= quiet:
                break
            if now >= deadline:
                break
            if not self.backend.is_alive():
                # Drenar lo que quede y salir.
                time.sleep(0.05)
                rest = self.backend.drain()
                if rest:
                    chunks.append(rest)
                break
            time.sleep(0.02)

        raw = "".join(chunks)
        clean = strip_ansi(raw)
        self._log("OUT", clean)
        if not clean.strip():
            if not self.backend.is_alive():
                return f"[sin salida — el ERP termino con codigo {self.backend.exit_code()}]"
            return "[sin salida en el tiempo de espera — el ERP puede estar esperando otro input, colgado, o tardando]"
        return clean

    def screen(self) -> str:
        if isinstance(self.backend, PtyBackend):
            s = self.backend.screen()
            if s is None:
                return "erp_screen requiere pyte instalado (pip install pyte). Usa erp_read."
            return s
        return "erp_screen solo esta disponible con backend 'pty'. Usa erp_read."

    def status(self) -> str:
        elapsed = int(time.monotonic() - self.started_at) if self.started_at else 0
        return (
            f"vivo={self.backend.is_alive()} exit_code={self.backend.exit_code()} "
            f"inputs={self.inputs_sent}/{self.cfg.limits.max_inputs_per_mission} "
            f"tiempo={elapsed}s/{self.cfg.limits.max_session_seconds}s "
            f"backend={self.cfg.erp.backend}"
        )
