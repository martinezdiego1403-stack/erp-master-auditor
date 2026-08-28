"""
Driver de navegador: maneja la interfaz web del ERP como lo haria una persona.

El driver HTTP alcanza para auditar reglas de negocio, pero no puede juzgar lo
que el usuario realmente sufre: cuantas teclas cuesta facturar, si un total se
muestra mal en pantalla aunque el dato este bien, si un error se explica o
aparece como un 409 crudo. Eso solo se ve manejando la pantalla.

Usa la API **asincronica** de Playwright: las tools del SDK corren dentro de un
event loop, y la API sincronica no se puede usar ahi adentro.

Es opcional: si Playwright no esta instalado, el arnes sigue funcionando en
modo API y las misiones que piden navegador avisan y se saltean.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import Config


def playwright_disponible() -> tuple[bool, str]:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False, (
            "Playwright no esta instalado. Para auditar la interfaz web:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        )
    return True, ""


class WebDriver:
    """Maneja la UI con un navegador headless. Superficie parecida al HttpDriver."""

    def __init__(self, cfg: Config, transcript_path: Path | None = None,
                 capturas_dir: Path | None = None) -> None:
        self.cfg = cfg
        self.web = cfg.erp.web
        self.transcript_path = transcript_path
        self.capturas_dir = capturas_dir
        self.acciones = 0
        self.started_at: float | None = None
        self._blocked = cfg.blocked_regexes
        self._pw = None
        self._browser = None
        self._page = None
        self._errores_consola: list[str] = []
        if transcript_path:
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
        if capturas_dir:
            capturas_dir.mkdir(parents=True, exist_ok=True)

    # -- transcript ---------------------------------------------------------
    def _log(self, marker: str, body: str) -> None:
        if not self.transcript_path:
            return
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        with self.transcript_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n--- [{stamp}] WEB {marker} ---\n{body}\n")

    # -- ciclo de vida ------------------------------------------------------
    async def start(self) -> str:
        ok, msg = playwright_disponible()
        if not ok:
            return msg

        from playwright.async_api import async_playwright

        await self.stop()
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.web.headless)
        contexto = await self._browser.new_context(
            viewport={"width": self.web.width, "height": self.web.height},
            locale="es-AR",
        )
        self._page = await contexto.new_page()
        self._page.set_default_timeout(self.web.timeout_ms)

        # Los errores de consola del navegador son hallazgos por si mismos.
        self._errores_consola = []
        self._page.on("console", lambda m: (
            self._errores_consola.append(f"{m.type}: {m.text[:300]}")
            if m.type in ("error", "warning") else None))
        self._page.on("pageerror", lambda e: self._errores_consola.append(f"pageerror: {str(e)[:300]}"))

        self.acciones = 0
        self.started_at = time.monotonic()
        self._log("START", self.web.base_url)

        try:
            await self._page.goto(self.web.base_url, wait_until="domcontentloaded")
        except Exception as exc:  # noqa: BLE001
            return f"NO SE PUDO ABRIR {self.web.base_url}: {type(exc).__name__}: {exc}"

        entrada = await self._login_ui()
        pantalla = await self.leer()
        return f"Navegador abierto en {self.web.base_url}\n{entrada}\n\n{pantalla}"

    async def _login_ui(self) -> str:
        """Entra por la pantalla de login, como lo haria el usuario."""
        if not self.web.login:
            return "Sin login configurado: se asume que la app no lo pide."
        try:
            await self._page.wait_for_timeout(800)
            await self._page.fill(self.web.login.selector_email, self.web.login.email)
            await self._page.fill(self.web.login.selector_password, self.web.login.password)
            await self._page.click(self.web.login.selector_submit)
            await self._page.wait_for_timeout(self.web.espera_ms)
            return f"Sesion iniciada por la interfaz como {self.web.login.email}"
        except Exception as exc:  # noqa: BLE001
            return (
                f"NO SE PUDO INICIAR SESION POR LA INTERFAZ ({type(exc).__name__}: {exc}). "
                "Revisa los selectores en erp.web.login o si la pantalla cambio. "
                "Que el login no funcione ya es un hallazgo."
            )

    async def stop(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self._page = None
        self._browser = None
        self._pw = None

    # -- limites ------------------------------------------------------------
    def budget_status(self) -> tuple[bool, str]:
        if self.acciones >= self.cfg.limits.max_inputs_per_mission:
            return False, (
                f"LIMITE ALCANZADO: {self.acciones} acciones en la interfaz. "
                "Cerra la mision y reporta lo que tengas."
            )
        if self.started_at is not None:
            elapsed = time.monotonic() - self.started_at
            if elapsed >= self.cfg.limits.max_session_seconds:
                return False, f"LIMITE ALCANZADO: {int(elapsed)}s de sesion."
        return True, ""

    def _guardia(self, texto: str) -> str | None:
        if self._page is None:
            return "El navegador no esta abierto. El arnes deberia haberlo abierto al arrancar la mision."
        ok, msg = self.budget_status()
        if not ok:
            return msg
        for rx in self._blocked:
            if rx.search(texto):
                return f"ACCION BLOQUEADA por la guarda de seguridad ({rx.pattern})."
        return None

    # -- acciones -----------------------------------------------------------
    async def ir(self, ruta: str) -> str:
        error = self._guardia(f"goto {ruta}")
        if error:
            return error
        url = ruta if ruta.startswith("http") else f"{self.web.base_url.rstrip('/')}/{ruta.lstrip('/')}"
        self.acciones += 1
        self._log("GOTO", url)
        try:
            await self._page.goto(url, wait_until="domcontentloaded")
            await self._page.wait_for_timeout(self.web.espera_ms)
        except Exception as exc:  # noqa: BLE001
            return f"ERROR AL NAVEGAR: {type(exc).__name__}: {exc}"
        return await self.leer()

    async def clic(self, objetivo: str) -> str:
        error = self._guardia(f"click {objetivo}")
        if error:
            return error
        self.acciones += 1
        self._log("CLICK", objetivo)
        try:
            await self._localizar(objetivo).first.click()
            await self._page.wait_for_timeout(self.web.espera_ms)
        except Exception as exc:  # noqa: BLE001
            return (
                f"NO SE PUDO HACER CLIC EN '{objetivo}': {type(exc).__name__}: {exc}\n"
                "Si el elemento deberia existir y no esta, es un hallazgo. "
                "Si no lo encontras, usa web_leer para ver que hay en pantalla."
            )
        return await self.leer()

    async def escribir(self, objetivo: str, valor: str) -> str:
        error = self._guardia(f"fill {objetivo} {valor}")
        if error:
            return error
        self.acciones += 1
        self._log("FILL", f"{objetivo} = {valor}")
        try:
            await self._localizar(objetivo).first.fill(valor)
            await self._page.wait_for_timeout(self.web.espera_ms)
        except Exception as exc:  # noqa: BLE001
            return f"NO SE PUDO ESCRIBIR EN '{objetivo}': {type(exc).__name__}: {exc}"
        return await self.leer()

    async def tecla(self, key: str) -> str:
        error = self._guardia(f"key {key}")
        if error:
            return error
        self.acciones += 1
        self._log("KEY", key)
        try:
            await self._page.keyboard.press(key)
            await self._page.wait_for_timeout(self.web.espera_ms)
        except Exception as exc:  # noqa: BLE001
            return f"NO SE PUDO ENVIAR LA TECLA '{key}': {type(exc).__name__}: {exc}"
        return await self.leer()

    def _localizar(self, objetivo: str):
        """Acepta 'texto:Guardar', 'label:Cliente', 'rol:button/Emitir' o un selector CSS."""
        page = self._page
        if objetivo.startswith("texto:"):
            return page.get_by_text(objetivo[6:], exact=False)
        if objetivo.startswith("label:"):
            return page.get_by_label(objetivo[6:], exact=False)
        if objetivo.startswith("placeholder:"):
            return page.get_by_placeholder(objetivo[12:], exact=False)
        if objetivo.startswith("rol:"):
            resto = objetivo[4:]
            if "/" in resto:
                rol, nombre = resto.split("/", 1)
                return page.get_by_role(rol.strip(), name=nombre.strip())
            return page.get_by_role(resto.strip())
        return page.locator(objetivo)

    # -- lectura ------------------------------------------------------------
    async def leer(self) -> str:
        """Texto visible + controles con los que se puede interactuar."""
        if self._page is None:
            return "El navegador no esta abierto."
        try:
            texto = await self._page.inner_text("body")
        except Exception as exc:  # noqa: BLE001
            return f"NO SE PUDO LEER LA PANTALLA: {type(exc).__name__}: {exc}"

        texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
        if len(texto) > self.web.max_chars:
            texto = texto[: self.web.max_chars] + "\n… [pantalla truncada]"

        partes = [f"URL: {self._page.url}", "", "--- LO QUE SE VE ---", texto]

        controles = await self._controles()
        if controles:
            partes += ["", "--- CON QUE SE PUEDE INTERACTUAR ---", controles]

        if self._errores_consola:
            partes += ["", "--- ERRORES DEL NAVEGADOR (son hallazgos) ---",
                       "\n".join(self._errores_consola[-10:])]
            self._errores_consola.clear()

        salida = "\n".join(partes)
        self._log("READ", salida[:3000])
        return salida

    async def _controles(self) -> str:
        """Inventario de controles: sin esto el agente tiene que adivinar selectores."""
        js = """
        () => {
          const vis = e => { const r = e.getBoundingClientRect();
            return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
          const out = [];
          for (const e of document.querySelectorAll('button, a[href], input, select, textarea, [role=button]')) {
            if (!vis(e)) continue;
            const tag = e.tagName.toLowerCase();
            const etiqueta = (e.getAttribute('aria-label') || e.placeholder || e.name ||
                              e.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
            const tipo = e.type ? `[${e.type}]` : '';
            const valor = (e.value !== undefined && e.value !== '' && e.type !== 'password')
                          ? ` = ${String(e.value).slice(0, 30)}` : '';
            out.push(`${tag}${tipo} "${etiqueta}"${valor}`);
          }
          return out.slice(0, 80);
        }
        """
        try:
            items = await self._page.evaluate(js)
        except Exception:  # noqa: BLE001
            return ""
        return "\n".join(f"  {i}" for i in items)

    async def captura(self, nombre: str) -> str:
        if self._page is None or not self.capturas_dir:
            return "No hay navegador abierto o no se configuro carpeta de capturas."
        limpio = re.sub(r"[^A-Za-z0-9_-]+", "-", nombre)[:60] or "pantalla"
        destino = self.capturas_dir / f"{limpio}.png"
        try:
            await self._page.screenshot(path=str(destino), full_page=True)
        except Exception as exc:  # noqa: BLE001
            return f"NO SE PUDO CAPTURAR: {type(exc).__name__}: {exc}"
        self._log("SHOT", str(destino))
        return f"Captura guardada en {destino.name} (queda en la carpeta de la corrida)."

    def status(self) -> str:
        elapsed = int(time.monotonic() - self.started_at) if self.started_at else 0
        return (
            f"navegador={'abierto' if self._page else 'cerrado'} "
            f"url={self._page.url if self._page else '-'} "
            f"acciones={self.acciones}/{self.cfg.limits.max_inputs_per_mission} "
            f"tiempo={elapsed}s/{self.cfg.limits.max_session_seconds}s"
        )
