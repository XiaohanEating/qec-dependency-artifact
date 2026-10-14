"""Framework for additional QEC software subjects (Gap 4).

This experiment provides the framework for evaluating our semantics on additional
QEC software packages, addressing **Gap 4**:

> 4. 更多的被测软件：目前只有 QUITS，缺少第二个、第三个独立 QEC 软件上的真实验证。

The following packages are candidates for future evaluation:
- Stim + sinter + PyMatching (the de facto standard stack)
- Deltakit (Google Quantum AI)
- Tsim (AWS Braket / IonQ)
- BP+OSD (standalone decoder)
- qec_code_sim (alternative simulator)

Each would require:
1. Cloning and pinning the repository
2. Implementing the semantic model (Spec, Component, Assembly)
3. Running the audit (hidden dependency detection)
4. Running the substitution experiments
5. Running the physical impact experiments

This file documents the framework and provides a template for adding new subjects.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
REPO_ROOT = OOPSLA_ROOT.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


SUBJECT_SPECS = {
    "stim_sinter_pymatching": {
        "name": "Stim + sinter + PyMatching",
        "repo": "https://github.com/quantumlib/Stim",
        "pinned_commit": "TODO",
        "description": "De facto standard: Stim for circuits, sinter for Monte Carlo, PyMatching for decoding",
        "components": {
            "code": "Stim's stabilizer codes / custom code construction",
            "circuit": "Stim circuit generation (different from QUITS extractor)",
            "noise": "Stim's noise models (DEPOLARIZE, etc.)",
            "decoder": "PyMatching (MWPM) / sinter's internal decoders",
            "simulation": "sinter Monte Carlo sampling",
        },
        "hidden_dependencies_known": [
            "Stim circuit construction reads noise parameters",
            "sinter sampling depends on both circuit and decoder",
            "PyMatching reads detector error model from Stim",
        ],
        "status": "not_cloned",
    },
    "deltakit": {
        "name": "Deltakit (Google Quantum AI)",
        "repo": "https://github.com/quantumlib/deltakit",
        "pinned_commit": "TODO",
        "description": "Google's QEC software stack with tile-based codes",
        "components": {
            "code": "Tile-based stabilizer codes (surface, color, etc.)",
            "circuit": "Stim-based circuit construction",
            "noise": "Custom noise models",
            "decoder": "Internal decoders (MWPM, BP, etc.)",
        },
        "hidden_dependencies_known": [],
        "status": "not_cloned",
    },
    "tsim": {
        "name": "Tsim (AWS Braket / IonQ)",
        "repo": "TODO",
        "pinned_commit": "TODO",
        "description": "AWS Braket simulator for trapped ion QEC",
        "components": {
            "code": "Trapped-ion specific codes",
            "circuit": "Native circuit construction",
            "noise": "Ion-specific noise models",
            "decoder": "Custom decoders",
        },
        "hidden_dependencies_known": [],
        "status": "not_available",
    },
    "bp_osd_standalone": {
        "name": "BP+OSD standalone decoder",
        "repo": "https://github.com/quantumlib/bp_osd",
        "pinned_commit": "TODO",
        "description": "Standalone BP+OSD decoder library",
        "components": {
            "decoder": "BP+OSD implementation",
            "input": "Detector error model + syndrome",
        },
        "hidden_dependencies_known": [],
        "status": "not_cloned",
    },
    "qec_code_sim": {
        "name": "qec_code_sim (alternative simulator)",
        "repo": "TODO",
        "pinned_commit": "TODO",
        "description": "Alternative QEC simulator for cross-validation",
        "components": {
            "code": "Multiple code families",
            "circuit": "Native circuit construction",
            "noise": "Standard noise models",
            "decoder": "Multiple decoders",
        },
        "hidden_dependencies_known": [],
        "status": "not_available",
    },
}


def run() -> dict:
    """Report on the status of additional QEC software subjects."""
    results = {
        "metadata": {
            "description": "Framework for additional QEC software subjects (Gap 4)",
            "date": date.today().isoformat(),
        },
        "subjects": {},
        "requirements": {
            "per_subject": [
                "Clone and pin repository at specific commit",
                "Identify component boundaries (code/circuit/noise/decoder/simulation)",
                "Map to semantic model: Spec, Component, Assembly",
                "Implement produce() functions returning real artifacts",
                "Extract declared read sets R(c) (static analysis or manual)",
                "Run hidden dependency audit (Theorem 3 probe)",
                "Run substitution experiments (Theorem 1 validation)",
                "Run physical impact experiments (LER, threshold, decoder ranking)",
                "Document any hidden dependencies found",
            ],
            "infrastructure_needed": [
                "Docker images for each subject (or conda environments)",
                "Shared evaluation script that works across subjects",
                "Unified artifact fingerprinting (stim circuit, DEM, etc.)",
                "Cross-subject comparison tables",
            ],
        },
    }

    for key, spec in SUBJECT_SPECS.items():
        results["subjects"][key] = spec

    return results


def to_markdown(data: dict) -> str:
    m = data["metadata"]
    L = ["# Additional QEC Software Subjects Framework (Gap 4)", "",
         f"Generated: {m['date']}", ""]

    L += ["## Subject Status Overview", ""]
    for key, spec in data["subjects"].items():
        L += [f"### {spec['name']} (`{key}`)", ""]
        L += [f"- **Repo**: {spec['repo']}", ""]
        L += [f"- **Pinned commit**: {spec['pinned_commit']}", ""]
        L += [f"- **Description**: {spec['description']}", ""]
        L += [f"- **Status**: {spec['status']}", ""]
        L += ["- **Components**:", ""]
        for comp, desc in spec["components"].items():
            L += [f"  - `{comp}`: {desc}"]
        L += [""]
        if spec["hidden_dependencies_known"]:
            L += ["- **Known hidden dependencies**:", ""]
            for dep in spec["hidden_dependencies_known"]:
                L += [f"  - {dep}"]
            L += [""]
        else:
            L += ["- **Known hidden dependencies**: None documented yet", ""]
        L += [""]

    L += ["## Per-Subject Requirements", ""]
    for req in data["requirements"]["per_subject"]:
        L += [f"- {req}"]
    L += [""]

    L += ["## Infrastructure Needed", ""]
    for req in data["requirements"]["infrastructure_needed"]:
        L += [f"- {req}"]
    L += [""]

    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out_dir = None
    if "--out" in argv:
        idx = argv.index("--out")
        out_dir = Path(argv[idx + 1])
        argv = argv[:idx] + argv[idx + 2:]

    data = run()

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "additional_subjects.json").write_text(json.dumps(data, indent=2))
        (out_dir / "additional_subjects.md").write_text(to_markdown(data))
    else:
        (HERE / "additional_subjects.json").write_text(json.dumps(data, indent=2))
        (HERE / "additional_subjects.md").write_text(to_markdown(data))

    print("Additional subjects framework completed.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())