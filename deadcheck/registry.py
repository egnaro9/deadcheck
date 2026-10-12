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

from .certificate import ARTIFACT, PROJECTIONS, SCOPES, _project, _recomputed
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
    kind: str                       # subject or calibration
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
    def subjects(self) -> tuple[Row, ...]:
        return tuple(r for r in self.rows if r.kind == "subject")

    @property
    def calibration(self) -> tuple[Row, ...]:
        return tuple(r for r in self.rows if r.kind == "calibration")

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
    root = cert_dir.resolve()
    for e in man.get("evidence", []):
        p = cert_dir / e["path"]
        # "Closed evidence" means closed. A path that resolves outside the
        # bundle is a manifest vouching for bytes it does not contain, and
        # hashing them anyway would accept a bundle whose evidence can be
        # swapped out from under it without touching the bundle.
        if not p.resolve().is_relative_to(root):
            reasons.append(f"evidence path escapes the bundle: {e['path']}")
            continue
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
    if got["classes"] == 0:
        # 0/0 recomputes as consistent, every hash can match, and the row
        # would list with every column empty, which reads as a clean sheet.
        # Refuse here, but KEEP what the evidence pass already found: an
        # early return that drops collected reasons hid a path-escape behind
        # this message the first time it ran.
        return None, (*reasons, "bundle measured nothing: zero defect classes")
    checks = man.get("results", {}).get("checks", [])
    if not checks:
        reasons.append("no checks: nothing in this bundle is verifiable")
    for fname, path in PROJECTIONS.items():
        pp = cert_dir / fname
        if not pp.exists():
            reasons.append(f"projection missing: {fname}")
            continue
        try:
            if json.loads(pp.read_text()) != _project(aj, path):
                reasons.append(f"{fname} is not {'.'.join(path)} of "
                               f"{ARTIFACT}: the headline could disagree "
                               "with the record")
        except (json.JSONDecodeError, KeyError):
            reasons.append(f"{fname} unreadable or {ARTIFACT} lacks "
                           f"{'.'.join(path)}")
    seen_scopes: set[str] = set()
    for chk in checks:
        art = chk.get("artifact", "")
        scope = art.split(".")[0]
        if scope not in SCOPES:
            reasons.append(f"check.artifact {art!r} is not a projection this "
                           "registry recomputes; the headline would bind to "
                           "evidence nobody checked")
        if scope in seen_scopes:
            reasons.append(f"scope {scope!r} claimed by more than one check")
        seen_scopes.add(scope)
        for k, v in chk.get("expect", {}).items():
            if k == "floor":
                want = round(aj["calibration"]["floor"], 4)
                if want != v:
                    reasons.append(f"expect.floor={v} but assay.json records {want}")
            elif k not in got:
                reasons.append(f"expect.{k} is not a recomputable field")
            elif got[k] != v:
                reasons.append(f"expect.{k}={v} but assay.json recomputes {got[k]}")

    summary = man.get("results", {}).get("summary", {})
    if set(summary) != set(SCOPES):
        reasons.append(f"summary scopes {sorted(summary)}, expected "
                       f"{sorted(SCOPES)}")

    if reasons:
        return None, tuple(reasons)

    cal = aj["calibration"]
    floor = cal["floor"]
    cov = got["covered"] / got["classes"]
    att = aj.get("attack")
    return Row(
        rubric_id=aj["rubric_id"],
        specimen_set_id=aj["specimen_set_id"],
        material_sha=aj["material_sha"],
        classes=got["classes"], covered=got["covered"],
        residual=tuple(aj["residual"]),
        floor=floor, difficulty=cal["difficulty"],
        earned=None if floor >= 1 else max(0.0, (cov - floor) / (1 - floor)),
        # A rubric that caught nothing cannot be evaded, and printing its 0%
        # beside a real 0% ranks a blind rubric as unbreakable. None here
        # renders as "n/a", and the reason travels with it below.
        evasion_rate=(None if att is None or not att.get("n_caught")
                      else att["evasion_rate"]),
        decoration=got["decoration"],
        uncalibrated=floor > 0,
        underpowered=tuple(aj.get("power", {}).get("underpowered", ())),
        kind=aj.get("rubric_kind", "subject"),
        path=cert_dir.name,
    ), ()


def build(cert_dirs: list[pathlib.Path]) -> Registry:
    """Verify every directory, keep what survives, publish why the rest did not."""
    if not cert_dirs:
        raise AssayError(
            "an empty registry would publish a 100% acceptance rate over zero "
            "submissions. Pass certificate directories.")
    seen: dict[pathlib.Path, str] = {}
    for d in cert_dirs:
        key = d.resolve()
        if key in seen:
            raise AssayError(
                f"{d} was passed twice. A board listing one bundle as two rows "
                "double-counts it, and an acceptance rate over duplicates is "
                "not a rate.")
        seen[key] = d.name
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
             "underpowered": list(r.underpowered), "kind": r.kind, "path": r.path}
            for r in reg.rows],
        "rejected": [{"path": x.path, "reasons": list(x.reasons)}
                     for x in reg.rejected],
    }


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _table(rows) -> list[str]:
    out = ["| rubric | material | caught | floor | earned | evades | residual | "
           "supported |",
           "|---|---|--:|--:|--:|--:|---|---|"]
    for r in rows:
        ev = ("n/a, caught nothing" if r.evasion_rate is None and r.covered == 0
              else "n/a" if r.evasion_rate is None else _pct(r.evasion_rate))
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
    return out


def render_markdown(reg: Registry) -> str:
    subj, cal = reg.subjects, reg.calibration
    out = [
        "# Certified rubrics", "",
        f"**{len(subj)} subject rubric(s) listed, {len(cal)} calibration "
        f"fixture(s), {len(reg.rejected)} rejected.** Every row was re-verified "
        "from its own bundle: the headline recomputed from the evidence, every "
        "evidence file re-hashed, and the floor checked. Rejections are "
        "published with their reasons, because an acceptance rate without "
        "them is not a number.",
        "",
        "You do not have to trust this board. Each row links to a bundle any "
        "third party can verify offline.",
        "",
        "## Subjects", "",
        "These rows are findings. Each is a rubric someone else wrote, scored "
        "against material it was not written for.",
        "",
    ]
    out += _table(subj) if subj else ["_No subject rubrics yet. Everything "
                                      "below is calibration._"]
    out += ["", "## Calibration fixtures", "",
            "**These rows are not findings.** Each rubric was written against "
            "its material to prove the instrument can produce a given verdict: "
            "low coverage, perfect detection with zero coverage, evadable by "
            "paraphrase, conclusive. They look exactly as good or bad as they "
            "were built to, and they are never ranked against a subject. If "
            "the instrument could not tell them apart it would certify "
            "nothing.", ""]
    out += _table(cal) if cal else ["_No calibration fixtures in this build._"]

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
