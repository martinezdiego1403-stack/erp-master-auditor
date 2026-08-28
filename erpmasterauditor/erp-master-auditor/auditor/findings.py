"""
Store de hallazgos.

Cada hallazgo del auditor se guarda estructurado (secciones 18, 26 y 27 del
charter) para que despues se pueda: priorizar automaticamente, generar backlog,
comparar contra auditorias anteriores y emitir tests de regresion.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

STATUSES = {"PASS", "FAIL", "WARNING", "BLOCKED", "NOT_IMPLEMENTED", "NOT_TESTABLE"}
EVIDENCE = {"CONFIRMADO", "PARCIAL", "NO_CONFIRMADO", "FALTANTE"}
TYPES = {
    "BUG", "MISSING", "PARTIAL", "RISK", "UX", "SECURITY",
    "PERFORMANCE", "DATA_INTEGRITY", "OPPORTUNITY",
}
CATEGORIES = {"CORE", "EXPECTED", "DIFFERENTIATOR", "INNOVATION"}
AUTOMATION = {"NONE", "SIMPLE", "AVANZADA", "IA"}

PRIORITY_ORDER = {"CRITICO": 0, "ALTO": 1, "MEDIO": 2, "BAJO": 3}
PRIORITY_EMOJI = {"CRITICO": "[C]", "ALTO": "[A]", "MEDIO": "[M]", "BAJO": "[B]"}


def _clamp(v: Any, lo: int = 1, hi: int = 5, default: int = 3) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _norm(value: Any, allowed: set[str], default: str) -> str:
    s = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    return s if s in allowed else default


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:60] or "sin-titulo"


@dataclass
class Finding:
    id: str
    mission: str
    module: str
    title: str
    type: str
    status: str
    evidence_level: str
    business_need: str = ""
    expected: str = ""
    observed: str = ""
    repro_steps: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    impact: int = 3
    urgency: int = 3
    risk: int = 3
    complexity: int = 3
    proposed_solution: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    affected_user: str = ""
    category: str = "EXPECTED"
    automation: str = "NONE"
    severity_score: float = 0.0
    priority: str = "MEDIO"
    quick_win: bool = False
    fingerprint: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_priority(impact: int, urgency: int, risk: int, complexity: int) -> tuple[float, str, bool]:
    """Severidad ponderada 1-5. El impacto y el riesgo pesan mas que la urgencia."""
    severity = round(impact * 0.40 + risk * 0.35 + urgency * 0.25, 2)
    if severity >= 4.2:
        priority = "CRITICO"
    elif severity >= 3.4:
        priority = "ALTO"
    elif severity >= 2.4:
        priority = "MEDIO"
    else:
        priority = "BAJO"
    quick_win = complexity <= 2 and severity >= 3.0
    return severity, priority, quick_win


class FindingStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.items: list[Finding] = []
        if self.path.exists():
            self.items = list(load_findings(self.path))

    def next_id(self) -> str:
        return f"F-{len(self.items) + 1:04d}"

    def add(self, mission: str, data: dict[str, Any]) -> Finding:
        impact = _clamp(data.get("impact"))
        urgency = _clamp(data.get("urgency"))
        risk = _clamp(data.get("risk"))
        complexity = _clamp(data.get("complexity"))
        severity, priority, quick_win = compute_priority(impact, urgency, risk, complexity)

        module = str(data.get("module") or "SIN_MODULO").strip()
        title = str(data.get("title") or "").strip()

        f = Finding(
            id=self.next_id(),
            mission=mission,
            module=module,
            title=title,
            type=_norm(data.get("type"), TYPES, "BUG"),
            status=_norm(data.get("status"), STATUSES, "FAIL"),
            evidence_level=_norm(data.get("evidence_level"), EVIDENCE, "NO_CONFIRMADO"),
            business_need=str(data.get("business_need") or "").strip(),
            expected=str(data.get("expected") or "").strip(),
            observed=str(data.get("observed") or "").strip(),
            repro_steps=[str(s) for s in (data.get("repro_steps") or [])],
            evidence=[str(s) for s in (data.get("evidence") or [])],
            impact=impact,
            urgency=urgency,
            risk=risk,
            complexity=complexity,
            proposed_solution=str(data.get("proposed_solution") or "").strip(),
            acceptance_criteria=[str(s) for s in (data.get("acceptance_criteria") or [])],
            dependencies=[str(s) for s in (data.get("dependencies") or [])],
            affected_user=str(data.get("affected_user") or "").strip(),
            category=_norm(data.get("category"), CATEGORIES, "EXPECTED"),
            automation=_norm(data.get("automation"), AUTOMATION, "NONE"),
            severity_score=severity,
            priority=priority,
            quick_win=quick_win,
            fingerprint=fingerprint(module, title),
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.items.append(f)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(f.to_dict(), ensure_ascii=False) + "\n")
        return f

    def sorted_items(self) -> list[Finding]:
        return sorted(
            self.items,
            key=lambda f: (PRIORITY_ORDER.get(f.priority, 9), -f.severity_score, f.module),
        )

    def by_module(self) -> dict[str, list[Finding]]:
        out: dict[str, list[Finding]] = {}
        for f in self.sorted_items():
            out.setdefault(f.module, []).append(f)
        return out

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for f in self.items:
            c[f.priority] = c.get(f.priority, 0) + 1
        return c


def fingerprint(module: str, title: str) -> str:
    """Huella estable para comparar el mismo problema entre auditorias."""
    key = f"{_slug(module)}::{_slug(title)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def load_findings(path: Path) -> Iterable[Finding]:
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        known = {k: v for k, v in raw.items() if k in Finding.__dataclass_fields__}
        yield Finding(**known)


# --------------------------------------------------------------------------
# Renderizado a markdown
# --------------------------------------------------------------------------
def qa_matrix_md(items: list[Finding]) -> str:
    rows = [
        "| ID | Modulo | Titulo | Estado | Evidencia | Prio | I/U/R/C |",
        "| -- | ------ | ------ | ------ | --------- | ---- | ------- |",
    ]
    for f in items:
        title = f.title.replace("|", "\\|")
        rows.append(
            f"| {f.id} | {f.module} | {title} | {f.status} | {f.evidence_level} | "
            f"{PRIORITY_EMOJI.get(f.priority,'')} {f.priority} | "
            f"{f.impact}/{f.urgency}/{f.risk}/{f.complexity} |"
        )
    return "\n".join(rows)


def backlog_md(items: list[Finding]) -> str:
    out: list[str] = []
    for f in items:
        out.append(f"### {f.id} — {f.title}")
        out.append("")
        out.append(f"- **Modulo:** {f.module}")
        out.append(f"- **Tipo / Estado:** {f.type} / {f.status} ({f.evidence_level})")
        out.append(
            f"- **Prioridad:** {f.priority} (severidad {f.severity_score}) — "
            f"impacto {f.impact}, urgencia {f.urgency}, riesgo {f.risk}, complejidad {f.complexity}"
            + ("  **QUICK WIN**" if f.quick_win else "")
        )
        out.append(f"- **Categoria:** {f.category}" + (f" | **Automatizacion:** {f.automation}" if f.automation != "NONE" else ""))
        if f.affected_user:
            out.append(f"- **Usuario afectado:** {f.affected_user}")
        if f.business_need:
            out.append(f"- **Necesidad empresarial:** {f.business_need}")
        if f.expected:
            out.append(f"- **Esperado:** {f.expected}")
        if f.observed:
            out.append(f"- **Observado:** {f.observed}")
        if f.repro_steps:
            out.append("- **Reproduccion:**")
            out.extend(f"  {i}. {s}" for i, s in enumerate(f.repro_steps, 1))
        if f.evidence:
            out.append("- **Evidencia:**")
            out.extend(f"  - {s}" for s in f.evidence)
        if f.proposed_solution:
            out.append(f"- **Solucion propuesta:** {f.proposed_solution}")
        if f.acceptance_criteria:
            out.append("- **Criterios de aceptacion:**")
            out.extend(f"  - [ ] {s}" for s in f.acceptance_criteria)
        if f.dependencies:
            out.append(f"- **Dependencias:** {', '.join(f.dependencies)}")
        out.append(f"- **Fingerprint:** `{f.fingerprint}`")
        out.append("")
    return "\n".join(out)
