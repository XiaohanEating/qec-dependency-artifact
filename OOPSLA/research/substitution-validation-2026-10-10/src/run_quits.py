"""Real QUITS behavior changes and fair field-aware dependency baselines."""
import contextlib
import io
import sys
from pathlib import Path

import numpy as np
import quits
from quits import ErrorModel
from quits.decoder import detector_error_model_to_matrix
from quits.decoder.base import spacetime
from quits.decoder import sliding_window_bposd_circuit_mem, sliding_window_bplsd_circuit_mem
from quits.qldpc_code import BbCode
from quits.simulation import get_stim_mem_result

from common import ROOT, digest, environment, file_hash, write_json
from dependency_engine import Task, compare

NORMAL = dict(idle_error=1e-4, sqgate_error=1e-3, tqgate_error=1e-3, spam_error=1e-3)
LOWER = dict(idle_error=2e-5, sqgate_error=2e-4, tqgate_error=2e-4, spam_error=2e-4)
STRESS = dict(idle_error=3e-3, sqgate_error=3e-2, tqgate_error=3e-2, spam_error=3e-2)


def build(code, params):
    return code.build_circuit("zxcoloration", error_model=ErrorModel(**params),
                              num_rounds=2, basis="Z")


def window_bundle(circuit, code):
    h, logical, prior, update = spacetime(circuit, code.hz, 3, 1, 1)
    return {"checks": h, "observables": logical, "priors": prior, "updates": update}


def positive_priors(reader):
    return bool(all(np.all((v > 0) & (v < 0.5)) for v in reader.read("windows", "priors")))


def transport(reader):
    # This is the actual window_update linear map used at sliding_window.py:169.
    matrices = reader.read("windows", "updates")
    return {"shape": tuple(m.shape for m in matrices),
            "maps": tuple(m.toarray() for m in matrices)}


def transport_contract(reader):
    maps = reader.read("transport", "maps")
    return all(np.all((m == 0) | (m == 1)) for m in maps)


def prediction_schema(reader):
    prediction = reader.read("prediction", "values")
    dimensions = reader.read("prediction", "expected_shape")
    return bool(prediction.shape == dimensions and np.all((prediction == 0) | (prediction == 1)))


