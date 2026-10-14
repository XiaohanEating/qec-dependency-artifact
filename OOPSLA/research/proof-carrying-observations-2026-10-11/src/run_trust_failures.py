"""Reject stale snapshots, missing premises, and type/binding claims."""
from kernel.checker import check_certificate, Step
from kernel.terms import field
from kernel.context import context
from dataclasses import replace
import json
from pathlib import Path


def main():
    old, new = field("schema", "old"), field("schema", "new")
    proof = Step("relation", new, old)
    rel = frozenset({"schema"})
    good = context(b"producer", b"consumer", "current")
    options = dict(producer_hash="p", consumer_hash="c", snapshot_id="s", expected_snapshot="s",
                   required_context=good)
    cases = {
        "missing_producer_hash": check_certificate(old, new, rel, proof, consumer_hash="c", snapshot_id="s", expected_snapshot="s"),
        "missing_consumer_hash": check_certificate(old, new, rel, proof, producer_hash="p", snapshot_id="s", expected_snapshot="s"),
        "stale_snapshot": check_certificate(old, new, rel, proof, producer_hash="p", consumer_hash="c", snapshot_id="old", expected_snapshot="new"),
        "missing_relation": check_certificate(old, new, frozenset(), proof, producer_hash="p", consumer_hash="c", snapshot_id="s", expected_snapshot="s"),
    }
    cases.update({
        "binding_hash_changed": check_certificate(old, new, rel, proof, actual_context=context(b"producer", b"other", "current"), **options),
        "wrong_type": check_certificate(old, new, rel, proof, actual_context=replace(good, type_contract="mutable-python"), **options),
        "alias_mutation": check_certificate(old, new, rel, proof, actual_context=replace(good, immutable=False), **options),
        "snapshot_changed": check_certificate(old, new, rel, proof, actual_context=replace(good, snapshot_id="old"), **options),
    })
    assert not any(cases.values())
    print("Context mismatches rejected; truth of caller-owned runtime context remains a premise.")
    out = Path(__file__).resolve().parents[1] / "results" / "trust-failures.json"
    out.write_text(json.dumps(cases, indent=2), encoding="utf-8")
    print(cases)


if __name__ == "__main__":
    main()
