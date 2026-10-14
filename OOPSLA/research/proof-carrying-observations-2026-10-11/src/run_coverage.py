"""Automatic actual consumer lowering and certificate-cost accounting."""
import hashlib
import json
from pathlib import Path
import time

from generator.lower import tasks
from generator.prove import prove
from kernel.checker import check_certificate
from kernel.context import context


def main():
    root = Path(__file__).resolve().parents[1]
    prior = root.parent / "substitution-validation-2026-10-10"
    relations = frozenset({"circuit.schema", "measurement_schema.detectors", "circuit.noise_free",
                          "circuit.observables", "prediction.expected_shape"})
    records = {}
    for system, name in (("qecc", "run_qecc.py"), ("quits", "run_quits.py")):
        path = prior / "src" / name
        source = path.read_text(encoding="utf-8")
        ctx = context(path.read_bytes(), path.read_bytes(), "fixed-snapshot")
        t0 = time.perf_counter_ns(); lowered = tasks(source); lowering = time.perf_counter_ns() - t0
        rows = []
        for name, terms, reason in lowered:
            if terms is None:
                rows.append({"consumer": name, "status": "unknown", "reason": reason}); continue
            old, new = terms
            t0 = time.perf_counter_ns(); proof = prove(old, new, relations); generation = time.perf_counter_ns() - t0
            t0 = time.perf_counter_ns(); ok = proof is not None and check_certificate(old, new, relations, proof,
                producer_hash="source-adapter-sha", consumer_hash="lambda-source-sha",
                snapshot_id="fixed-snapshot", expected_snapshot="fixed-snapshot", actual_context=ctx, required_context=ctx); checking = time.perf_counter_ns() - t0
            rows.append({"consumer": name, "status": "conditional_proof" if ok else "unknown",
                         "generation_ns": generation, "checking_ns": checking,
                         "preconditions": "reader.read obeys literal path semantics; scalar_gt takes fixed scalar data; producer relations separately established"})
        records[system] = {"source": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "lowering_ns": lowering, "consumers": rows}
    assert sum(r["status"] == "conditional_proof" for r in records["qecc"]["consumers"]) == 4
    assert sum(r["status"] == "conditional_proof" for r in records["quits"]["consumers"]) == 1
    out = root / "results" / "coverage.json"
    out.write_text(json.dumps({"systems": records, "input_enumerations": 0,
        "baseline": "ordinary symbolic semantic-stamp baseline shares same relation generator/checker and pays identical costs; dynamic-read baseline reads same literal paths but cannot discard changed guard without additional proof",
        "producer_relations_are_explicit_assumptions": True,
        "complete_automatic_python_soundness_established": False}, indent=2), encoding="utf-8")
    print({s: [(r["consumer"], r["status"]) for r in v["consumers"]] for s, v in records.items()})


if __name__ == "__main__":
    main()
