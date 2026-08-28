"""
Generacion de reportes.

El reporte tiene dos mitades deliberadamente distintas:

  - La parte deterministica (esta) arma la matriz QA, el backlog priorizado y
    la comparacion contra auditorias anteriores. No opina: cuenta.
  - La parte de juicio (Maturity Score, veredicto, roadmap) la escribe el
    agente en la mision 99_sintesis, porque requiere criterio y no se puede
    calcular sumando hallazgos.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .findings import (
    PRIORITY_ORDER,
    Finding,
    FindingStore,
    backlog_md,
    load_findings,
    qa_matrix_md,
)


def build_report(run_dir: Path, store: FindingStore) -> Path:
    items = store.sorted_items()
    counts = store.counts()
    by_module = store.by_module()

    lines: list[str] = [
        "# Auditoria del ERP — reporte de hallazgos",
        "",
        f"_Corrida `{run_dir.name}` · {datetime.now():%Y-%m-%d %H:%M} · "
        f"{len(items)} hallazgos_",
        "",
        "## Tablero",
        "",
        "| Prioridad | Cantidad |",
        "| --------- | -------: |",
    ]
    for p in ("CRITICO", "ALTO", "MEDIO", "BAJO"):
        lines.append(f"| {p} | {counts.get(p, 0)} |")

    lines += ["", "### Por modulo", "", "| Modulo | Total | Criticos | Altos |", "| ------ | ----: | -------: | ----: |"]
    for module, fs in sorted(by_module.items(), key=lambda kv: -len(kv[1])):
        crit = sum(1 for f in fs if f.priority == "CRITICO")
        alto = sum(1 for f in fs if f.priority == "ALTO")
        lines.append(f"| {module} | {len(fs)} | {crit} | {alto} |")

    quick = [f for f in items if f.quick_win]
    if quick:
        lines += ["", "### Quick wins (alto impacto, baja complejidad)", ""]
        lines += [f"- **{f.id}** {f.module} — {f.title}" for f in quick]

    blockers = [f for f in items if f.evidence_level == "NO_CONFIRMADO"]
    if blockers:
        lines += [
            "",
            f"> {len(blockers)} hallazgos quedaron como NO_CONFIRMADO: requieren verificacion "
            "manual antes de tomarlos como ciertos.",
        ]

    lines += ["", "---", "", "## Matriz QA", "", qa_matrix_md(items), ""]
    lines += ["---", "", "## Backlog priorizado", "", backlog_md(items)]

    # Sintesis del agente, si la mision 99 corrio.
    synth = run_dir / "99_sintesis.log.md"
    if synth.exists():
        lines += ["", "---", "", "# Sintesis, madurez y veredicto", "",
                  synth.read_text(encoding="utf-8")]

    smap = run_dir / "system_map.md"
    if smap.exists():
        lines += ["", "---", "", "# Mapa del sistema", "", smap.read_text(encoding="utf-8")]

    regression = run_dir / "regression"
    if regression.exists():
        tests = sorted(p.name for p in regression.glob("*.Tests.ps1"))
        if tests:
            lines += [
                "", "---", "",
                "# Tests de regresion generados",
                "",
                "Estos tests describen el comportamiento **correcto**: van a fallar hasta que "
                "el bug este arreglado, y despues quedan como red de seguridad permanente.",
                "",
            ]
            lines += [f"- `regression/{t}`" for t in tests]

    path = run_dir / "REPORT.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# CONTINUOUS AUDIT MODE
# --------------------------------------------------------------------------
def compare_runs(prev_dir: Path, curr_dir: Path) -> str:
    prev_path = prev_dir / "findings.jsonl"
    curr_path = curr_dir / "findings.jsonl"
    if not prev_path.exists():
        return f"No hay hallazgos en {prev_dir}."

    prev = {f.fingerprint: f for f in load_findings(prev_path)}
    curr = {f.fingerprint: f for f in load_findings(curr_path)} if curr_path.exists() else {}

    resolved = [f for k, f in prev.items() if k not in curr]
    persistent = [curr[k] for k in curr if k in prev]
    new = [f for k, f in curr.items() if k not in prev]

    # Regresion: el mismo hallazgo que antes estaba OK y ahora falla, o que empeoro.
    regressions: list[tuple[Finding, Finding]] = []
    for k, f in curr.items():
        old = prev.get(k)
        if not old:
            continue
        worse_status = old.status == "PASS" and f.status in ("FAIL", "WARNING")
        worse_priority = PRIORITY_ORDER.get(f.priority, 9) < PRIORITY_ORDER.get(old.priority, 9)
        if worse_status or worse_priority:
            regressions.append((old, f))

    def block(title: str, fs: list[Finding]) -> list[str]:
        out = [f"## {title} ({len(fs)})", ""]
        if not fs:
            out += ["_ninguno_", ""]
            return out
        out += [f"- **{f.id}** [{f.priority}] {f.module} — {f.title}" for f in
                sorted(fs, key=lambda x: PRIORITY_ORDER.get(x.priority, 9))]
        out.append("")
        return out

    lines = [
        "# Auditoria continua",
        "",
        f"_Comparando `{prev_dir.name}` -> `{curr_dir.name}`_",
        "",
        f"| | Anterior | Actual |",
        f"| --- | ---: | ---: |",
        f"| Hallazgos totales | {len(prev)} | {len(curr)} |",
        f"| Criticos | {sum(1 for f in prev.values() if f.priority=='CRITICO')} "
        f"| {sum(1 for f in curr.values() if f.priority=='CRITICO')} |",
        "",
    ]
    lines += block("Solucionados (ya no aparecen)", resolved)
    lines += block("Persisten", persistent)
    lines += block("Nuevos", new)

    lines += [f"## Regresiones ({len(regressions)})", ""]
    if regressions:
        for old, cur in regressions:
            lines.append(
                f"- **{cur.id}** {cur.module} — {cur.title}: "
                f"{old.status}/{old.priority} -> {cur.status}/{cur.priority}"
            )
    else:
        lines.append("_ninguna_")
    lines.append("")

    lines += [
        "> Nota: 'solucionado' aca significa que el hallazgo no volvio a aparecer en esta corrida. "
        "Si la mision que lo detecto no se ejecuto, tambien desaparece. Contrasta con los tests "
        "de regresion, que si son prueba positiva de que el bug esta arreglado.",
    ]
    return "\n".join(lines)
