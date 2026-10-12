"""deadcheck: measure what a rubric can and cannot see.

Everything here is stdlib-only and deterministic. There is no model in the loop,
so the same rubric and the same specimens always produce the same three numbers:
separation per checkpoint, coverage per defect class, and the residual.
"""

from .assay import Assay, CheckpointResult, ClassResult, run
from .fragility import (DecisionRule, FlipReport, at_most, blocking,
                        no_checkpoint_fired, what_flips)
from .power import ClassPower, PowerReport, power, required_n, wilson
from .registry import (Registry, Rejection, Row, build, index_json,
                       render_markdown, verify)
from .certificate import (ARTIFACT, PROFILE, VAC_VERSION, assay_json,
                          certify, render, vac_manifest)
from .agreement import (SUBSTANTIAL, AgreementResult, RaterCheck, Rating,
                        agree, cohens_kappa)
from .adversary import (GENERIC_EVASIONS, AttackReport, Evaded, Evasion,
                        attack, paraphrase)
from .calibration import (NAIVE_PROBES, Calibration, Probe, ProbeResult,
                          calibrate, earned)
from .specimens import (Base, Injection, Pack, append_to_reply,
                        prepend_to_reply, replace_in_reply)
from .ratchet import (RatchetReport, capability, compare, load,
                      material_fingerprint, save)
from .model import (AssayError, Checkpoint, CoveragePolicy, Rubric, Specimen,
                    SpecimenSet, defect_classes)
from .report import markdown

__version__ = "0.1.0"

__all__ = [
    "Assay", "AssayError", "Checkpoint", "CheckpointResult", "ClassResult",
    "ARTIFACT", "ClassPower", "PROFILE", "PowerReport", "Registry", "Rejection", "Row", "SUBSTANTIAL",
    "VAC_VERSION", "AgreementResult", "AttackReport", "Base", "Calibration",
    "RaterCheck", "Rating", "CoveragePolicy", "Evaded", "Evasion",
    "GENERIC_EVASIONS", "DecisionRule", "FlipReport", "Injection", "Pack",
    "NAIVE_PROBES", "Probe", "ProbeResult", "RatchetReport", "Rubric",
    "Specimen", "SpecimenSet", "at_most", "blocking", "capability", "compare",
    "defect_classes", "load", "markdown", "material_fingerprint",
    "agree", "append_to_reply", "assay_json", "attack", "calibrate", "certify",
    "build", "cohens_kappa", "earned", "index_json", "render", "render_markdown",
    "power", "required_n", "vac_manifest", "verify", "wilson",
    "no_checkpoint_fired",
    "paraphrase",
    "prepend_to_reply",
    "replace_in_reply", "run", "save", "what_flips",
]
