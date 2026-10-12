"""deadcheck: measure what a rubric can and cannot see.

Everything here is stdlib-only and deterministic. There is no model in the loop,
so the same rubric and the same specimens always produce the same three numbers:
separation per checkpoint, coverage per defect class, and the residual.
"""

from .assay import Assay, CheckpointResult, ClassResult, run
from .fragility import (DecisionRule, FlipReport, at_most, blocking,
                        no_checkpoint_fired, what_flips)
from .ratchet import (RatchetReport, capability, compare, load,
                      material_fingerprint, save)
from .model import (AssayError, Checkpoint, CoveragePolicy, Rubric, Specimen,
                    SpecimenSet, defect_classes)
from .report import markdown

__version__ = "0.1.0"

__all__ = [
    "Assay", "AssayError", "Checkpoint", "CheckpointResult", "ClassResult",
    "CoveragePolicy", "DecisionRule", "FlipReport", "RatchetReport", "Rubric",
    "Specimen", "SpecimenSet", "at_most", "blocking", "capability", "compare",
    "defect_classes", "load", "markdown", "material_fingerprint",
    "no_checkpoint_fired", "run", "save", "what_flips",
]
