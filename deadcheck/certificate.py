"""Layer 5: a certificate a stranger can check without trusting you.

Emits a Capability Evidence Bundle in the vac-protocol v0.2 shape, so the
existing offline verifier reads it. deadcheck still has no dependencies: this
writes the format, it does not import the protocol.

Three properties are inherited from that format deliberately.

  NO WALL CLOCK. Every field derives from the inputs or from git, so
  re-emission is byte-identical and a diff means something changed.

  CLOSED EVIDENCE. Every sibling of vac.json is listed and hashed, so a file
  added after issue breaks verification instead of riding along unnoticed.

  THE SUMMARY IS RECOMPUTABLE. `expect` holds only numbers a verifier can
  derive from assay.json itself. Nothing in the headline is the issuer's word.

And one guard this layer adds, which is the reason the certificate means
anything: **it refuses to issue against uncalibrated material.** A coverage
number from a specimen set a naive probe can already reach is not interpretable,
so rating it would be publishing a figure nobody can read. The floor travels in
the claim either way.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from dataclasses import dataclass

from .adversary import AttackReport
from .agreement import AgreementResult
from .assay import Assay
from .calibration import Calibration, earned
from .model import AssayError, Rubric, SpecimenSet

VAC_VERSION = "0.2"
PROFILE = "deadcheck-assay-v1"
ARTIFACT = "assay.json"          # scope is derived from this filename
SCOPE = ARTIFACT.split(".")[0]   # keep the two from drifting

_CONTROL_POLICY = (
    "the specimen set is calibrated before any rubric is scored against it: a "
    "battery of deliberately naive probes, including a DETERMINISTIC COIN "
    "FLIP, is run over the same material, and the best coverage any of them "
    "reaches is published as the floor. A defect class a coin flip can cover "
    "tests nothing, so this certificate is refused when the floor is nonzero. "
    "Every score below is reported with the floor beside it and with the "
    "earned figure, which is coverage with the floor subtracted out")

_LIMITATIONS = (
    "covers exactly the specimen set pinned by material_sha and says nothing "
    "beyond it: coverage is measured against the defect classes PRESENT in "
    "that material, never against what the rubric claims to target",
    "the residual names what this rubric misses ON THIS MATERIAL. Defect "
    "classes absent from the specimen set are neither caught nor counted, and "
    "a class no checkpoint declares is reported as undeclared rather than "
    "treated as covered",
    "grading reads artifacts only: predicates are run over transcripts and "
    "nothing consults the rubric author's description of what they do",
    "an evasion rate is measured against the declared battery only. Holding "
    "against those transformations is not a claim about transformations "
    "nobody wrote",
)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256(path: pathlib.Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _git(repo: pathlib.Path, *args: str) -> str:
    """Trimmed output, for single-value queries like rev-parse."""
    return _git_raw(repo, *args).strip()


def _git_raw(repo: pathlib.Path, *args: str) -> str:
    """UNTRIMMED. Porcelain lines are `XY<space>path` and an unstaged change
    begins with a SPACE, so stripping the whole output eats the first line's
    leading space and every subsequent slice cuts one character into the path.
    That produced `eadcheck/__init__.py` the first time this ran."""
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, check=True).stdout


def _is_checkout(repo: pathlib.Path) -> bool:
    return subprocess.run(["git", "rev-parse", "--git-dir"], cwd=repo,
                          capture_output=True).returncode == 0


def _issuer_commit(repo: pathlib.Path) -> tuple[str, bool]:
    """(stamp, is_a_commit).

    An INSTALLED package has no commit to pin. Pretending otherwise would put
    a fake pin in the one field a verifier uses to fetch the issuer, so the
    version is used instead and the claim says so. Discovered the ordinary
    way: `parents[1]` is site-packages after a pip install, and the dirty
    check died there with a raw CalledProcessError.
    """
    if _is_checkout(repo):
        return _git(repo, "rev-parse", "--short", "HEAD"), True
    from . import __version__
    return f"v{__version__}", False


def _refuse_dirty(repo: pathlib.Path, out_dir: pathlib.Path) -> None:
    """A certificate stamped from a dirty tree is unattributable to any commit,
    which makes `issuer_commit` a decoration rather than a pin.

    `out_dir` is exempt, and so is everything under it, because a registry
    issues many certificates into one parent and the second would otherwise
    trip on the first. Everything OUTSIDE it still blocks: the point is that
    the harness producing the verdict is pinned, not that the output is tidy.
    """
    if not _is_checkout(repo):
        return   # nothing to be dirty; _issuer_commit records the version
    rel = out_dir.resolve().relative_to(repo.resolve()).as_posix() \
        if out_dir.resolve().is_relative_to(repo.resolve()) else None
    dirty = [ln[3:] for ln in
             _git_raw(repo, "status", "--porcelain").splitlines() if ln]
    outside = [p for p in dirty if not (rel and p.startswith(rel))]
    if outside:
        raise AssayError(
            "refusing to stamp a dirty tree: uncommitted changes outside the "
            "output directory: " + ", ".join(sorted(outside)[:8]))


def assay_json(rubric: Rubric, specimens: SpecimenSet, assay: Assay,
               cal: Calibration,
               attack: AttackReport | None = None,
               agreements: tuple[AgreementResult, ...] = ()) -> dict:
    """The primary evidence artifact. Everything in the manifest's `expect`
    block is recomputable from this."""
    from .ratchet import material_fingerprint
    return {
        "schema": 1,
        "rubric_id": assay.rubric_id,
        "specimen_set_id": assay.specimen_set_id,
        "material_sha": material_fingerprint(specimens),
        "policy": {"min_separation": assay.policy.min_separation,
                   "max_false_alarm_rate": assay.policy.max_false_alarm_rate},
        "classes": [
            {"defect_class": c.defect_class, "n_specimens": c.n_specimens,
             "covered": c.covered, "claimed": c.claimed,
             "best_separation": round(c.best_separation, 4),
             "covering_checkpoints": list(c.covering_checkpoints)}
            for c in assay.classes],
        "checkpoints": [
            {"checkpoint_id": c.checkpoint_id, "targets": list(c.targets),
             "detection": [c.fired_on_target, c.n_target],
             "false_alarms": [c.fired_on_clean, c.n_clean],
             "off_target": [c.fired_on_other, c.n_other],
             "separation": round(c.separation, 4),
             "decoration": c.is_decoration, "untested": c.untested}
            for c in assay.checkpoints],
        "residual": list(assay.residual),
        "undeclared_classes": list(assay.undeclared_classes),
        "unmeasured_targets": list(assay.unmeasured_targets),
        "calibration": {
            "floor": round(cal.floor, 4),
            "difficulty": round(cal.difficulty, 4),
            "best_probe": cal.best_probe,
            "cheap_classes": list(cal.cheap_classes),
            "probes": [{"probe_id": p.probe_id,
                        "coverage": round(p.coverage, 4),
                        "covered_classes": list(p.covered_classes)}
                       for p in cal.probes],
        },
        "attack": None if attack is None else {
            "n_caught": attack.n_caught, "n_uncaught": attack.n_uncaught,
            "evasion_rate": round(attack.evasion_rate, 4),
            "searched_up_to": attack.searched_up_to,
            "exhaustive": attack.exhaustive,
            "evaded": [{"specimen_id": e.specimen_id,
                        "evasion_ids": list(e.evasion_ids)}
                       for e in attack.evaded],
        },
        "agreement": [
            {"checkpoint_id": a.checkpoint_id, "verdict": a.verdict,
             "raters": list(a.raters), "n_specimens": a.n_specimens,
             "kappa_human": None if a.kappa_human is None
             else round(a.kappa_human, 4)}
            for a in agreements],
    }


def _recomputed(aj: dict) -> dict:
    """Only fields a verifier can derive from assay.json. The issuer's word
    appears nowhere in this block."""
    return {
        "classes": len(aj["classes"]),
        "covered": sum(1 for c in aj["classes"] if c["covered"]),
        "residual": len(aj["residual"]),
        "checkpoints": len(aj["checkpoints"]),
        "decoration": sum(1 for c in aj["checkpoints"] if c["decoration"]),
    }


def vac_manifest(out_dir: pathlib.Path, repo: pathlib.Path,
                 issuer: str) -> dict:
    """Pure function of the written bundle plus git. Never writes."""
    aj = json.loads((out_dir / ARTIFACT).read_text())
    cal, recomputed = aj["calibration"], _recomputed(aj)

    clash = sorted(set(cal["cheap_classes"]) & set(recomputed))
    if clash:
        raise AssayError(
            f"defect class {clash} collides with a recomputed field name, so "
            "the summary key would bind to the recomputed value instead of "
            "the class. Rename the class.")

    coverage = recomputed["covered"] / recomputed["classes"] if recomputed["classes"] else 0.0
    commit, pinned = _issuer_commit(repo)
    headline = (f"{recomputed['covered']}/{recomputed['classes']} defect "
                f"classes caught, floor {cal['floor']:.0%}, earned "
                f"{(coverage - cal['floor']) / (1 - cal['floor']):.0%}"
                if cal["floor"] < 1 else "uninterpretable: floor is 100%")

    return {
        "vac_version": VAC_VERSION,
        "claim": {
            "capability": f"rubric-coverage:{aj['rubric_id']} — {headline}",
            "scope": (f"exactly the specimen set {aj['specimen_set_id']!r} "
                      f"pinned by material_sha {aj['material_sha']}, under the "
                      "policy recorded in assay.json, and nothing beyond it"),
            "limitations": [
                *(_LIMITATIONS),
                *([f"RESIDUAL: {', '.join(aj['residual'])} present in the "
                   "material and NOT caught"] if aj["residual"] else []),
                *([f"UNDECLARED: {', '.join(aj['undeclared_classes'])} present "
                   "and claimed by no checkpoint"] if aj["undeclared_classes"] else []),
                *([f"UNMEASURED: {', '.join(aj['unmeasured_targets'])} claimed "
                   "by a checkpoint and carried by no specimen, so their "
                   "separation is asserted and not measured"]
                  if aj["unmeasured_targets"] else []),
                *([] if pinned else [
                    "ISSUER NOT PINNED: this bundle was produced by an "
                    f"INSTALLED deadcheck ({commit}), not a git checkout, so "
                    "issuer_commit names a release rather than a commit and "
                    "the replay below checks out a tag"]),
            ],
        },
        "subject": {"kind": "rubric", "id": aj["rubric_id"],
                    "version": {"material_sha": aj["material_sha"],
                                "specimen_set": aj["specimen_set_id"]}},
        "protocol": {
            "issuer": issuer,
            "issuer_commit": commit,
            "task": f"rubric-assay:{aj['specimen_set_id']}",
            "hashes": {"material_sha": aj["material_sha"],
                       "assay_sha256": _sha256(out_dir / ARTIFACT)},
            "grading": ("deterministic predicates over transcripts, no model "
                        "in the loop; separation = detection rate minus false "
                        "alarm rate; coverage measured against classes present "
                        "in the material"),
            "control_policy": _CONTROL_POLICY,
        },
        "evidence": [
            {"path": p.relative_to(out_dir).as_posix(), "sha256": _sha256(p)}
            for p in sorted(out_dir.rglob("*"))
            if p.is_file() and p.relative_to(out_dir).as_posix() != "vac.json"],
        "results": {
            "summary": {SCOPE: {**recomputed,
                                "floor_pct": round(cal["floor"] * 100),
                                "difficulty_pct": round(cal["difficulty"] * 100)}},
            "checks": [{"profile": PROFILE, "artifact": ARTIFACT,
                        "render": "CERTIFICATE.md",
                        "expect": dict(recomputed)}],
        },
        "replay": {
            "issuer_commit": commit,
            "commands": [
                f"git clone https://github.com/{issuer} issuer",
                f"git -C issuer checkout {commit}",
                "python -m pytest issuer/tests -q",
                f"python -m deadcheck.recompute {ARTIFACT}",
            ],
            "expected": (
                f"exit 0; recompute reports 'consistent — "
                f"{recomputed['classes']}/{recomputed['classes']} classes "
                "recomputed identical'. NOTE THE LIMIT: this re-derives every "
                "value in the bundle from the raw counts the bundle recorded, "
                "and checks the headline against the artifact. It does NOT "
                "re-run the rubric, because predicates are code and are not in "
                "the bundle. A passing bundle is internally consistent, not "
                "independently reproduced"),
        },
    }


def certify(out_dir: pathlib.Path, rubric: Rubric, specimens: SpecimenSet,
            assay: Assay, cal: Calibration,
            attack: AttackReport | None = None,
            agreements: tuple[AgreementResult, ...] = (),
            issuer: str = "egnaro9/deadcheck",
            repo: pathlib.Path | None = None,
            allow_uncalibrated: bool = False,
            cert_root: pathlib.Path | None = None) -> pathlib.Path:
    """Write assay.json, CERTIFICATE.md and vac.json into `out_dir`."""
    repo = repo or pathlib.Path(__file__).resolve().parents[1]

    if cal.floor > 0 and not allow_uncalibrated:
        raise AssayError(
            f"refusing to certify against {cal.specimen_set_id!r}: a naive "
            f"probe ({cal.best_probe}) already reaches "
            f"{', '.join(cal.cheap_classes)} on this material, floor "
            f"{cal.floor:.0%}. A coverage number against material chance can "
            "cover is not interpretable, so a rating on it would be a figure "
            "nobody can read. Harden the material, or pass "
            "allow_uncalibrated=True and the floor will travel in the claim.")
    if cal.specimen_set_id != assay.specimen_set_id:
        raise AssayError(
            f"calibration is for {cal.specimen_set_id!r} and the assay is for "
            f"{assay.specimen_set_id!r}. A floor from other material says "
            "nothing about this score.")

    _refuse_dirty(repo, cert_root or out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    aj = assay_json(rubric, specimens, assay, cal, attack, agreements)
    (out_dir / ARTIFACT).write_text(json.dumps(aj, indent=1, sort_keys=True) + "\n")
    (out_dir / "CERTIFICATE.md").write_text(render(aj))
    man = vac_manifest(out_dir, repo, issuer)
    (out_dir / "vac.json").write_text(json.dumps(man, indent=1) + "\n")
    return out_dir / "vac.json"


def render(aj: dict) -> str:
    """The human-readable face, bound to the same numbers the manifest checks."""
    cal, r = aj["calibration"], _recomputed(aj)
    cov = r["covered"] / r["classes"] if r["classes"] else 0.0
    out = [
        f"# Rubric certificate — `{aj['rubric_id']}`", "",
        f"Specimen set `{aj['specimen_set_id']}` · material "
        f"`{aj['material_sha']}`", "",
        f"**{r['covered']}/{r['classes']} defect classes caught.** "
        f"Floor {cal['floor']:.0%} (best naive probe: {cal['best_probe']}), "
        f"so the earned figure is "
        + (f"{(cov - cal['floor']) / (1 - cal['floor']):.0%}."
           if cal["floor"] < 1 else "undefined: the floor is 100%."),
        "", "## What this rubric cannot see", "",
    ]
    if aj["residual"]:
        out += [f"- **{c}** present in the material and not caught"
                for c in aj["residual"]]
    else:
        out.append("No defect class present in this material went uncaught. "
                   "That is a statement about this material only.")
    if aj["undeclared_classes"]:
        out.append("- **undeclared**: " + ", ".join(aj["undeclared_classes"]))
    if aj["unmeasured_targets"]:
        out.append("- **unmeasured**: " + ", ".join(aj["unmeasured_targets"]))
    if aj["attack"]:
        out += ["", "## Evasion", "",
                f"Of {aj['attack']['n_caught']} defects this rubric catches, "
                f"**{aj['attack']['evasion_rate']:.0%}** can be hidden by a "
                "declared defect-preserving transformation."]
    return "\n".join(out) + "\n"


__all__ = ["ARTIFACT", "PROFILE", "VAC_VERSION", "assay_json", "certify",
           "render", "vac_manifest"]
