"""Layer 6: the public board.

A registry that lists whatever it is handed is a directory. A registry that can
REFUSE is a rating. So nothing is listed until it has been re-verified here,
from the bundle's own bytes:

  RECOMPUTE   every number in `results.checks[].expect` is derived again from
              assay.json. A headline that no longer follows from the evidence
              is rejected, not footnoted.
  RE-HASH     every file in `evidence` is hashed again. A bundle edited after
              issue fails, which is the only reason listing the hashes was
              worth doing.
  FLOOR       a row whose material a naive probe can already reach is marked
              UNCALIBRATED on the board, because a coverage number against it
              cannot be read and quietly listing it would launder that.

**The rejected rows are published with their reasons.** An acceptance rate is
meaningless without them, and a board that shows only what passed is making the
same omission its own tool exists to catch.

No wall clock anywhere, so rebuilding is byte-identical and a diff in the
published index means something actually changed.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field

from .certificate import ARTIFACT, SCOPE, _recomputed
from .model import AssayError

SCHEMA = 1


@dataclass(frozen=True)
class Row:
    rubric_id: str
    specimen_set_id: str
    material_sha: str
    classes: int
    covered: int
    residual: tuple[str, ...]
    floor: float
    difficulty: float
    earned: float | None          # None when the floor is 100%
    evasion_rate: float | None    # None when no attack was run
    decoration: int
    uncalibrated: bool
    underpowered: tuple[str, ...]   # classes whose verdict the sample cannot hold up
    path: str

    @property
    def coverage(self) -> float:
        return self.covered / self.classes if self.classes else 0.0


@dataclass(frozen=True)
class Rejection:
    path: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Registry:
    rows: tuple[Row, ...]
    rejected: tuple[Rejection, ...]

    @property
    def accepted(self) -> int:
        return len(self.rows)

    @property
    def acceptance_rate(self) -> float | None:
        total = len(self.rows) + len(self.rejected)
        return len(self.rows) / total if total else None


def verify(cert_dir: pathlib.Path) -> tuple[Row | None, tuple[str, ...]]:
    """Re-verify one certificate directory. Returns (row, reasons-it-failed)."""
    reasons: list[str] = []
    vac_path, art_path = cert_dir / "vac.json", cert_dir / ARTIFACT
    if not vac_path.exists():
        return None, ("no vac.json",)
    if not art_path.exists():
        return None, (f"no {ARTIFACT}",)

    try:
        man = json.loads(vac_path.read_text())
        aj = json.loads(art_path.read_text())
    except json.JSONDecodeError as exc:
        return None, (f"unreadable json: {exc}",)

    if man.get("vac_version") != "0.2":
        reasons.append(f"vac_version {man.get('vac_version')!r}, expected '0.2'")

    # RE-HASH: a bundle edited after issue must fail here.
    for e in man.get("evidence", []):
        p = cert_dir / e["path"]
        if not p.exists():
            reasons.append(f"evidence missing: {e['path']}")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != e["sha256"]:
            reasons.append(f"evidence changed since issue: {e['path']}")
    listed = {e["path"] for e in man.get("evidence", [])}
    present = {p.relative_to(cert_dir).as_posix()
               for p in cert_dir.rglob("*") if p.is_file()} - {"vac.json"}
    for extra in sorted(present - listed):
        reasons.append(f"file present but not in evidence: {extra}")

    # RECOMPUTE: the headline must still follow from assay.json.
    try:
        got = _recomputed(aj)
    except (KeyError, TypeError) as exc:
        return None, (f"{ARTIFACT} does not have the expected shape: {exc!r}",)
    checks = man.get("results", {}).get("checks", [])
    if not checks:
        reasons.append("no checks: nothing in this bundle is verifiable")
    for chk in checks:
        for k, v in chk.get("expect", {}).items():
            if k not in got:
                reasons.append(f"expect.{k} is not a recomputable field")
            elif got[k] != v:
                reasons.append(f"expect.{k}={v} but assay.json recomputes {got[k]}")

    summary = man.get("results", {}).get("summary", {})
    if set(summary) != {SCOPE}:
        reasons.append(f"summary scope {sorted(summary)}, expected [{SCOPE!r}]")

    if reasons:
        return None, tuple(reasons)

    cal = aj["calibration"]
    floor = cal["floor"]
    cov = got["covered"] / got["classes"] if got["classes"] else 0.0
    att = aj.get("attack")
    return Row(
        rubric_id=aj["rubric_id"],
        specimen_set_id=aj["specimen_set_id"],
        material_sha=aj["material_sha"],
        classes=got["classes"], covered=got["covered"],
        residual=tuple(aj["residual"]),
        floor=floor, difficulty=cal["difficulty"],
        earned=None if floor >= 1 else max(0.0, (cov - floor) / (1 - floor)),
        evasion_rate=None if att is None else att["evasion_rate"],
        decoration=got["decoration"],
        uncalibrated=floor > 0,
        underpowered=tuple(aj.get("power", {}).get("underpowered", ())),
        path=cert_dir.name,
    ), ()


def build(cert_dirs: list[pathlib.Path]) -> Registry:
    """Verify every directory, keep what survives, publish why the rest did not."""
    if not cert_dirs:
        raise AssayError(
            "an empty registry would publish a 100% acceptance rate over zero "
            "submissions. Pass certificate directories.")
    rows, rejected = [], []
    for d in sorted(cert_dirs, key=lambda p: p.name):
        row, reasons = verify(d)
        if row is None:
            rejected.append(Rejection(d.name, reasons))
        else:
            rows.append(row)
    return Registry(tuple(rows), tuple(rejected))


def index_json(reg: Registry) -> dict:
    """The machine-readable board. Counts are recomputed on read, never stored
    as a number somebody has to trust."""
    return {
        "schema": SCHEMA,
        "rows": [
            {"rubric_id": r.rubric_id, "specimen_set_id": r.specimen_set_id,
             "material_sha": r.material_sha, "classes": r.classes,
             "covered": r.covered, "coverage": round(r.coverage, 4),
             "floor": round(r.floor, 4), "difficulty": round(r.difficulty, 4),
             "earned": None if r.earned is None else round(r.earned, 4),
             "evasion_rate": r.evasion_rate, "decoration": r.decoration,
             "residual": list(r.residual), "uncalibrated": r.uncalibrated,
             "underpowered": list(r.underpowered), "path": r.path}
            for r in reg.rows],
        "rejected": [{"path": x.path, "reasons": list(x.reasons)}
                     for x in reg.rejected],
    }


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_markdown(reg: Registry) -> str:
    out = [
        "# Certified rubrics", "",
        f"**{reg.accepted} listed, {len(reg.rejected)} rejected.** Every row "
        "below was re-verified from its own bundle: the headline recomputed "
        "from the evidence, every evidence file re-hashed, and the floor "
        "checked. Rejections are published with their reasons, because an "
        "acceptance rate without them is not a number.",
        "",
        "You do not have to trust this board. Each row links to a bundle any "
        "third party can verify offline.",
        "",
        "| rubric | material | caught | floor | earned | evades | residual | "
        "supported |",
        "|---|---|--:|--:|--:|--:|---|---|",
    ]
    for r in reg.rows:
        ev = "n/a" if r.evasion_rate is None else _pct(r.evasion_rate)
        earned = "n/a" if r.earned is None else _pct(r.earned)
        resid = ", ".join(r.residual) if r.residual else "none on this material"
        mark = " ⚠ UNCALIBRATED" if r.uncalibrated else ""
        # A verdict the sample cannot hold up is printed AS SUCH. The number
        # stays, because it is what was measured; the column beside it says
        # whether the interval behind it clears the bar.
        supported = ("yes" if not r.underpowered else
                     "**no**: " + ", ".join(r.underpowered))
        out.append(f"| `{r.rubric_id}`{mark} | `{r.specimen_set_id}` "
                   f"({r.material_sha[:8]}) | {r.covered}/{r.classes} | "
                   f"{_pct(r.floor)} | {earned} | {ev} | {resid} | "
                   f"{supported} |")

    out += ["", "## Rejected", ""]
    if reg.rejected:
        for x in reg.rejected:
            out.append(f"- **`{x.path}`** — " + "; ".join(x.reasons))
    else:
        out.append("Nothing was rejected in this build. With "
                   f"{reg.accepted} submission(s) that says little; the "
                   "reasons above are the ones a bundle can fail on.")

    out += ["", "## How a row is earned", "",
            "**Coverage** is measured against the defect classes present in "
            "the material, never against what a rubric claims to target. "
            "**Floor** is the best coverage a battery of naive probes reaches "
            "on the same material, including a deterministic coin flip; a "
            "class chance can cover tests nothing. **Earned** is coverage with "
            "the floor subtracted out. **Residual** is what the rubric misses, "
            "and it is a column rather than a footnote on purpose. "
            "**Supported** says whether each verdict's 95% interval clears "
            "the bar at this sample size; a row can read 100% and still be "
            "unsupported, and the board says so rather than hiding it."]
    return "\n".join(out) + "\n"


__all__ = ["Registry", "Rejection", "Row", "SCHEMA", "build", "index_json",
           "render_markdown", "verify"]
