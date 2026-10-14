"""Constructive DEM structure certificate from the producer's event stream."""
import hashlib
import json
import time
from pathlib import Path

import stim

from common import ROOT, environment, file_hash, write_json


def structural_certificate(dem):
    """Certificate omits probabilities and retains instruction kind/targets."""
    rows = []
    for instruction in dem.flattened():
        if instruction.type == "error":
            targets = tuple(("D", t.val) if t.is_relative_detector_id() else
                            ("L", t.val) if t.is_logical_observable_id() else
                            ("other", str(t)) for t in instruction.targets_copy())
            rows.append((instruction.type, targets))
        elif instruction.type in {"detector", "logical_observable"}:
            rows.append((instruction.type, tuple(str(t) for t in instruction.targets_copy())))
        else:
            raise ValueError(instruction.type)
    raw = repr(tuple(rows)).encode("utf-8")
    return {"sha256": hashlib.sha256(raw).hexdigest(), "rows": len(rows),
            "targets": sum(len(r[1]) for r in rows), "certificate_bytes": len(raw)}


def main():
    paths = {name: ROOT / "results" / "quits" / (name + ".dem") for name in ("normal", "lower")}
    records = {}
    for name, path in paths.items():
        dem = stim.DetectorErrorModel(path.read_text(encoding="utf-8"))
        t0 = time.perf_counter_ns(); cert = structural_certificate(dem); cert_ns = time.perf_counter_ns() - t0
        # Strong baseline reads probabilities as well and computes a separate digest.
        t1 = time.perf_counter_ns()
        full = [(str(i.type), tuple(str(t) for t in i.targets_copy()), tuple(i.args_copy()))
                for i in dem.flattened()]
        full_ns = time.perf_counter_ns() - t1
        records[name] = {"file": str(path), "file_sha256": file_hash(path),
                         "structural": cert, "full_rows": len(full),
                         "structural_certificate_ns": cert_ns, "full_snapshot_ns": full_ns}
    equal = records["normal"]["structural"]["sha256"] == records["lower"]["structural"]["sha256"]
    assert equal
    evidence = {"environment": environment(), "records": records,
                "structural_certificate_equal": equal,
                "full_artifacts_equal": records["normal"]["file_sha256"] == records["lower"]["file_sha256"],
                "property": "DEM target structure and instruction kinds are invariant while probabilities may vary",
                "proof_condition": "producer emits identical flattened instruction kinds/targets; probability arguments are not branch predicates or target generators",
                "strong_baseline": "full DEM snapshot including probabilities; same structural projection and ordinary cache",
                "algorithmic_speedup_claimed": False}
    write_json(ROOT / "results" / "dem-structure-certificate.json", evidence)
    print(json.dumps({"structural_certificate_equal": equal,
                      "full_artifacts_equal": evidence["full_artifacts_equal"],
                      "normal": records["normal"]["structural"],
                      "lower": records["lower"]["structural"]}, indent=2))


if __name__ == "__main__":
    main()
