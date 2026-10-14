"""Actual source analysis, replacement proof attempts, and failing witnesses."""
import inspect
import time
import contextlib
import io

import stim

from quits.decoder import base

from certificates.source_flow import Flow, Unsupported
from common import ROOT, digest, environment, file_hash, write_json


def analyze(source):
    start = time.perf_counter_ns()
    try:
        result = Flow(source).analyze()
        result["accepted"] = result["probability_independent_structure"]
    except Unsupported as error:
        result = {"accepted": False, "unsupported": str(error)}
    result["analysis_ns"] = time.perf_counter_ns() - start
    return result


def main():
    original = inspect.getsource(base)
    cases = {
        "real_quits": original,
        "branch_probability": original.replace("if dets not in dem_dict:", "if prob > 0.001 and dets not in dem_dict:"),
        "alias_probability": original.replace("dets = frozenset(detectors)", "alias = dem_dict\n        alias[frozenset(detectors)] = prob\n        dets = frozenset(detectors)"),
        "cross_procedure_probability": original.replace("dets = frozenset(detectors)", "dets = leak(prob, detectors)") + "\n\ndef leak(prob, detectors):\n    return frozenset(detectors) if prob > 0.001 else frozenset()\n",
        "unmodeled_dynamic_call": original.replace("dets = frozenset(detectors)", "dets = external_callback(detectors)"),
        "equivalent_helper_alias": original.replace("dets = frozenset(detectors)", "same_detectors = detectors\n        dets = copy_targets(same_detectors)") + "\n\ndef copy_targets(items):\n    return frozenset(items)\n",
    }
    results = {name: analyze(source) for name, source in cases.items()}
    print({name: result["accepted"] for name, result in results.items()})
    assert results["real_quits"]["accepted"], results["real_quits"]
    assert results["equivalent_helper_alias"]["accepted"], results["equivalent_helper_alias"]
    assert not any(results[n]["accepted"] for n in ("branch_probability", "alias_probability", "cross_procedure_probability", "unmodeled_dynamic_call"))
    namespace = {"__name__": "equivalent_replacement"}
    exec(compile(cases["equivalent_helper_alias"], "<replacement>", "exec"), namespace)
    real_dem = stim.DetectorErrorModel((ROOT / "results" / "quits" / "normal.dem").read_text(encoding="utf-8"))
    t0 = time.perf_counter_ns()
    with contextlib.redirect_stdout(io.StringIO()):
        before = base.detector_error_model_to_matrix(real_dem)
        after = namespace["detector_error_model_to_matrix"](real_dem)
    replay_ns = time.perf_counter_ns() - t0
    assert all(digest(a) == digest(b) for a, b in zip(before, after))
    write_json(ROOT / "results" / "source-certificate.json", {
        "environment": environment(), "source": inspect.getfile(base),
        "source_sha256": file_hash(inspect.getfile(base)), "cases": results,
        "domain_enumerations": 0, "upstream_artifact_enumerations": 0,
        "equivalent_source_replacement_real_replay_equal": True,
        "validation_replay_ns": replay_ns,
        "source_replacement_proof": "helper maps input detector list to frozenset exactly; local alias preserves object identity; remaining syntax unchanged",
        "strong_baseline": "same cached source summary keyed by complete source version; proof checker and ordinary semantic cache share identical proof cost and zero domain enumerations",
        "scope": "Restricted abstract interpretation; source proof obligations are conditional on whitelisted operation summaries. Not machine-verified Python semantics.",
        "independent_algorithm_novelty": False,
    })
    out = ROOT / "provenance" / "source-witnesses"
    out.mkdir(parents=True, exist_ok=True)
    for name, source in cases.items():
        (out / (name + ".py")).write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
