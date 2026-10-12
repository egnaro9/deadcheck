"""Every command the README documents is invoked here.

A documented command nobody runs is a gate that tests a path no one takes,
which is the failure this package exists to find. These exist so the docs
cannot rot silently.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deadcheck.cli import load, main

PACK = "packs.flight_v1:FLIGHT_V1"
RUBRIC = "examples.flight_rubric:written_v2"
NAIVE = "examples.flight_rubric:naive_v1"


@pytest.fixture(autouse=True)
def _at_root(monkeypatch):
    monkeypatch.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    (ROOT / "examples" / "__init__.py").touch()


def test_calibrate_runs_and_reports_the_floor(capsys):
    assert main(["calibrate", "--pack", PACK]) == 0
    out = capsys.readouterr().out
    assert "CALIBRATION" in out and "floor" in out


def test_assay_runs_and_prints_the_residual_section(capsys):
    assert main(["assay", "--pack", PACK, "--rubric", RUBRIC]) == 0
    out = capsys.readouterr().out
    assert "Residual: what this rubric cannot see" in out
    assert "Floor" in out and "Earned" in out


def test_attack_exits_nonzero_when_the_rubric_is_evadable(capsys):
    """The exit code is the point: this belongs in CI."""
    assert main(["attack", "--pack", PACK, "--rubric", RUBRIC]) == 0
    code = main(["attack", "--pack", PACK, "--rubric", RUBRIC,
                 "--evasions", "packs.flight_v1:EVASIONS",
                 "--max-combined", "1"])
    assert code == 1
    assert "slips past" in capsys.readouterr().out


def test_certify_and_then_recompute_and_registry(tmp_path, capsys):
    """--repo points at a clean throwaway checkout, because the real tree is
    legitimately dirty while anyone is working in it."""
    import subprocess as sp
    repo = tmp_path / "repo"
    repo.mkdir()
    for c in (["init", "-q"], ["config", "user.email", "t@t"],
              ["config", "user.name", "t"]):
        sp.run(["git", *c], cwd=repo, check=True, capture_output=True)
    (repo / "x").write_text("x")
    sp.run(["git", "add", "x"], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "commit", "-qm", "i"], cwd=repo, check=True, capture_output=True)

    out = tmp_path / "certs" / "written_v2"
    assert main(["certify", "--pack", PACK, "--rubric", RUBRIC,
                 "--out", str(out), "--cert-root", str(tmp_path),
                 "--repo", str(repo)]) == 0
    assert (out / "vac.json").exists()
    capsys.readouterr()

    assert main(["recompute", str(out)]) == 0
    assert "consistent" in capsys.readouterr().out

    assert main(["registry", str(out)]) == 0
    assert "Certified rubrics" in capsys.readouterr().out


def test_registry_exits_nonzero_when_something_was_rejected(tmp_path, capsys):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "vac.json").write_text("{}")
    (bad / "assay.json").write_text("{}")
    assert main(["registry", str(bad)]) == 1
    assert "## Rejected" in capsys.readouterr().out


def test_a_bad_spec_is_a_sentence_not_a_traceback(capsys):
    assert main(["assay", "--pack", "nope", "--rubric", RUBRIC]) == 2
    err = capsys.readouterr().err
    assert "not a module:attribute spec" in err
    assert "Traceback" not in err


def test_an_unimportable_module_says_what_to_do(capsys):
    assert main(["calibrate", "--pack", "no.such.module:X"]) == 2
    assert "has to be on sys.path" in capsys.readouterr().err


def test_a_missing_attribute_is_named(capsys):
    assert main(["calibrate", "--pack", "packs.flight_v1:NOPE"]) == 2
    assert "has no attribute 'NOPE'" in capsys.readouterr().err


def test_load_accepts_a_built_specimen_set_as_well_as_a_pack():
    from packs.flight_v1 import FLIGHT_V1

    from deadcheck.cli import _material
    built = _material(PACK)
    assert len(built.specimens) == len(FLIGHT_V1.bases) + len(FLIGHT_V1.injections)
    assert len(built.clean) == len(FLIGHT_V1.bases)


def test_the_console_entry_point_is_wired():
    """pyproject declares `deadcheck = deadcheck.cli:main`; prove the target
    resolves rather than trusting the metadata string."""
    assert callable(load("deadcheck.cli:main"))
    r = subprocess.run([sys.executable, "-m", "deadcheck.cli", "calibrate",
                        "--pack", PACK], cwd=ROOT, capture_output=True,
                       text=True, env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    assert "CALIBRATION" in r.stdout
