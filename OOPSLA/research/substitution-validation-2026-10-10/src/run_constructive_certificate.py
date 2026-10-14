"""End-to-end probability replacement, real converter oracle, strong baselines."""
import contextlib
import inspect
import io
import statistics
import time

import numpy as np
import stim
from quits.decoder import base

from certificates.dem_builder import from_dem, priors, rescale, reusable
from certificates.source_flow import Flow
from common import ROOT, digest, environment, file_hash, write_json
from run_dem_certificate import structural_certificate


def real_convert(text, function=base.detector_error_model_to_matrix):
    with contextlib.redirect_stdout(io.StringIO()):
        return function(stim.DetectorErrorModel(text))


def main():
    source = ROOT / "results" / "quits" / "normal.dem"
    old_dem = stim.DetectorErrorModel(source.read_text(encoding="utf-8"))
    t0 = time.perf_counter_ns(); old = from_dem(old_dem); initialization_ns = time.perf_counter_ns() - t0
    t0 = time.perf_counter_ns(); proof = Flow(inspect.getsource(base)).analyze(); analysis_ns = time.perf_counter_ns() - t0
    assert proof["probability_independent_structure"]
    old_values = real_convert(old.text)
    assert np.array_equal(old_values[2], priors(old))
    new = rescale(old, 0.2)
    fresh = real_convert(new.text)
    assert reusable(old, new)
    assert digest(old_values[0]) == digest(fresh[0])
    assert digest(old_values[1]) == digest(fresh[1])
    assert np.array_equal(fresh[2], priors(new))
    assert not np.array_equal(old_values[2], fresh[2])
    assert np.all((fresh[2] > 0) & (fresh[2] < 0.5))
    modes = ("full_recompute", "field_snapshot", "semantic_projection_scan",
             "semantic_certificate_cache", "proposed_constructive")
    timings = {}
    for mode in modes:
        samples = []
        for _ in range(9):
            start = time.perf_counter_ns()
            replacement = rescale(old, 0.2)
            if mode in {"full_recompute", "field_snapshot"}:
                values = real_convert(replacement.text)
                if mode == "field_snapshot":
                    assert digest(values[0]) == digest(old_values[0])
                    assert digest(values[1]) == digest(old_values[1])
                assert bool(np.all((values[2] > 0) & (values[2] < 0.5)))
            elif mode == "semantic_projection_scan":
                assert structural_certificate(stim.DetectorErrorModel(replacement.text)) == structural_certificate(old_dem)
                values = old_values[0], old_values[1], priors(replacement)
                assert bool(np.all((values[2] > 0) & (values[2] < 0.5)))
            else:
                assert reusable(old, replacement) and replacement.bounded_priors
                values = old_values[0], old_values[1], priors(replacement)
            samples.append(time.perf_counter_ns() - start)
        timings[mode] = {"samples_ns": samples, "median_ns": statistics.median(samples),
                         "includes_replacement_production": True,
                         "matrix_conversion_runs": int(mode in {"full_recompute", "field_snapshot"}),
                         "postproduction_dem_scans": int(mode in {"full_recompute", "field_snapshot"}) + 2 * int(mode == "semantic_projection_scan")}
    # Real executable failure witness: a probability controls target creation.
    modified = inspect.getsource(base).replace("dets = frozenset(detectors)",
                         "dets = frozenset(detectors) if prob > 0.001 else frozenset()")
    namespace = {"__name__": "probability_structural_failure"}
    exec(compile(modified, "<failure-witness>", "exec"), namespace)
    bad_old = real_convert(old.text, namespace["detector_error_model_to_matrix"])
    bad_new = real_convert(new.text, namespace["detector_error_model_to_matrix"])
    structure_changes = digest(bad_old[0]) != digest(bad_new[0])
    assert structure_changes
    rejected = []
    for factor in (0, -1, float("nan"), 2):
        try:
            rescale(old, factor)
        except ValueError:
            rejected.append(str(factor))
    assert len(rejected) == 4
    out = ROOT / "results" / "constructive-dem"
    out.mkdir(exist_ok=True)
    (out / "rescaled.dem").write_text(new.text, encoding="utf-8")
    np.savez_compressed(out / "evidence.npz", old_priors=old_values[2], new_priors=fresh[2],
                        old_h=old_values[0].toarray(), new_h=fresh[0].toarray(),
                        old_l=old_values[1].toarray(), new_l=fresh[1].toarray())
    write_json(out / "comparison.json", {
        "environment": environment(), "source_dem_sha256": file_hash(source),
        "converter_sha256": file_hash(inspect.getfile(base)),
        "initial_certificate_construction_ns": initialization_ns, "initial_source_analysis_ns": analysis_ns,
        "instruction_rows": len(old.rows), "fault_columns": len(old.priors),
        "real_dem_probabilities_changed": old.text != new.text,
        "real_check_matrix_equal": True, "real_observable_matrix_equal": True,
        "real_priors_changed": True, "new_priors_in_open_zero_half": True,
        "new_dem_postproduction_certificate_scans": 0,
        "construction_condition_checks": sum(col >= 0 for col in new.column_ids),
        "failing_probability_branch_changes_real_matrix": structure_changes,
        "rejected_factors": rejected, "timings": timings,
        "strong_baseline_same_certificate": True,
        "independent_algorithm_advantage_over_same_certificate_baseline": False,
        "trust_boundary": "Immutable records and constructor provenance; Python code can forge Payload objects, so arbitrary/untrusted replacements must use full validation. No cryptographic or hostile-code guarantee.",
    })
    print("Real probabilities differ; H and L agree; priors agree with full converter.")
    print({m: round(v["median_ns"] / 1e6, 3) for m, v in timings.items()})


if __name__ == "__main__":
    main()
