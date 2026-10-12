"""The command line.

    deadcheck calibrate  --pack   packs.flight_v1:FLIGHT_V1
    deadcheck assay      --pack P --rubric examples.flight_rubric:written_v2
    deadcheck attack     --pack P --rubric R [--evasions packs.flight_v1:EVASIONS]
    deadcheck certify    --pack P --rubric R --out DIR
    deadcheck power      --pack P --rubric R
    deadcheck ratchet    --pack P --rubric R --baseline capability.json
    deadcheck recompute  DIR
    deadcheck registry   DIR [DIR ...]

**Rubrics are CODE, not configuration.** A checkpoint is a predicate, so there
is no file format that could carry one, and `--rubric` therefore takes a
`module:attribute` spec and IMPORTS it. That means running this command
executes the named module. Point it at your own rubrics; do not point it at
something a stranger handed you, for the same reason you would not run their
script.

Every command documented here has a test that invokes it. A README command
nobody runs is a gate that tests a path no one takes.
"""

from __future__ import annotations

import argparse
import importlib
import pathlib
import sys
from typing import Any

from .model import AssayError

_EXAMPLES = "https://github.com/egnaro9/deadcheck#readme"


def load(spec: str) -> Any:
    """Import `module:attribute`. The convention gunicorn and celery use."""
    if ":" not in spec:
        raise AssayError(
            f"{spec!r} is not a module:attribute spec. Rubrics and packs are "
            "Python objects, so they are named the way gunicorn names an app, "
            "for example packs.flight_v1:FLIGHT_V1")
    mod_name, _, attr = spec.partition(":")
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as exc:
        raise AssayError(
            f"cannot import {mod_name!r}: {exc}. The module has to be on "
            "sys.path; run from the project root or set PYTHONPATH.") from exc
    try:
        return getattr(mod, attr)
    except AttributeError as exc:
        raise AssayError(
            f"{mod_name!r} has no attribute {attr!r}") from exc


def _material(spec: str):
    """A --pack may name a Pack or an already-built SpecimenSet."""
    obj = load(spec)
    if isinstance(obj, type):
        raise AssayError(
            f"{spec!r} names the class {obj.__name__}, not an instance of it. "
            "A pack spec points at a built object, e.g. packs.flight_v1:FLIGHT_V1")
    return obj.build() if hasattr(obj, "build") else obj


def _cmd_calibrate(args) -> int:
    from .calibration import calibrate
    print(calibrate(_material(args.pack)).summary())
    return 0


def _cmd_assay(args) -> int:
    from .assay import run
    from .calibration import calibrate, earned
    from .report import markdown
    mat = _material(args.pack)
    rubric = load(args.rubric)
    a = run(rubric, mat)
    print(markdown(a))
    cal = calibrate(mat)
    print(f"\nFloor {cal.floor:.0%} (best naive probe: {cal.best_probe}). "
          + (f"Earned {earned(a, cal):.0%}." if cal.floor < 1 else
             "Earned is undefined: the floor is 100%."))
    return 0


def _cmd_attack(args) -> int:
    from .adversary import GENERIC_EVASIONS, attack
    from .adversary import Evasion
    evasions = GENERIC_EVASIONS
    if args.evasions:
        extra = load(args.evasions)
        try:
            extra = tuple(extra)
        except TypeError:
            extra = ()
        if not extra or not all(isinstance(e, Evasion) for e in extra):
            raise AssayError(
                f"{args.evasions!r} does not name a sequence of Evasion "
                "objects, e.g. packs.flight_v1:EVASIONS")
        evasions = evasions + extra
    rep = attack(load(args.rubric), _material(args.pack), evasions,
                 max_combined=args.max_combined)
    print(rep.summary())
    return 0 if rep.held else 1


def _cmd_certify(args) -> int:
    from .adversary import GENERIC_EVASIONS, attack
    from .assay import run
    from .calibration import calibrate
    from .certificate import certify
    mat = _material(args.pack)
    rubric = load(args.rubric)
    out = pathlib.Path(args.out)
    p = certify(out, rubric, mat, run(rubric, mat), calibrate(mat),
                attack(rubric, mat, GENERIC_EVASIONS, max_combined=2),
                issuer=args.issuer,
                repo=pathlib.Path(args.repo) if args.repo else None,
                allow_uncalibrated=args.allow_uncalibrated,
                cert_root=pathlib.Path(args.cert_root) if args.cert_root
                else None)
    print(f"wrote {p}")
    return 0


