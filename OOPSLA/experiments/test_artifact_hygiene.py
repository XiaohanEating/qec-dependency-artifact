"""Artifact-hygiene regression tests (`SUBMISSION_READINESS.md` §3.4 A–D).

Four engineering defects were found by re-running CI's own order locally:

===============  ==================================================  ==========
id               defect                                               fixed by
===============  ==================================================  ==========
§3.4-A           CI's drift check was a **false positive**: pytest     every
                 overwrote the *published* artifacts with quick-mode   ``main()``
                 output before the snapshot was taken                 takes
                                                                   ``--out``
§3.4-B           the Docker image never copied ``shared/``, so the     one
                 default ``CMD`` (pytest) and the README's            ``COPY
                 ``cone_table.py`` invocation both hit                 shared/``
                 ``FileNotFoundError`` on ``/work/shared/C0/…``
§3.4-C           two checked-in artifacts could not be reproduced     drift
                 from the current sources                             test below
§3.4-D           ``quant_evidence._import_pinned_quits`` leaked the    the pinned
                 pinned tree onto ``sys.path`` for the rest of the     import is
                 process, flipping ``metadata.quits_file``            context-managed
===============  ==================================================  ==========

These tests are the locks.  They are deliberately **cheap** — no QUITS
import, no circuit construction — because they must stay runnable in the
``python -m pytest OOPSLA -q`` sweep and inside the container's default
``CMD``.  The two files that were genuinely stale in §3.4-C
(``artifact_invariance.*`` and ``change_locality_matrix.*``) are re-derived
from source here; that is ~1.3 s, which is affordable and is the only
place where "the checked-in number is reproducible" is actually asserted
inside pytest rather than only in CI.
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
REPO_ROOT = OOPSLA_ROOT.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import outdir  # noqa: E402  (path shim above)
import pytest  # noqa: E402

#: the seven experiments whose ``*.json`` / ``*.md`` are checked in
EXPERIMENTS = (
    "cone_table",
    "artifact_invariance",
    "change_locality_matrix",
    "quant_evidence",
    "extract_read_sets",
    "dynamic_impact",
    "stim_circuit_gate",
)

#: script name -> published file stem (``extract_read_sets.py`` publishes
#: ``read_sets.json`` because that is the name of the *artefact*, not the
#: extractor)
PUBLISHED_STEM = {"extract_read_sets": "read_sets"}

#: artifacts that are cheap enough to re-derive inside pytest
FAST_REPRODUCIBLE = ("artifact_invariance", "change_locality_matrix")

#: `abstraction.CORPUS_PATH` walks up two parents from `src/`, i.e. the image
#: directory that holds both `OOPSLA/` and `shared/`
CORPUS_TAIL = ("shared", "C0", "corpus.json")


def _normalise(text: str) -> str:
    """Blank out the two volatile classes (see ``src/outdir.py``).

    This delegates to the *same* function CI uses, so the local regression
    test and the CI gate can never disagree about what counts as drift.
    """
    return outdir.normalise_for_drift(text, REPO_ROOT)


def _published(stem: str, suffix: str) -> Path:
    return HERE / f"{PUBLISHED_STEM.get(stem, stem)}.{suffix}"


# ---------------------------------------------------------------------------
# A — publishing vs. self-testing are separable (`src/outdir.py`)
# ---------------------------------------------------------------------------

def test_outdir_resolves_flag_argument_and_creates_the_directory(tmp_path):
    """``--out DIR`` wins over the default and creates DIR if missing."""
    target = tmp_path / "scratch" / "nested"
    assert not target.exists()
    resolved = outdir.resolve_out(["--out", str(target)], HERE)
    assert resolved == target
    assert resolved.is_dir()


def test_outdir_defaults_to_the_publishing_directory_without_the_flag():
    """No ``--out`` ⇒ publish next to the script (this is the *documented*
    publishing behaviour; everything else in this file checks that nothing
    takes that path by accident)."""
    assert outdir.resolve_out([], HERE) == HERE
    assert outdir.resolve_out(["--quick"], HERE) == HERE


def test_outdir_rejects_a_dangling_flag():
    with pytest.raises(SystemExit):
        outdir.resolve_out(["--out"], HERE)


@pytest.mark.parametrize("stem", EXPERIMENTS)
def test_every_experiment_routes_its_writes_through_outdir(stem):
    """Each ``main()`` must resolve its output directory through
    ``outdir.resolve_out(argv, HERE)``; a script that writes ``HERE / name``
    unconditionally cannot be run by pytest or by CI's drift step."""
    src = (HERE / f"{stem}.py").read_text(encoding="utf-8")
    assert "import outdir" in src, f"{stem} does not import the outdir helper"
    assert "outdir.resolve_out(argv, HERE)" in src, (
        f"{stem}.main() does not call outdir.resolve_out(argv, HERE) — "
        "its published artifacts would be overwritten by any caller "
        "(§3.4-D)")


