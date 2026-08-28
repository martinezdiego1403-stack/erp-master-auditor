"""Carga de misiones desde prompts/missions/*.md con front matter YAML."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Mission:
    key: str            # 01_lunes_0800
    title: str
    mode: str
    body: str
    reset_db: bool = False
    no_console: bool = False
    path: Path | None = None
    # Modelo propio para esta mision (las de descubrimiento pueden ir con uno
    # mas barato; la sintesis conviene con el mejor). None = el de la config.
    model: str | None = None
    # Requiere manejar la interfaz web con navegador (tools web_*).
    needs_browser: bool = False

    @property
    def order(self) -> str:
        return self.key.split("_", 1)[0]


def load_mission(path: Path) -> Mission:
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    m = FRONT_MATTER.match(text)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        text = text[m.end():]
    key = path.stem
    return Mission(
        key=key,
        title=str(meta.get("title") or key),
        mode=str(meta.get("mode") or "AUDIT MODE"),
        body=text.strip(),
        reset_db=bool(meta.get("reset_db", False)),
        no_console=bool(meta.get("no_console", False)),
        path=path,
        model=(str(meta["model"]) if meta.get("model") else None),
        needs_browser=bool(meta.get("needs_browser", False)),
    )


def load_all(missions_dir: Path) -> list[Mission]:
    return [load_mission(p) for p in sorted(missions_dir.glob("*.md"))]


def resolve(missions_dir: Path, name: str) -> Mission:
    """Acepta el nombre completo, el prefijo numerico, o una subcadena."""
    all_missions = load_all(missions_dir)
    name = name.strip().lower().removesuffix(".md")
    for m in all_missions:
        if m.key.lower() == name:
            return m
    for m in all_missions:
        if m.order == name.zfill(2):
            return m
    matches = [m for m in all_missions if name in m.key.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"'{name}' es ambiguo: {', '.join(m.key for m in matches)}")
    raise ValueError(
        f"No existe la mision '{name}'. Disponibles: {', '.join(m.key for m in all_missions)}"
    )
