"""Real-artifact gate for subject 2 (qecc_routing).

The answer to "your second subject is a toy table" (``subject_system2.md``
§5 item 1): this gate **executes the pinned qecc_routing pipeline** and
measures, on its real products, the three controls the QUITS side runs in
``stim_circuit_gate``:

  (a) **code change moves the artifacts** -- swapping the module-level
      ``code`` spec (one of the repo's own commented candidate codes,
      general.py:17) must change Hz, the lattice, the success-probability
      vectors and the built stim circuit;
  (b) **noise-only change moves the products of components that declare
      only ``{code}``** -- patching nothing but the global ``probs`` /
      ``idle_error`` tables (general.py:39-41) changes
      ``x/z_check_succ_probs`` (computed by the component the hand model
      calls ``succ_probs``) and the idle DEPOLARIZE1 probability inside the
      real ``stim.Circuit`` (the ``idle`` component) -- the hidden
      dependency, evidenced on real artifacts (the H3 reverse control of
      QUITS's ``stim_circuit_gate``);
  (c) **faithful components are invariant** -- under the noise-only change
      the products of the code/embedding/geometry components are
      byte-identical to baseline.

Execution model.  ``general.py`` is a script: its module-level experiment
loop (general.py:448-496, a tqdm loop over 1,000,001 iterations writing
into ``results/``) runs at import and is not a unit of work this gate can
execute.  The gate therefore loads the module **from its file path**
(the directory name ``bivariate-bicycle`` is not an importable package
name) with importlib-style ``compile``/``exec`` of the *unmodified* source
truncated exactly at the experiment loop, and applies substitutions as
*source-level re-assignments of the module globals* (``code = [...]``,
``probs = probs * 0.9``) before any consumer runs.  Every definition --
A/B polynomials, Hx/Hz, ``embed_code``, the radii, the success
probabilities, ``Simulation`` -- is the pinned code itself; nothing is
re-implemented.  The pinned tree is never written to.

Every artifact comparison is a sha256 over the artifact's bytes plus, where
shapes allow, ``np.array_equal`` and ``max|Δ|``.

No toy replica anywhere: if the pinned pipeline cannot run, this script
fails; there is no fallback simulation.

Outputs (written next to this file):
  - ``subject2_artifact_gate.json`` / ``subject2_artifact_gate.md``

Run:  python experiments/subject2_artifact_gate.py [--quick] [--out DIR]
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")   # headless circuit building

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

import outdir  # noqa: E402
import subject2_qecc as S2  # noqa: E402  (commit pin + hand model)
from subject2_read_sets import dependency_report  # noqa: E402

QECC_DIR = (OOPSLA_ROOT.parent / "third_party" / f"qecc_routing-{S2.QECC_COMMIT}"
            / "src_py" / "bivariate-bicycle")
GENERAL_PY = QECC_DIR / "general.py"
if str(QECC_DIR) not in sys.path:
    sys.path.insert(0, str(QECC_DIR))   # `from mec import make_circle` etc.

SEED = 20261012
LR_TIME = 5
NUM_ROUNDS_FULL = 10
NUM_ROUNDS_QUICK = 2

#: the pinned baseline spec line and the repo's own commented alternative
#: (general.py:17, a k=8 code) used by control (a)
BASELINE_CODE_LINE = "code = [9,5,8,4,1,5,8,7,5,9,2,1,9,5]"
ALT_CODE = "[12,3,9,1,2,0,1,11,3,12,2,0,11,6]"
#: control (b): only the noise globals are re-assigned, after their pinned
#: definitions (general.py:39-41) and before any consumer executes
NOISE_OVERRIDE_LINES = ["probs = probs * 0.9", "idle_error = 2 * idle_error"]


# ---------------------------------------------------------------------------
# loading the pinned module (truncated at the experiment loop)
# ---------------------------------------------------------------------------

def general_source() -> str:
    """The pinned general.py with the module-level experiment loop removed.

    Everything up to and including ``p_mask`` (general.py:447) is kept
    verbatim -- that is the whole component layer; general.py:448-496 is
    the 1e6-iteration experiment driver, not a definition.
    """
    lines = GENERAL_PY.read_text(encoding="utf-8").splitlines(keepends=True)
    cut = next(i for i, l in enumerate(lines)
               if l.startswith("for T in range(20, 21, 10):"))
    return "".join(lines[:cut])


def load_general(code_value: str | None = None,
                 extra_lines: list[str] | None = None) -> dict:
    """Execute the pinned module source with substitutions applied.

    ``code_value`` replaces the pinned ``code = [...]`` spec line;
    ``extra_lines`` are inserted right after ``idle_error = 0.0002``
    (general.py:41), i.e. after every pinned global definition and before
    any consumer of it runs.
    """
    src = general_source()
    if code_value is not None:
        if BASELINE_CODE_LINE not in src:               # pragma: no cover
            raise RuntimeError("pinned code spec line not found")
        src = src.replace(BASELINE_CODE_LINE,
                          f"code = {code_value}", 1)
    if extra_lines:
        anchor = "idle_error = 0.0002\n"
        if anchor not in src:                           # pragma: no cover
            raise RuntimeError("pinned idle_error line not found")
        src = src.replace(anchor, anchor + "".join(
            line + "\n" for line in extra_lines), 1)
    module = {"__name__": "qecc_general_gate", "__file__": str(GENERAL_PY)}
    exec(compile(src, str(GENERAL_PY), "exec"), module)   # noqa: S102
    return {"module": module,
            "source_sha256": hashlib.sha256(src.encode()).hexdigest()}


# ---------------------------------------------------------------------------
# artifact production (the module's own products, nothing re-implemented)
# ---------------------------------------------------------------------------

def _sha(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def build_artifacts(module: dict, num_rounds: int) -> dict:
    """The real products of the pinned pipeline for one module instance."""
    mod = module["module"]
    np.random.seed(SEED)                      # simulate() draws route coin flips
    sim = mod["Simulation"](num_rounds, LR_TIME)
    sim.simulate()
    circuit = sim.c

    lattice_cells = [[str(cell) for cell in row] for row in mod["lattice"]]
    depolarize1_probs = sorted({round(inst.gate_args_copy()[0], 12)
                                for inst in circuit
                                if inst.name == "DEPOLARIZE1"})
    return {
        "Hz": {"sha256": _sha(np.asarray(mod["Hz"])),
               "shape": list(np.asarray(mod["Hz"]).shape)},
        "lattice": {"sha256": hashlib.sha256(
                        json.dumps(lattice_cells).encode()).hexdigest(),
                    "shape": list(mod["lattice"].shape)},
        "x_rs": {"sha256": _sha(np.asarray(mod["x_rs"], dtype=np.float64)),
                 "len": len(mod["x_rs"])},
        "z_rs": {"sha256": _sha(np.asarray(mod["z_rs"], dtype=np.float64)),
                 "len": len(mod["z_rs"])},
        "split": {"sha256": hashlib.sha256(json.dumps(
                      [mod["lr_x_checks"].tolist(), mod["sr_x_checks"].tolist(),
                       mod["lr_z_checks"].tolist(),
                       mod["sr_z_checks"].tolist()]).encode()).hexdigest()},
        "succ_probs": {"x_sha256": _sha(np.asarray(mod["x_check_succ_probs"])),
                       "z_sha256": _sha(np.asarray(mod["z_check_succ_probs"])),
                       "len": len(mod["x_check_succ_probs"])},
        "circuit": {"sha256": hashlib.sha256(
                        str(circuit).encode()).hexdigest(),
                    "num_measurements": circuit.num_measurements,
                    "num_detectors": circuit.num_detectors},
        "depolarize1_probs": depolarize1_probs,
        # raw copies for the comparisons below (not serialised)
        "_raw": {"x_succ": np.asarray(mod["x_check_succ_probs"]),
                 "z_succ": np.asarray(mod["z_check_succ_probs"]),
                 "Hz": np.asarray(mod["Hz"])},
    }


def run_variant(name: str, num_rounds: int, code_value: str | None = None,
                extra_lines: list[str] | None = None,
                patch_description: str = "none (pinned baseline)") -> dict:
    module = load_general(code_value=code_value, extra_lines=extra_lines)
    artifacts = build_artifacts(module, num_rounds)
    raw = artifacts.pop("_raw")
    return {"name": name, "patch": patch_description,
            "source_sha256": module["source_sha256"],
            "artifacts": artifacts, "_raw": raw}


# ---------------------------------------------------------------------------
# the three controls
# ---------------------------------------------------------------------------

def _cmp_num(a: np.ndarray, b: np.ndarray) -> dict:
    if a.shape != b.shape:
        return {"changed": True, "same_shape": False,
                "max_abs_delta": None}
    return {"changed": not np.array_equal(a, b), "same_shape": True,
            "max_abs_delta": float(np.max(np.abs(a - b))) if a.size else 0.0}


def compare(baseline: dict, alt: dict) -> dict:
    """sha256-based comparison of every artifact, plus numeric deltas where
    shapes allow."""
    rows = {}
    b, a = baseline["artifacts"], alt["artifacts"]
    for key in ("Hz", "lattice", "x_rs", "z_rs", "split", "circuit"):
        rows[key] = {"baseline_sha256": b[key]["sha256"],
                     "alt_sha256": a[key]["sha256"],
                     "changed": b[key]["sha256"] != a[key]["sha256"]}
    rows["succ_probs_x"] = {
        **{k: v for k, v in _cmp_num(baseline["_raw"]["x_succ"],
                                     alt["_raw"]["x_succ"]).items()},
        "baseline_sha256": b["succ_probs"]["x_sha256"],
        "alt_sha256": a["succ_probs"]["x_sha256"]}
    rows["succ_probs_z"] = {
        **{k: v for k, v in _cmp_num(baseline["_raw"]["z_succ"],
                                     alt["_raw"]["z_succ"]).items()},
        "baseline_sha256": b["succ_probs"]["z_sha256"],
        "alt_sha256": a["succ_probs"]["z_sha256"]}
    rows["depolarize1_probs"] = {
        "baseline": b["depolarize1_probs"], "alt": a["depolarize1_probs"],
        "changed": b["depolarize1_probs"] != a["depolarize1_probs"]}
    return rows


def run(quick: bool = False) -> dict:
    num_rounds = NUM_ROUNDS_QUICK if quick else NUM_ROUNDS_FULL
    baseline = run_variant("baseline", num_rounds)
    code_alt = run_variant(
        "code_alt", num_rounds, code_value=ALT_CODE,
        patch_description=f"general.py:18 `code` -> the repo's own "
                          f"commented k=8 candidate (general.py:17): "
                          f"{ALT_CODE}")
    noise_alt = run_variant(
        "noise_alt", num_rounds, extra_lines=NOISE_OVERRIDE_LINES,
        patch_description="only the noise globals re-assigned after their "
                          "pinned definitions (general.py:39-41): "
                          + "; ".join(NOISE_OVERRIDE_LINES))
    # reproducibility: a second, independent load+run of the same baseline
    baseline2 = run_variant("baseline_repro", num_rounds)
    repro = {"Hz": baseline["artifacts"]["Hz"]["sha256"]
             == baseline2["artifacts"]["Hz"]["sha256"],
             "lattice": baseline["artifacts"]["lattice"]["sha256"]
             == baseline2["artifacts"]["lattice"]["sha256"],
             "succ_probs": baseline["artifacts"]["succ_probs"]["x_sha256"]
             == baseline2["artifacts"]["succ_probs"]["x_sha256"]
             and baseline["artifacts"]["succ_probs"]["z_sha256"]
             == baseline2["artifacts"]["succ_probs"]["z_sha256"],
             "circuit": baseline["artifacts"]["circuit"]["sha256"]
             == baseline2["artifacts"]["circuit"]["sha256"]}

    cmp_code = compare(baseline, code_alt)
    cmp_noise = compare(baseline, noise_alt)

    code_change = {
        "question": "(a) does a code-spec change move the real artifacts?",
        "comparisons": cmp_code,
        "verdict_pass": (cmp_code["Hz"]["changed"]
                         and cmp_code["lattice"]["changed"]
                         and cmp_code["succ_probs_x"]["changed"]
                         and cmp_code["circuit"]["changed"]),
    }
    noise_only = {
        "question": "(b) does a noise-only change move the products of "
                    "components that declare only {code}?",
        "hidden_components": sorted(S2.FAITHFUL_BUT_WRONG),
        "comparisons": cmp_noise,
        "verdict_pass": (
            cmp_noise["succ_probs_x"]["changed"]
            and cmp_noise["succ_probs_z"]["changed"]
            and cmp_noise["depolarize1_probs"]["changed"]
            and cmp_noise["circuit"]["changed"]
            # ... while the products of components that do NOT read noise
            # hold byte-for-byte (this is control (c), asserted here so a
            # regression in either direction fails the same case):
            and not cmp_noise["Hz"]["changed"]
            and not cmp_noise["lattice"]["changed"]
            and not cmp_noise["x_rs"]["changed"]
            and not cmp_noise["split"]["changed"]),
        "interpretation":
            "succ_probs and idle declare R(c) = {code} in the hand model, "
            "yet the real pipeline recomputes their products from the "
            "global `probs`/`idle_error` tables: the noise-only patch "
            "changes x/z_check_succ_probs (max|Δ| > 0) and the idle "
            "DEPOLARIZE1 probability inside the real stim.Circuit.  This "
            "is hypothesis H3 evidenced on real artifacts, on a system "
            "with no registry.",
    }
    invariance = {
        "question": "(c) are faithful components' products invariant under "
                    "a coordinate they do not declare?",
        "unchanged_artifacts": {
            k: {"baseline_sha256": cmp_noise[k]["baseline_sha256"],
                "held": not cmp_noise[k]["changed"]}
            for k in ("Hz", "lattice", "x_rs", "z_rs", "split")},
        "verdict_pass": all(not cmp_noise[k]["changed"]
                            for k in ("Hz", "lattice", "x_rs", "z_rs",
                                      "split")),
    }
    return {
        "metadata": {
            "title": "subject 2 real-artifact gate (qecc_routing pipeline)",
            "date": date.today().isoformat(),
            "subject": "qecc_routing (Berthusen et al., arXiv:2404.17676)",
            "qecc_commit": S2.QECC_COMMIT,
            "source_file": "src_py/bivariate-bicycle/general.py",
            "method": "compile/exec of the pinned general.py from its file "
                      "path (the directory name is not a package name), "
                      "truncated at the module-level experiment loop "
                      "(general.py:448); substitutions are source-level "
                      "re-assignments of module globals; every product is "
                      "produced by the pinned code itself",
            "truncation": "general.py:448-496 (the tqdm experiment driver, "
                          "1,000,001 iterations writing into results/) is "
                          "not a definition and is not executed",
            "seed": SEED, "lr_time": LR_TIME, "num_rounds": num_rounds,
            "quick": quick,
            "dependency_availability": dependency_report(),
        },
        "variants": {v["name"]: {"patch": v["patch"],
                                 "source_sha256": v["source_sha256"],
                                 "artifacts": v["artifacts"]}
                     for v in (baseline, code_alt, noise_alt)},
        "reproducibility": {"identical": repro,
                            "all_identical": all(repro.values())},
        "controls": {"code_change": code_change,
                     "noise_only_hidden_read": noise_only,
                     "faithful_invariance": invariance},
        "summary": {
            "all_pass": (code_change["verdict_pass"]
                         and noise_only["verdict_pass"]
                         and invariance["verdict_pass"]
                         and all(repro.values())),
            "max_abs_delta_succ_probs_x":
                cmp_noise["succ_probs_x"]["max_abs_delta"],
            "max_abs_delta_succ_probs_z":
                cmp_noise["succ_probs_z"]["max_abs_delta"],
        },
    }


# ---------------------------------------------------------------------------
# markdown
# ---------------------------------------------------------------------------

def to_markdown(d: dict) -> str:
    m, c = d["metadata"], d["controls"]
    L = ["# Subject 2 real-artifact gate — qecc_routing pipeline", "",
         f"Generated: {m['date']}  ",
         f"commit: `{m['qecc_commit']}`  ",
         f"rounds: {m['num_rounds']}, lr_time: {m['lr_time']}, seed: "
         f"{m['seed']}  ",
         f"Method: {m['method']}", "",
         f"> {m['truncation']}.  Substitutions never touch the pinned "
         "tree; they are re-assignments of module globals in the executed "
         "copy.", ""]
    L += ["## Variants", "", "| variant | patch |", "|---|---|"]
    for name, v in d["variants"].items():
        L.append(f"| `{name}` | {v['patch']} |")
    L += ["", "## (a) code change moves the real artifacts", ""]
    for k, r in c["code_change"]["comparisons"].items():
        L.append(f"- `{k}`: changed = **{r['changed']}**")
    L += ["", f"verdict: **{c['code_change']['verdict_pass']}**", ""]
    L += ["## (b) noise-only change moves the {code}-declared components' "
          "products (the hidden read, on real artifacts)", ""]
    n = c["noise_only_hidden_read"]["comparisons"]
    L += [f"- `succ_probs_x`: changed = **{n['succ_probs_x']['changed']}** "
          f"(max|Δ| = {n['succ_probs_x']['max_abs_delta']:.6g})",
          f"- `succ_probs_z`: changed = **{n['succ_probs_z']['changed']}** "
          f"(max|Δ| = {n['succ_probs_z']['max_abs_delta']:.6g})",
          f"- `depolarize1_probs` (incl. the idle rate): changed = "
          f"**{n['depolarize1_probs']['changed']}** "
          f"({n['depolarize1_probs']['baseline']} -> "
          f"{n['depolarize1_probs']['alt']})",
          f"- `circuit` (stim.Circuit sha256): changed = "
          f"**{n['circuit']['changed']}**", "",
          f"interpretation: {c['noise_only_hidden_read']['interpretation']}",
          "",
          f"verdict: **{c['noise_only_hidden_read']['verdict_pass']}**", ""]
    L += ["## (c) faithful components are invariant under the noise change",
          ""]
    for k, r in c["faithful_invariance"]["unchanged_artifacts"].items():
        L.append(f"- `{k}`: held byte-identical = **{r['held']}**")
    L += ["", f"verdict: **{c['faithful_invariance']['verdict_pass']}**", ""]
    L += ["## Reproducibility", "",
          f"an independent second baseline load/run produces identical "
          f"sha256 for every artifact: **{all(d['reproducibility']['identical'].values())}** "
          f"({d['reproducibility']['identical']})", ""]
    L += ["## Verdict", "",
          f"all controls pass: **{d['summary']['all_pass']}**", ""]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    quick = "--quick" in argv
    out = outdir.resolve_out(argv, HERE)
    d = run(quick=quick)
    (out / "subject2_artifact_gate.json").write_text(
        json.dumps(d, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    (out / "subject2_artifact_gate.md").write_text(
        to_markdown(d), encoding="utf-8")
    print(f"controls: (a) {d['controls']['code_change']['verdict_pass']}  "
          f"(b) {d['controls']['noise_only_hidden_read']['verdict_pass']}  "
          f"(c) {d['controls']['faithful_invariance']['verdict_pass']}  "
          f"repro {all(d['reproducibility']['identical'].values())}")
    print(f"all pass: {d['summary']['all_pass']}")
    print(f"wrote {out / 'subject2_artifact_gate.json'}")
    print(f"wrote {out / 'subject2_artifact_gate.md'}")
    return 0 if d["summary"]["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