@pytest.mark.parametrize("stem", EXPERIMENTS)
def test_every_experiment_has_both_published_files(stem):
    for suffix in ("json", "md"):
        p = _published(stem, suffix)
        assert p.is_file() and p.stat().st_size > 0, p.name


@pytest.mark.parametrize("stem", EXPERIMENTS)
def test_experiment_main_signatures_accept_argv(stem):
    """``main(argv)`` (not ``main()``) is what makes ``--out`` reachable
    from pytest; a bare ``main()`` would silently ignore the flag."""
    mod = __import__(stem)
    assert callable(getattr(mod, "main", None)), stem
    params = list(inspect.signature(mod.main).parameters)
    assert params == ["argv"], (stem, params)


def test_the_suite_never_calls_a_publishing_main_without_out():
    """The §3.4-A false positive in its purest form: *this* test suite is
    the thing that used to overwrite the published artifacts.  Lock it by
    requiring every ``<script>.main([...])`` call inside the suite to pass
    ``--out``."""
    offenders = []
    for test_file in sorted(HERE.glob("test_*.py")):
        tree = ast.parse(test_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "main"):
                continue
            owner = getattr(func.value, "id", None)
            if owner not in EXPERIMENTS:
                continue
            literals = []
            for a in node.args:
                for sub in (a.elts if isinstance(a, ast.List) else [a]):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        literals.append(sub.value)
            if outdir.FLAG not in literals:
                offenders.append(f"{test_file.name}:{node.lineno} {owner}.main(")
    assert not offenders, (
        "these calls would overwrite the published artifacts "
        "(§3.4-A/§3.4-D): " + "; ".join(offenders))


@pytest.mark.parametrize("stem", FAST_REPRODUCIBLE)
def test_checked_in_artifact_is_reproducible_from_source(stem, tmp_path):
    """§3.4-C: two published outputs were stale — ``artifact_invariance.json``
    was missing ``assembly_model_sources[...]["_baseline_dimensions"]`` and
    ``change_locality_matrix`` still carried an older ``column_provenance``
    string.  Re-derive them and compare byte-for-byte after normalising the
    repo-root path (the only machine-dependent string, README §6)."""
    mod = __import__(stem)
    assert mod.main(["--out", str(tmp_path)]) == 0
    for suffix in ("json", "md"):
        new = tmp_path / f"{stem}.{suffix}"
        old = _published(stem, suffix)
        assert old.is_file(), f"published {old.name} is missing"
        assert _normalise(old.read_text(encoding="utf-8")) == \
            _normalise(new.read_text(encoding="utf-8")), (
            f"{old.name} is stale — re-run "
            f"`python OOPSLA/experiments/{stem}.py` and commit the result")


def test_the_regenerated_artifacts_land_in_tmp_not_in_the_repository(tmp_path):
    """``--out tmp_path`` must be honoured by every write, including the
    legacy-corpus variants the suite exercises."""
    import cone_table

    before = {p.name: p.stat().st_mtime_ns
              for p in HERE.glob("cone_table.*") if p.is_file()}
    assert cone_table.main(["--configs", "24", "--out", str(tmp_path)]) == 0
    after = {p.name: p.stat().st_mtime_ns
             for p in HERE.glob("cone_table.*") if p.is_file()}
    assert before == after, sorted(set(before) ^ set(after))
    assert (tmp_path / "cone_table.json").is_file()
    blob = json.loads((tmp_path / "cone_table.json").read_text(encoding="utf-8"))
    assert blob["metadata"]["n_configs"] == 24


# ---------------------------------------------------------------------------
# B — the container can actually run the documented commands
# ---------------------------------------------------------------------------

DOCKERFILE = OOPSLA_ROOT / "Dockerfile"


def _dockerfile_text() -> str:
    assert DOCKERFILE.is_file(), "OOPSLA/Dockerfile is missing"
    return DOCKERFILE.read_text(encoding="utf-8")


def test_corpus_path_is_resolved_two_parents_above_src():
    """``abstraction.CORPUS_PATH`` climbs out of ``OOPSLA/src`` twice, so it
    lands on the directory that must hold ``shared/`` in the image."""
    import abstraction

    assert abstraction.CORPUS_PATH.parts[-3:] == CORPUS_TAIL, \
        abstraction.CORPUS_PATH
    # .../OOPSLA/src/abstraction.py -> parents[2] is the repo root
    assert Path(inspect.getfile(abstraction)).resolve().parents[2] == \
        OOPSLA_ROOT.parent.resolve()


