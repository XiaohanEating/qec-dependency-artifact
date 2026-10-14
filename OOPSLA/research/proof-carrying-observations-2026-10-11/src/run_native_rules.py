"""Native QUITS and independent qecc relation checks and actual executions."""
import ast
import hashlib
import inspect
import json
from pathlib import Path
import time

import numpy as np
from quits.decoder import base

from kernel.native_rules import check_native_rule, probability_identity


def main():
    root = Path(__file__).resolve().parents[1]
    workspace = root.parents[2]
    qecc = workspace / "third_party" / "qecc_routing-4ef18121c39492414b85ff36b3a61c83f9ebf95f" / "src_py" / "bivariate-bicycle" / "general.py"
    source = qecc.read_text(encoding="utf-8")
    quits_source = inspect.getsource(base)
    t0 = time.perf_counter_ns(); qproof = check_native_rule(quits_source, "handle_error", "ordered_first_label_xor_fold"); qcost = time.perf_counter_ns()-t0
    t0 = time.perf_counter_ns(); eproof = check_native_rule(source, "commute", "mod_two_bilinear"); ecost = time.perf_counter_ns()-t0
    assert qproof["accepted"] and eproof["accepted"] and probability_identity()
    # Execute the original independent-system function unchanged. Actual code
    # arrays are derived by executing its initial definitions through Hx/Hz.
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "commute")
    setup = source[:source.index("GF = galois.GF(2)")]
    # Avoid unrelated optional imports: retain only original assignments and
    # cyclic_shift_matrix plus explicit matched NumPy bindings.
    initial = ast.parse(setup)
    nodes = [n for n in initial.body if isinstance(n, (ast.Assign, ast.FunctionDef))
             and not (isinstance(n, ast.Assign) and any(isinstance(t,ast.Name) and t.id in {"full_path","path","filename"} for t in ast.walk(n) if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)))]
    ns = {"np": np, "matrix_power": np.linalg.matrix_power}
    exec(compile(ast.fix_missing_locations(ast.Module(nodes, [])), str(qecc), "exec"), ns)
    exec(compile(ast.fix_missing_locations(ast.Module([fn], [])), str(qecc), "exec"), ns)
    h = ns["Hx"]
    n = h.shape[1]
    x = np.concatenate((h[0], np.zeros(n, dtype=int)))
    z = np.concatenate((np.zeros(n, dtype=int), ns["Hz"][0]))
    xp, zp = x + 2, z + 4
    old, new = ns["commute"](x,z,n), ns["commute"](xp,zp,n)
    assert np.array_equal(old,new) and not np.array_equal(x,xp)
    mutated_q = quits_source.replace("dets = frozenset(detectors)", "dets = frozenset(detectors) if prob > 0.001 else frozenset()")
    mutated_e = source.replace("return (x1 @ z2 % 2) ^ (x2 @ z1 % 2)", "return (x1 @ z2 % 3) ^ (x2 @ z1 % 3)")
    rejects = {"probability_control": not check_native_rule(mutated_q,"handle_error","ordered_first_label_xor_fold")["accepted"],
               "wrong_modulus": not check_native_rule(mutated_e,"commute","mod_two_bilinear")["accepted"]}
    assert all(rejects.values())
    data = {"quits": {"proof": qproof, "generation_check_ns": qcost, "source_sha256": hashlib.sha256(quits_source.encode()).hexdigest()},
            "qecc": {"proof": eproof, "generation_check_ns": ecost,"source_sha256":hashlib.sha256(qecc.read_bytes()).hexdigest(),
                     "native_function": "commute", "actual_Hx_shape":h.shape,"actual_output_equal":bool(np.array_equal(old,new)),
                     "actual_input_changed":True,"old_output":int(old),"new_output":int(new)},
            "rejections":rejects,"polynomial_identity_checked":True,"input_enumerations":0,
            "source_to_rule": "exact AST rule recognition; not a generic Python prover",
            "producer_relation": "event target/order identity or modulo-two input relation still separately established",
            "novel_general_rule_established":False}
    (root/"results"/"native-rules.json").write_text(json.dumps(data,indent=2),encoding="utf-8")
    print({"quits_rule":qproof["accepted"],"qecc_native_rule":eproof["accepted"],"native_equal":bool(np.array_equal(old,new)),"rejects":rejects})


if __name__ == "__main__":
    main()
