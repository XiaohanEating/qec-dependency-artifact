"""Immutable checked context, supplied by caller-owned current state."""
from dataclasses import dataclass
import hashlib


@dataclass(frozen=True)
class Context:
    producer_sha256: str
    consumer_sha256: str
    snapshot_id: str
    immutable: bool
    type_contract: str


def valid_context(actual, required):
    if not isinstance(actual, Context) or not isinstance(required, Context):
        return False
    return (actual == required and actual.immutable and actual.type_contract == "pure-total-ir-v1"
            and len(actual.producer_sha256) == len(actual.consumer_sha256) == 64
            and all(c in "0123456789abcdef" for c in actual.producer_sha256 + actual.consumer_sha256)
            and bool(actual.snapshot_id))


def context(producer_bytes, consumer_bytes, snapshot_id):
    return Context(hashlib.sha256(producer_bytes).hexdigest(), hashlib.sha256(consumer_bytes).hexdigest(),
                   snapshot_id, True, "pure-total-ir-v1")