def test_dockerfile_copies_the_shared_tree():
    """§3.4-B: without this line the default ``CMD`` dies in
    ``FileNotFoundError`` as soon as a test calls ``load_corpus()``."""
    text = _dockerfile_text()
    copies = [ln.strip() for ln in text.splitlines()
              if ln.strip().upper().startswith("COPY ")]
    targets = {ln.split()[2].rstrip("/") for ln in copies if len(ln.split()) >= 3}
    assert "/work/shared" in targets, (
        "the image never copies shared/; `abstraction.CORPUS_PATH` resolves "
        "to /work/shared/C0/corpus.json.  Found: " + "; ".join(copies))


def test_dockerfile_copies_the_artifact_and_the_pinned_tree():
    targets = {ln.split()[2].rstrip("/") for ln in _dockerfile_text().splitlines()
               if ln.strip().upper().startswith("COPY ") and len(ln.split()) >= 3}
    assert {"/work/OOPSLA", "/work/third_party"} <= targets, sorted(targets)


def test_dockerfile_default_cmd_is_the_pytest_suite():
    """The README advertises ``docker run --rm oopsla-quits`` as 'runs the
    suite', so the default ``CMD`` has to be the suite and must be given an
    absolute in-image path (the image's ``WORKDIR`` is ``/work``)."""
    cmds = [ln.strip() for ln in _dockerfile_text().splitlines()
            if ln.strip().startswith("CMD ")]
    assert cmds, "the Dockerfile has no default CMD"
    cmd = cmds[-1]
    assert "-m" in cmd and "pytest" in cmd, cmd
    assert "/work/OOPSLA" in cmd, cmd
    # PYTHONHASHSEED must be image-wide: three artifacts record stim-circuit
    # fingerprints that depend on it (README §4.6).
    assert 'ENV PYTHONHASHSEED=0' in _dockerfile_text()


# ---------------------------------------------------------------------------
# D — the pinned-tree import does not outlive the call that needed it
# ---------------------------------------------------------------------------

def test_pinned_quits_import_is_context_managed_and_restores_state():
    """§3.4-D's cause: ``quant_evidence._import_pinned_quits`` used to
    ``sys.path.insert(0, pinned_src)`` permanently, which flipped
    ``dynamic_impact``'s ``metadata.quits_file`` from the installed wheel to
    the pinned snapshot depending on **which test ran first**."""
    import contextlib

    import quant_evidence

    cm = getattr(quant_evidence, "_isolate_pinned_quits", None)
    assert cm is not None, (
        "quant_evidence must expose a context manager that saves/restores "
        "sys.path and sys.modules around the pinned-tree import")
    assert hasattr(cm, "__wrapped__") and \
        inspect.isgeneratorfunction(cm.__wrapped__), (
        "_isolate_pinned_quits must be @contextlib.contextmanager over a "
        "generator with a finally-block restore")

    path_before = list(sys.path)
    modules_before = {k for k in sys.modules
                      if k == "quits" or k.startswith("quits.")}
    try:
        with cm():
            assert sys.path != path_before, (
                "the pinned src directory was put on sys.path")
    except quant_evidence._Unavailable:
        pytest.skip("pinned quits tree is not importable in this environment")
    assert sys.path == path_before
    assert {k for k in sys.modules
            if k == "quits" or k.startswith("quits.")} == modules_before


def test_quant_evidence_published_metadata_names_the_tree_it_measured():
    """``metadata.quits_file`` is the only machine-dependent field, but it
    must at least name *a* tree, and the pinned one — otherwise the run was
    not the pinned run."""
    import quant_evidence

    blob = json.loads(_published("quant_evidence", "json")
                      .read_text(encoding="utf-8"))
    meta = blob["metadata"]
    assert meta["quits_commit"] == quant_evidence.QUITS_COMMIT
    assert "third_party" in meta.get("quits_src", "") or \
        "third_party" in meta.get("quits_file", ""), meta


# ---------------------------------------------------------------------------
# the drift gate itself
# ---------------------------------------------------------------------------