def _cmd_power(args) -> int:
    from .assay import run
    from .power import power
    mat = _material(args.pack)
    rep = power(run(load(args.rubric), mat))
    print(rep.summary())
    return 0 if rep.ok else 1


def _cmd_ratchet(args) -> int:
    from .assay import run
    from .ratchet import capability, compare, load as load_baseline, save
    mat = _material(args.pack)
    rubric = load(args.rubric)
    a = run(rubric, mat)
    if args.write:
        save(capability(a, mat), args.baseline)
        print(f"wrote baseline {args.baseline}")
        return 0
    rep = compare(load_baseline(args.baseline), a, mat)
    print(rep.summary())
    return 0 if rep.ok else 1


def _cmd_recompute(args) -> int:
    from .recompute import main as rmain
    return rmain(args.paths)


def _cmd_registry(args) -> int:
    from .registry import build, render_markdown
    reg = build([pathlib.Path(p) for p in args.paths])
    print(render_markdown(reg))
    return 1 if reg.rejected else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="deadcheck",
        description="Measure what a rubric can and cannot see.",
        epilog=f"Rubrics are imported as module:attribute. See {_EXAMPLES}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def pack(sp):
        sp.add_argument("--pack", required=True,
                        help="module:attribute naming a Pack or SpecimenSet")

    def rubric(sp):
        sp.add_argument("--rubric", required=True,
                        help="module:attribute naming a Rubric")

    c = sub.add_parser("calibrate", help="how hard is the material")
    pack(c)
    c.set_defaults(fn=_cmd_calibrate)

    a = sub.add_parser("assay", help="separation, coverage, residual")
    pack(a), rubric(a)
    a.set_defaults(fn=_cmd_assay)

    t = sub.add_parser("attack", help="what can be made to slip")
    pack(t), rubric(t)
    t.add_argument("--evasions", help="module:attribute naming extra evasions")
    t.add_argument("--max-combined", type=int, default=2, dest="max_combined")
    t.set_defaults(fn=_cmd_attack)

    y = sub.add_parser("certify", help="emit a verifiable bundle")
    pack(y), rubric(y)
    y.add_argument("--out", required=True)
    y.add_argument("--issuer", default="egnaro9/deadcheck")
    y.add_argument("--repo", help="issuer checkout to pin (default: the "
                   "installed package's own location)")
    y.add_argument("--cert-root", dest="cert_root",
                   help="parent exempt from the dirty-tree check")
    y.add_argument("--allow-uncalibrated", action="store_true",
                   dest="allow_uncalibrated")
    y.set_defaults(fn=_cmd_certify)

    w = sub.add_parser("power", help="can the sample support its verdicts")
    pack(w), rubric(w)
    w.set_defaults(fn=_cmd_power)

    h = sub.add_parser("ratchet", help="capability must not silently regress")
    pack(h), rubric(h)
    h.add_argument("--baseline", required=True)
    h.add_argument("--write", action="store_true",
                   help="write the baseline instead of comparing against it")
    h.set_defaults(fn=_cmd_ratchet)

    r = sub.add_parser("recompute", help="re-derive a bundle from its own counts")
    r.add_argument("paths", nargs="+")
    r.set_defaults(fn=_cmd_recompute)

    g = sub.add_parser("registry", help="build the board from certificate dirs")
    g.add_argument("paths", nargs="+")
    g.set_defaults(fn=_cmd_registry)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    # The project root is on sys.path so `--pack packs.x:Y` resolves when the
    # tool is invoked from a checkout rather than an install.
    root = str(pathlib.Path.cwd())
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        return args.fn(args)
    except AssayError as exc:
        # A refusal is the product. Print it plainly and exit nonzero rather
        # than dumping a traceback that buries the sentence that matters.
        print(f"deadcheck: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
