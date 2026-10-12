"""Rendering. The residual section prints even when it is empty, and prints
LAST, because a report that buries what the rubric cannot see is the thing this
tool was built to replace.
"""

from __future__ import annotations

from .assay import Assay


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def markdown(a: Assay) -> str:
    out: list[str] = [
        f"# Rubric assay: `{a.rubric_id}`",
        "",
        f"Specimen set `{a.specimen_set_id}` · policy: separation >= "
        f"{a.policy.min_separation:.2f}, false alarms <= "
        f"{_pct(a.policy.max_false_alarm_rate)}",
        "",
        f"**Coverage {_pct(a.coverage)}** "
        f"({sum(1 for c in a.classes if c.covered)}/{len(a.classes)} defect "
        "classes present in the material are caught).",
        "",
        "## Separation, per checkpoint",
        "",
        "| checkpoint | targets | detects | false alarms | off-target | "
        "separation | verdict |",
        "|---|---|--:|--:|--:|--:|---|",
    ]
    for c in a.checkpoints:
        if c.untested:
            verdict = "UNTESTED, no specimen carries its target"
            sep = "n/a"
        elif c.is_decoration:
            verdict = "**DECORATION, cut it**"
            sep = f"{c.separation:+.2f}"
        else:
            verdict = "separates"
            sep = f"{c.separation:+.2f}"
        out.append(
            f"| `{c.checkpoint_id}` | {', '.join(c.targets)} | "
            f"{c.fired_on_target}/{c.n_target} | "
            f"{c.fired_on_clean}/{c.n_clean} | "
            f"{c.fired_on_other}/{c.n_other} | {sep} | {verdict} |")

    out += ["", "_Off-target counts fires on defective specimens carrying none "
            "of the checkpoint's declared classes. A checkpoint that fires "
            "mostly off-target is right by accident._",
            "", "## Coverage, per defect class", "",
            "| defect class | specimens | caught by | best separation |",
            "|---|--:|---|--:|"]
    for cl in a.classes:
        caught = ", ".join(f"`{x}`" for x in cl.covering_checkpoints) or "**nothing**"
        out.append(f"| {cl.defect_class} | {cl.n_specimens} | {caught} | "
                   f"{cl.best_separation:+.2f} |")

    out += ["", "## Residual: what this rubric cannot see", ""]
    if a.residual:
        out.append("Present in the material and NOT caught under this policy:")
        out.append("")
        for cl in a.classes:
            if cl.covered:
                continue
            if not cl.claimed:
                detail = (" NO CHECKPOINT DECLARES THIS CLASS. It is not being "
                          "looked for at all.")
            elif cl.missed_specimens:
                miss = ", ".join(f"`{m}`" for m in cl.missed_specimens)
                detail = (" Declared, but no claiming checkpoint fired on: "
                          f"{miss}.")
            else:
                detail = (" Every specimen was flagged by a claiming checkpoint, "
                          "but it did not clear the policy, so the gap it opens "
                          "is too small or it also fires on clean material.")
            out.append(f"- **{cl.defect_class}** ({cl.n_specimens} specimens)."
                       f"{detail}")
    else:
        out.append("No defect class present in this specimen set went uncaught. "
                   "That is a statement about THIS material only, and the "
                   "unmeasured list below is the honest limit of it.")

    if a.undeclared_classes:
        out += ["", "**Caught nothing because nothing claims them.** These "
                "classes are in the material and no checkpoint declares them: "
                + ", ".join(f"`{c}`" for c in a.undeclared_classes) + "."]
    if a.unmeasured_targets:
        out += ["", "**Claimed but never tested.** Checkpoints target these and "
                "no specimen carries them, so their separation is an assertion, "
                "not a measurement: "
                + ", ".join(f"`{c}`" for c in a.unmeasured_targets) + "."]
    if a.decoration:
        out += ["", "**Cut candidates.** These opened no gap between defective "
                "and clean material: "
                + ", ".join(f"`{c}`" for c in a.decoration) + "."]

    return "\n".join(out) + "\n"


__all__ = ["markdown"]