def test_normalise_for_drift_blanks_absolute_paths_and_dates_only():
    """The two — and only two — volatile classes.  Anything else (a number,
    a verdict, a modelling-provenance string) must survive normalisation, or
    the drift check would stop being a regression test."""
    sample = json.dumps({"quits_file": r"C:\work\repo\t",
                         "date": "2026-10-09",
                         "summary": {"applicable": 200, "verdict": "bounded"}},
                        indent=2)
    later = sample.replace("2026-10-09", "2026-12-31")
    assert outdir.normalise_for_drift(sample, r"C:\work\repo") == \
        outdir.normalise_for_drift(later, r"C:\work\repo")
    changed = sample.replace('"applicable": 200', '"applicable": 240')
    assert outdir.normalise_for_drift(sample, r"C:\work\repo") != \
        outdir.normalise_for_drift(changed, r"C:\work\repo")
    assert "2026-10-09" not in outdir.normalise_for_drift(
        "Generated: 2026-10-09  \n", r"C:\work\repo")
    assert "<VOLATILE>" in outdir.normalise_for_drift(
        "Generated: 2026-10-09  \n", r"C:\work\repo")


def test_date_stamping_scripts_do_not_make_the_gate_red_every_midnight():
    """Regression test for a defect found on 2026-10-10: five of the seven
    scripts stamp ``date.today()`` into their output, so comparing the
    checked-in artifacts literally turned the drift check red as soon as the
    calendar moved, with the *content* byte-identical (measured: all eight
    files of four experiments differed in the date line only).

    The invariant: the two *structured* date slots — the JSON metadata field
    and the Markdown ``Generated:`` header — are blanked for **any** date, in
    every published artifact."""
    import re

    slot_json = re.compile(r'"date"\s*:\s*"\d{4}-\d{2}-\d{2}"')
    slot_md = re.compile(r"Generated:\s*\d{4}-\d{2}-\d{2}")
    seen = 0
    for name in EXPERIMENTS:
        for suffix in ("json", "md"):
            p = _published(name, suffix)
            if not p.is_file():
                continue
            blanked = outdir.normalise_for_drift(p.read_text(encoding="utf-8"),
                                                 REPO_ROOT)
            assert not slot_json.search(blanked), p.name
            assert not slot_md.search(blanked), p.name
            seen += 1
    assert seen >= 14, seen


@pytest.mark.parametrize("stamp", ['"date": "1999-12-31",',
                                   "Generated: 2027-01-01  "])
def test_every_date_value_is_blanked_in_both_structured_slots(stamp):
    blanked = outdir.normalise_for_drift(stamp, REPO_ROOT)
    assert "1999" not in blanked and "2027" not in blanked, blanked
    assert "<VOLATILE>" in blanked, blanked


def test_normalise_for_drift_blanks_the_json_escaped_windows_path():
    """On Linux the CI normaliser matched the forward-slash spelling; the
    JSON *escapes* backslashes, so on Windows a naive replacement silently
    keeps the path and every artifact with ``metadata.quits_file`` reads as
    stale forever."""
    raw = r"C:\work\1014gogogo"
    escaped = json.dumps({"quits_file": raw + r"\third_party"})[1:-1]
    assert "\\\\" in escaped                      # the JSON really doubled them
    assert raw not in escaped                     # ...so the raw form is absent
    blanked = outdir.normalise_for_drift(escaped, raw)
    assert "1014gogogo" not in blanked, blanked


def test_ci_uses_the_shared_comparator_rather_than_a_private_one():
    """If ci.yml grows its own normalisation inline, it can silently disagree
    with the local regression test."""
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8")
    assert "outdir.drift_report(" in ci, "CI must call outdir.drift_report"
    assert "def normalise(" not in ci, \
        "CI must not define a private normaliser (it would rot)"


def test_drift_report_ignores_a_date_bump_but_flags_a_changed_number(tmp_path):
    """``drift_report`` is the gate CI calls; check both directions on a
    synthetic pair so the contract is pinned independently of which
    artifacts happen to be checked in today."""
    committed = tmp_path / "committed"
    regen = tmp_path / "regenerated"
    committed.mkdir()
    regen.mkdir()
    (committed / "demo.json").write_text(json.dumps(
        {"date": "2026-10-09", "quits_file": r"C:\work\repo\t",
         "summary": {"applicable": 200}}, indent=2), encoding="utf-8")
    # same checkout (so the path is identical), next day
    (regen / "demo.json").write_text(json.dumps(
        {"date": "2026-10-10", "quits_file": r"C:\work\repo\t",
         "summary": {"applicable": 200}}, indent=2), encoding="utf-8")
    assert outdir.drift_report(committed, regen, r"C:\work\repo") == []
    # one changed number is drift
    (regen / "demo.json").write_text(json.dumps(
        {"date": "2026-10-10", "quits_file": r"C:\work\repo\t",
         "summary": {"applicable": 240}}, indent=2), encoding="utf-8")
    assert outdir.drift_report(committed, regen, r"C:\work\repo") == ["demo.json"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))