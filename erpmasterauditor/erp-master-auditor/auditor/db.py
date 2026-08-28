"""Acceso de SOLO LECTURA a la base del ERP.

Sirve para que el auditor pueda contrastar lo que la consola *dice* que paso
contra lo que realmente quedo en los datos. En un ERP la mayoria de los bugs
caros viven exactamente en esa brecha (totales que no cierran, stock que no
se descuenta, cuenta corriente que no se actualiza).
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from .config import DatabaseConfig

# Solo se permite una sentencia de lectura. Sin punto y coma extra, sin DDL/DML.
_READ_ONLY = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|merge|exec|execute|grant|revoke|backup|restore)\b",
    re.IGNORECASE,
)


class ReadOnlyViolation(ValueError):
    pass


def guard(sql: str) -> str:
    stripped = sql.strip().rstrip(";").strip()
    if not _READ_ONLY.match(stripped):
        raise ReadOnlyViolation("Solo se permiten consultas SELECT / WITH.")
    if ";" in stripped:
        raise ReadOnlyViolation("Una sola sentencia por consulta (sin ';').")
    if _FORBIDDEN.search(stripped):
        raise ReadOnlyViolation("La consulta contiene palabras de escritura. Rechazada.")
    return stripped


def _connect(cfg: DatabaseConfig):
    if cfg.kind == "sqlite":
        con = sqlite3.connect(cfg.connection_string)
        con.row_factory = sqlite3.Row
        return con
    if cfg.kind == "sqlserver":
        import pyodbc  # type: ignore
        return pyodbc.connect(cfg.connection_string, readonly=True, autocommit=True)
    if cfg.kind == "postgres":
        import psycopg  # type: ignore
        return psycopg.connect(cfg.connection_string)
    raise ValueError(f"database.kind no soportado: {cfg.kind}")


def run_query(cfg: DatabaseConfig, sql: str, max_rows: int | None = None) -> str:
    if not cfg.enabled:
        return "Acceso a base deshabilitado en config (database.enabled = false)."
    limit = min(int(max_rows or cfg.max_rows), cfg.max_rows)
    try:
        clean = guard(sql)
    except ReadOnlyViolation as exc:
        return f"CONSULTA RECHAZADA: {exc}"

    con = None
    try:
        con = _connect(cfg)
        cur = con.cursor()
        cur.execute(clean)
        cols = [d[0] for d in (cur.description or [])]
        rows = cur.fetchmany(limit)
        if not rows:
            return f"(0 filas)\ncolumnas: {', '.join(cols) or '-'}"
        return _format_table(cols, [list(r) for r in rows], limit)
    except Exception as exc:  # noqa: BLE001 - se reporta al agente tal cual
        return f"ERROR DE BASE: {type(exc).__name__}: {exc}"
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass


def _format_table(cols: list[str], rows: list[list[Any]], limit: int) -> str:
    def cell(v: Any) -> str:
        s = "NULL" if v is None else str(v)
        return s if len(s) <= 40 else s[:37] + "..."

    body = [[cell(v) for v in r] for r in rows]
    widths = [max(len(c), *(len(r[i]) for r in body)) for i, c in enumerate(cols)]
    lines = [
        " | ".join(c.ljust(widths[i]) for i, c in enumerate(cols)),
        "-+-".join("-" * w for w in widths),
    ]
    lines += [" | ".join(v.ljust(widths[i]) for i, v in enumerate(r)) for r in body]
    note = f"\n({len(rows)} filas, tope {limit})"
    return "\n".join(lines) + note