def main():
    out = ROOT / "results" / "quits"
    out.mkdir(parents=True, exist_ok=True)
    code = BbCode(l=6, m=6, A_x_pows=[3], A_y_pows=[1, 2], B_x_pows=[1, 2], B_y_pows=[3])
    normal, lower, stress = [build(code, params) for params in (NORMAL, LOWER, STRESS)]
    circuits = {"normal": normal, "lower": lower, "stress": stress}
    for name, circuit in circuits.items():
        (out / (name + ".stim")).write_text(str(circuit), encoding="utf-8")
        (out / (name + ".dem")).write_text(str(circuit.detector_error_model()), encoding="utf-8")
    old, new = window_bundle(normal, code), window_bundle(lower, code)
    np.savez_compressed(out / "noise-window-evidence.npz",
                        **{f"{prefix}_{field}_{i}": m.toarray() if hasattr(m, "toarray") else m
                           for prefix, bundle in (("old", old), ("new", new))
                           for field, matrices in bundle.items() for i, m in enumerate(matrices)})
    noise_comparison = {
        "circuit_changed": str(normal) != str(lower),
        "dem_changed": str(normal.detector_error_model()) != str(lower.detector_error_model()),
        "complete_window_artifact_changed": digest(old) != digest(new),
        "field_equal": {field: digest(old[field]) == digest(new[field]) for field in old},
        "old_field_hash": {field: digest(old[field]) for field in old},
        "new_field_hash": {field: digest(new[field]) for field in new},
    }
    assert noise_comparison["complete_window_artifact_changed"]
    assert noise_comparison["field_equal"]["updates"]
    assert noise_comparison["field_equal"]["checks"]
    assert not noise_comparison["field_equal"]["priors"]
    tasks = [Task("transport", transport),
             Task("transport_contract", transport_contract, True),
             Task("prior_contract", positive_priors, True)]
    noise_comparison["baselines"] = compare({"windows": old}, {"windows": new}, tasks)
    det, obs = get_stim_mem_result(stress, 128, seed=7)
    with contextlib.redirect_stdout(io.StringIO()):
        osd = sliding_window_bposd_circuit_mem(det.copy(), stress, code.hz, code.lz, W=3, F=1)
        lsd = sliding_window_bplsd_circuit_mem(det.copy(), stress, code.hz, code.lz, W=3, F=1)
    np.savez_compressed(out / "decoder-evidence.npz", detectors=det, observables=obs,
                        bp_osd=osd, bp_lsd=lsd, hz=code.hz, lz=code.lz)
    changed_bits = int(np.count_nonzero(osd != lsd))
    decoder_comparison = {
        "operating_point": STRESS, "shots": 128, "sampler_seed": 7,
        "predictions_changed": changed_bits > 0, "differing_bits": changed_bits,
        "differing_shots": int(np.count_nonzero(np.any(osd != lsd, axis=1))),
        "old_hash": digest(osd), "new_hash": digest(lsd),
        "consumer_contract": "binary array with shape (nshots, number of logical observables)",
        "logical_accuracy_preserved": "not claimed",
        "old_schema_valid": osd.shape == (128, code.lz.shape[0]) and bool(np.all((osd == 0) | (osd == 1))),
        "new_schema_valid": lsd.shape == (128, code.lz.shape[0]) and bool(np.all((lsd == 0) | (lsd == 1))),
    }
    assert changed_bits > 0
    old_prediction = {"values": osd, "expected_shape": (128, code.lz.shape[0])}
    new_prediction = {"values": lsd, "expected_shape": (128, code.lz.shape[0])}
    decoder_tasks = [Task("schema_contract", prediction_schema, True),
                     Task("dimensions", lambda r: r.read("prediction", "expected_shape"))]
    decoder_comparison["baselines"] = compare({"prediction": old_prediction},
                                               {"prediction": new_prediction}, decoder_tasks)
    sources = Path(quits.__file__).resolve().parent
    evidence = {
        "environment": environment(), "quits_file": str(quits.__file__),
        "source_hashes": {str(p): file_hash(p) for p in (sources / "decoder" / "base.py",
                                                         sources / "decoder" / "sliding_window.py")},
        "noise": noise_comparison, "decoder": decoder_comparison,
        "generation_cost_accounting": {"code_constructions": 1, "circuit_constructions": 3,
                                        "window_bundle_constructions": 2, "decoder_executions": 2,
                                        "note": "These real production calls precede every baseline; comparison counts concern downstream consumers and contracts only."},
        "read_provenance": [
            {"consumer": "window slices", "source": "decoder/base.py:152-202", "fields": ["checks", "observables", "priors", "updates"], "method": "actual upstream spacetime return values"},
            {"consumer": "syndrome transport", "source": "decoder/sliding_window.py:169", "fields": ["updates"], "method": "study adapter observes actual upstream linear maps; downstream application is represented by transport task"},
            {"consumer": "prediction schema", "source": "decoder/sliding_window.py:149-189", "fields": ["shape", "binary values"], "method": "study contract for source-documented output interface"},
        ],
        "novel_algorithm_advantage": False,
        "reason": "Field-aware incremental tracking and tracked ordinary contracts execute exactly the same nodes as proposed projections."
    }
    write_json(out / "comparison.json", evidence)
    print("noise fields:", noise_comparison["field_equal"])
    print("decoder differing bits:", changed_bits)
    print("noise baseline runs:", [(r["mode"], r["producer_runs"], r["contract_runs"]) for r in noise_comparison["baselines"]])


if __name__ == "__main__":
    main()
