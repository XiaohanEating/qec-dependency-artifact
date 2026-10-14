"""Execute upstream qecc Simulation definitions and read actual dependencies.

No third-party source modification. The isolated namespace's NumPy seed is
fixed. AST names and runtime executed lines jointly identify global reads.
"""
import argparse
import ast
import contextlib
import io
import subprocess
import sys
from pathlib import Path

import numpy as np

from common import ROOT, WORKSPACE, digest, environment, file_hash, write_json
from dependency_engine import Task, compare

UPSTREAM = WORKSPACE / "third_party" / "qecc_routing-4ef18121c39492414b85ff36b3a61c83f9ebf95f" / "src_py" / "bivariate-bicycle"
GENERAL = UPSTREAM / "general.py"


def load_namespace():
    source = GENERAL.read_text(encoding="utf-8")
    cut = source.index("lr_time = 5")
    namespace = {"__name__": "qecc_definitions", "__file__": str(GENERAL)}
    sys.path.insert(0, str(UPSTREAM))
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(source[:cut], str(GENERAL), "exec"), namespace)
    return namespace, source[:cut]


def construct(namespace, idle, depth):
    namespace["idle_error"] = idle
    np.random.seed(2026)
    executed = set()

    def tracer(frame, event, arg):
        if event == "line" and frame.f_code.co_filename == str(GENERAL):
            executed.add(frame.f_lineno)
        return tracer

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        simulation = namespace["Simulation"](5, depth)
        simulation.simulate()
    finally:
        sys.settrace(previous)
    circuit = simulation.c
    dem = circuit.detector_error_model()
    return circuit, dem, sorted(executed)


def read_evidence(source, lines):
    globals_ = {"code", "idle_error", "muls001", "probs", "x_check_succ_probs", "z_check_succ_probs",
                "sr_z_checks", "lr_z_checks", "sr_x_checks", "lr_x_checks", "all_qbts", "qbts", "Hx", "Hz", "ell", "m"}
    nodes = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)
             and isinstance(n.ctx, ast.Load) and n.id in globals_]
    return [{"name": n.id, "line": n.lineno,
             "executed_line": n.lineno in lines,
             "text": source.splitlines()[n.lineno-1].strip()} for n in nodes]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-executable', type=Path)
    parser.add_argument('--native-instance', type=Path)
    args = parser.parse_args()
    if bool(args.native_executable) != bool(args.native_instance):
        parser.error('Provide both --native-executable and --native-instance')
    out = ROOT / "results" / "qecc"
    out.mkdir(parents=True, exist_ok=True)
    namespace, source = load_namespace()
    runs = {}
    for name, idle, depth in (("baseline", 0.0002, 5), ("idle-change", 0.0004, 5),
                              ("routing-change", 0.0002, 4)):
        circuit, dem, lines = construct(namespace, idle, depth)
        (out / (name + ".stim")).write_text(str(circuit), encoding="utf-8")
        (out / (name + ".dem")).write_text(str(dem), encoding="utf-8")
        syndrome, observable = circuit.compile_detector_sampler(seed=2026).sample(32, separate_observables=True)
        np.savez_compressed(out / (name + "-samples.npz"), syndrome=syndrome, observable=observable)
        runs[name] = {"circuit": circuit, "dem": dem, "lines": lines,
                      "schema": {"detectors": circuit.num_detectors, "observables": circuit.num_observables,
                                 "measurements": circuit.num_measurements},
                      "noise_free": str(circuit.without_noise()),
                      "observables": [str(inst) for inst in circuit.flattened() if inst.name == "OBSERVABLE_INCLUDE"]}
    baseline, changed = runs["baseline"], runs["idle-change"]
    assert str(baseline["circuit"]) != str(changed["circuit"])
    assert baseline["noise_free"] == changed["noise_free"]
    tasks = [Task("measurement_schema", lambda r: r.read("circuit", "schema")),
             Task("schema_contract", lambda r: r.read("measurement_schema", "detectors") > 0, True),
             Task("ideal_behavior", lambda r: r.read("circuit", "noise_free")),
             Task("observable_definition", lambda r: r.read("circuit", "observables"))]
    old_payload = {"full": str(baseline["circuit"]), "schema": baseline["schema"],
                   "noise_free": baseline["noise_free"], "observables": baseline["observables"]}
    new_payload = {"full": str(changed["circuit"]), "schema": changed["schema"],
                   "noise_free": changed["noise_free"], "observables": changed["observables"]}
    # Built executable is reused read-only. Failure is recorded, no replacement
    # binary or silently substituted routing result is used.
    native = {"status": "not run: optional native routing build not supplied"}
    proc = None
    if args.native_executable is not None:
        exe, instance = args.native_executable, args.native_instance
        proc = subprocess.run([str(exe), str(instance), "--independent-sets", "--quiet"],
                              capture_output=True, text=True)
        native = {"executable": str(exe), "exe_sha256": file_hash(exe),
                  "instance": str(instance), "returncode": proc.returncode,
                  "stdout": proc.stdout, "stderr": proc.stderr,
                  "status": "success" if proc.returncode == 0 else "native execution failed"}
    write_json(out / "comparison.json", {
        "environment": environment(), "source": str(GENERAL), "source_sha256": file_hash(GENERAL),
        "loaded_definition_lines": len(source.splitlines()), "driver_excluded": "lr_time = 5 and following million-shot loop",
        "rounds": 5, "seed": 2026, "noise_change": {"idle_error": [0.0002, 0.0004],
                "full_circuit_changed": True, "ideal_circuit_equal": True,
                "dem_changed": str(baseline["dem"]) != str(changed["dem"]),
                "schema_equal": baseline["schema"] == changed["schema"],
                "observable_definition_equal": baseline["observables"] == changed["observables"]},
        "routing_change": {"lr_time": [5, 4],
                "circuit_changed": str(baseline["circuit"]) != str(runs["routing-change"]["circuit"]),
                "schema_before": baseline["schema"], "schema_after": runs["routing-change"]["schema"]},
        "baselines": compare({"circuit": old_payload}, {"circuit": new_payload}, tasks),
        "actual_source_reads": read_evidence(source, baseline["lines"]),
        "executed_source_lines": baseline["lines"],
        "read_detection_boundary": "AST global loads on executed lines; this is source-level evidence, not a complete interprocedural runtime read certificate",
        "cpp_reuse": native,
        "novel_guarantee_gap": False,
    })
    print("qecc actual circuit noise change: true; ideal circuit equal: true")
    print("qecc routing schema:", baseline["schema"], runs["routing-change"]["schema"])
    print("compiled engine:", native["status"])


if __name__ == "__main__":
    main()
