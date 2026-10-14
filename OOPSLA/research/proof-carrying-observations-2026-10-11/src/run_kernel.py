"""Unbounded symbolic relation certificates with forged-proof witnesses."""
import json
from pathlib import Path
import time

from generator.prove import prove
from kernel.checker import Step, check_certificate
from kernel.context import context
from kernel.terms import Term, call, constant, field, select


def main():
    rel = frozenset({"updates", "schema", "noise_free", "observables"})
    ctx = context(b"builder", b"consumer", "snapshot-1")
    cases = {
        "quits_transport": (call("transport", field("updates", "old")),
                             call("transport", field("updates", "new"))),
        "qecc_schema": (call("schema", field("schema", "old")),
                         call("schema", field("schema", "new"))),
        "qecc_ideal": (call("ideal", field("noise_free", "old")),
                        call("ideal", field("noise_free", "new"))),
        "changed_priors": (call("prior_check", field("priors", "old")),
                            call("prior_check", field("priors", "new"))),
        "equal_branch_refactor": (call("schema", field("schema", "old")),
                                   select(field("priors", "new"),
                                          call("schema", field("schema", "new")),
                                          call("schema", field("schema", "new")))),
    }
    records = {}
    for name, (old, new) in cases.items():
        t0 = time.perf_counter_ns(); proof = prove(old, new, rel); generation = time.perf_counter_ns() - t0
        t0 = time.perf_counter_ns(); ok = proof is not None and check_certificate(old, new, rel, proof,
            producer_hash="fixed-builder-sha", consumer_hash="fixed-consumer-sha",
            snapshot_id="snapshot-1", expected_snapshot="snapshot-1", actual_context=ctx, required_context=ctx); checking = time.perf_counter_ns() - t0
        records[name] = {"accepted": ok, "generation_ns": generation, "checking_ns": checking,
                         "input_enumerations": 0}
    assert all(records[n]["accepted"] for n in cases if n != "changed_priors")
    assert not records["changed_priors"]["accepted"]
    old, new = cases["changed_priors"]
    assert not check_certificate(old, new, rel, Step("refl", new, old), producer_hash="p", consumer_hash="c", snapshot_id="s", expected_snapshot="s")
    forbidden = Step("relation", field("priors", "new"), field("priors", "old"))
    assert not check_certificate(forbidden.after, forbidden.before, rel, forbidden, producer_hash="p", consumer_hash="c", snapshot_id="s", expected_snapshot="s")
    out = Path(__file__).resolve().parents[1] / "results"
    out.mkdir(exist_ok=True)
    (out / "kernel.json").write_text(json.dumps({"cases": records, "forged_proofs_rejected": 2,
        "scope": "unbounded total pure first-order terms under explicit producer field relations",
        "python_translation_validated": False, "producer_relations_automatically_proved": False,
        "real_data_mapping": "QUITS updates and qecc schema/noise_free names correspond to prior saved real evidence; these terms are adapters, not automatic translation"}, indent=2), encoding="utf-8")
    print(records)


if __name__ == "__main__":
    main()
