"""The command every certificate's replay block names.

    python -m deadcheck.recompute <assay.json | certificate-dir>

**WHAT THIS PROVES, and the limit is the point.** It does NOT re-run the
rubric: predicates are code and are not in the bundle, so no bundle can be
replayed into a fresh score. What it does is check that every DERIVED number in
the bundle follows from the RAW COUNTS the bundle itself recorded, and that the
manifest's headline follows from the artifact.

So a bundle that passes here is internally consistent, not independently
reproduced. Saying more than that would be the overclaim this package exists to
catch, and the certificate's `replay.expected` says the same thing.

Concretely, these are recomputed rather than read:

  separation      detection rate minus false-alarm rate, from the raw counts
  decoration      separation at or below zero
  untested        no specimen carried a declared target
  residual        exactly the classes whose `covered` is false
  difficulty      1 - floor
  floor           the best coverage any probe reached
  the headline    `results.checks[].expect` against the artifact

Anything that disagrees is printed with both numbers. Exit 0 only when nothing
does.
"""

from __future__ import annotations

import json
import pathlib
import sys

TOL = 1e-4   # the artifact rounds to 4 places; anything larger is a real gap


def _rate(pair: list[int]) -> float:
    hit, n = pair
    return hit / n if n else 0.0


def recompute(aj: dict) -> list[str]:
    """Return every discrepancy between the bundle's derived and raw numbers."""
    bad: list[str] = []

    for c in aj.get("checkpoints", []):
        cid = c["checkpoint_id"]
        want = _rate(c["detection"]) - _rate(c["false_alarms"])
        if abs(want - c["separation"]) > TOL:
            bad.append(f"checkpoint {cid}: separation recorded "
                       f"{c['separation']:+.4f}, counts give {want:+.4f}")
        if c["decoration"] != (want <= 0):
            bad.append(f"checkpoint {cid}: decoration recorded "
                       f"{c['decoration']}, separation {want:+.4f} implies "
                       f"{want <= 0}")
        if c["untested"] != (c["detection"][1] == 0):
            bad.append(f"checkpoint {cid}: untested recorded {c['untested']}, "
                       f"but it has {c['detection'][1]} target specimen(s)")

    classes = aj.get("classes", [])
    want_residual = sorted(c["defect_class"] for c in classes if not c["covered"])
    if sorted(aj.get("residual", [])) != want_residual:
        bad.append(f"residual recorded {sorted(aj.get('residual', []))}, "
                   f"covered flags give {want_residual}")

    for c in classes:
        if c["covered"] and not c["covering_checkpoints"]:
            bad.append(f"class {c['defect_class']}: covered with no covering "
                       "checkpoint named")
        if c["covered"] and not c["claimed"]:
            bad.append(f"class {c['defect_class']}: covered but claimed by no "
                       "checkpoint")

    cal = aj.get("calibration")
    if cal:
        probes = cal.get("probes", [])
        if probes:
            want_floor = max(p["coverage"] for p in probes)
            if abs(want_floor - cal["floor"]) > TOL:
                bad.append(f"floor recorded {cal['floor']:.4f}, best probe "
                           f"gives {want_floor:.4f}")
        if abs((1 - cal["floor"]) - cal["difficulty"]) > TOL:
            bad.append(f"difficulty recorded {cal['difficulty']:.4f}, "
                       f"1 - floor gives {1 - cal['floor']:.4f}")
        want_cheap = sorted({c for p in probes for c in p["covered_classes"]})
        if sorted(cal.get("cheap_classes", [])) != want_cheap:
            bad.append(f"cheap_classes recorded "
                       f"{sorted(cal.get('cheap_classes', []))}, probes give "
                       f"{want_cheap}")

    att = aj.get("attack")
    if att and att["n_caught"]:
        want = len(att["evaded"]) / att["n_caught"]
        if abs(want - att["evasion_rate"]) > TOL:
            bad.append(f"evasion_rate recorded {att['evasion_rate']:.4f}, "
                       f"{len(att['evaded'])}/{att['n_caught']} gives "
                       f"{want:.4f}")
    return bad


def check(target: pathlib.Path) -> tuple[int, str]:
    """Recompute one artifact or certificate directory. Returns (exit, report)."""
    from .certificate import ARTIFACT, _recomputed

    art = target / ARTIFACT if target.is_dir() else target
    if not art.exists():
        return 2, f"no {art}"
    try:
        aj = json.loads(art.read_text())
    except json.JSONDecodeError as exc:
        return 2, f"{art}: unreadable json: {exc}"

    bad = recompute(aj)

    # If the manifest sits beside it, the headline must follow from the artifact.
    man_path = (target if target.is_dir() else target.parent) / "vac.json"
    if man_path.exists():
        try:
            man = json.loads(man_path.read_text())
            got = _recomputed(aj)
            for chk in man.get("results", {}).get("checks", []):
                for k, v in chk.get("expect", {}).items():
                    if k not in got:
                        bad.append(f"vac.json expect.{k} is not a recomputable "
                                   "field")
                    elif got[k] != v:
                        bad.append(f"vac.json expect.{k}={v}, artifact "
                                   f"recomputes {got[k]}")
        except json.JSONDecodeError as exc:
            bad.append(f"vac.json unreadable: {exc}")

    n = len(aj.get("classes", []))
    if bad:
        lines = [f"INCONSISTENT — {len(bad)} discrepanc"
                 f"{'y' if len(bad) == 1 else 'ies'} in {art.name}"]
        lines += [f"  {b}" for b in bad]
        lines.append("  this bundle's derived numbers do not follow from its "
                     "own recorded counts")
        return 1, "\n".join(lines)
    return 0, (f"consistent — {n}/{n} classes recomputed identical\n"
               "  derived values follow from the recorded counts. This is "
               "internal consistency,\n  not an independent re-run: predicates "
               "are not in the bundle.")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    worst = 0
    for a in args:
        code, report = check(pathlib.Path(a))
        print(report)
        worst = max(worst, code)
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
