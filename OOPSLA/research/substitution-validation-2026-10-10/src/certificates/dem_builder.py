"""Trusted constructor for probability-only DEM replacement.

The immutable payload and opaque structure identity are produced together.
Identity is process-local provenance, not a signature or an adversarial seal.
"""
from dataclasses import dataclass
import math

import numpy as np
import stim


@dataclass(frozen=True)
class Payload:
    text: str
    rows: tuple
    column_ids: tuple
    structure_identity: object
    priors: tuple
    bounded_priors: bool


def from_dem(dem):
    rows, ids, groups, priors = [], [], {}, []
    bound = True
    for inst in dem.flattened():
        targets, args = tuple(inst.targets_copy()), tuple(inst.args_copy())
        rows.append((inst.type, args, targets))
        if inst.type == "error":
            p = args[0]
            key = frozenset(t.val for t in targets if t.is_relative_detector_id())
            if key not in groups:
                groups[key] = len(groups)
                priors.append(0.0)
            col = groups[key]
            priors[col] = priors[col] * (1 - p) + p * (1 - priors[col])
            ids.append(col)
            bound &= 0 < p < 0.5
        else:
            ids.append(-1)
            if inst.type not in {"detector", "logical_observable"}:
                raise ValueError(inst.type)
    return Payload(str(dem.flattened()), tuple(rows), tuple(ids), object(), tuple(priors), bool(bound))


def rescale(payload, factor):
    """O(n) mandatory production; no post-production matrix/cert scan."""
    if not payload.bounded_priors or not math.isfinite(factor) or not 0 < factor <= 1:
        raise ValueError("Expected positive sub-half source probabilities and factor in (0,1]")
    dem, rows = stim.DetectorErrorModel(), []
    priors = [0.0] * len(payload.priors)
    for (kind, args, targets), col in zip(payload.rows, payload.column_ids):
        if kind == "error":
            # Stim's textual artifact uses 16 significant digits. Merge the
            # serialized value, not a hidden higher-precision intermediate.
            p = float(format(args[0] * factor, ".16g"))
            # IEEE underflow would violate the real-arithmetic proof.
            if not 0 < p < 0.5:
                raise ValueError("Probability underflow or invalid range")
            args = (p,)
            priors[col] = priors[col] * (1 - p) + p * (1 - priors[col])
            if not 0 < priors[col] < 0.5:
                raise ValueError("Rounded merged prior violates proof domain")
        dem.append(kind, args, targets)
        rows.append((kind, args, targets))
    return Payload(str(dem), tuple(rows), payload.column_ids,
                   payload.structure_identity, tuple(priors), True)


def reusable(old, new):
    return old.structure_identity is new.structure_identity


def priors(payload):
    return np.array(payload.priors)
