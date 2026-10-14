"""Check a strictly weaker observation using saved real decoder outputs.

Certificate extraction is counted as a complete array scan; this script does
not attribute that work to a free certificate or claim a speed improvement.
"""
import numpy as np

from common import ROOT, environment, file_hash, write_json


def schema_projection(values):
    return (values.shape, bool(np.all((values == 0) | (values == 1))))


def main():
    source = ROOT / "results" / "quits" / "decoder-evidence.npz"
    with np.load(source, allow_pickle=False) as data:
        old, new = data["bp_osd"], data["bp_lsd"]
        old_projection, new_projection = schema_projection(old), schema_projection(new)
        expected = (len(data["detectors"]), len(data["lz"]))
        old_contract = old_projection == (expected, True)
        new_contract = new_projection == (expected, True)
        assert not np.array_equal(old, new)
        assert old_projection == new_projection
        assert old_contract and new_contract
        evidence = {
            "environment": environment(), "source": str(source),
            "source_sha256": file_hash(source), "field_values_equal": False,
            "old_projection": old_projection, "new_projection": new_projection,
            "projection_equal": True, "contract_equal": old_contract == new_contract,
            "differing_bits": int(np.count_nonzero(old != new)),
            "strictly_weaker_than_field_equality_witness": True,
            "certificate_extraction": {
                "old_array_elements_scanned": old.size,
                "new_array_elements_scanned": new.size,
                "new_contract_evaluations_saved_after_certificate": 1,
                "complete_new_array_scans_saved": 0,
            },
            "algorithm_speed_advantage_established": False,
            "scope": "schema predicate factors exactly through shape and binary-validity; logical correctness and accuracy are outside this observation",
        }
    write_json(ROOT / "results" / "property-projection.json", evidence)
    print("Values differ; shape/binary observation and interface contract agree.")
    print("Full new-array scans saved: 0.")


if __name__ == "__main__":
    main()
