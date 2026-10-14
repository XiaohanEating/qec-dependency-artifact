"""Restricted producer plan; no general Python-to-proof translation claim."""
from collections import Counter
import numpy as np
from .model import Bundle


def lossless_dem_bundle(dem):
    """Fold identical full responses, preserving distinct logical labels.

    An error instruction is one independent Bernoulli variable, including
    separator-correlated components. Repeated target IDs cancel modulo two.
    Identical (detector, logical) responses combine by XOR probability.
    """
    rows = {}
    for instruction in dem.flattened():
        if instruction.type in ('detector', 'logical_observable'):
            continue
        if instruction.type != 'error':
            raise ValueError('unsupported flattened instruction')
        detectors, logicals = [], []
        for target in instruction.targets_copy():
            if target.is_relative_detector_id():
                detectors.append(target.val)
            elif target.is_logical_observable_id():
                logicals.append(target.val)
            elif not target.is_separator():
                raise ValueError('unsupported target')
        key = (tuple(sorted(k for k, n in Counter(detectors).items() if n % 2)),
               tuple(sorted(k for k, n in Counter(logicals).items() if n % 2)))
        p = float(instruction.args_copy()[0])
        if not np.isfinite(p) or not 0 < p < 0.5:
            raise ValueError('probability outside supported domain (0, .5)')
        if not key[0] and not key[1]:
            continue  # Identity response affects no requested observation.
        q = rows.get(key, 0.0)
        rows[key] = q * (1 - p) + p * (1 - q)
    h = np.zeros((dem.num_detectors, len(rows)), dtype=np.uint8)
    logical = np.zeros((dem.num_observables, len(rows)), dtype=np.uint8)
    for column, (detectors, observables) in enumerate(rows):
        h[list(detectors), column] = 1
        logical[list(observables), column] = 1
    return Bundle(h, logical, np.array(list(rows.values()), dtype=np.float64))


def execute_plan(old, plan):
    """Generate new artifact and untrusted evidence from an explicit plan."""
    if 'steps' in plan:
        permutation = np.arange(old.priors.size)
        for step in plan['steps']:
            if step.get('operation') != 'reindex-fault-columns':
                raise ValueError('unsupported producer operation')
            p = step['permutation']
            if len(p) != old.priors.size or sorted(p) != list(range(old.priors.size)):
                raise ValueError('step is not a bijection')
            permutation = permutation[p]
        permutation = permutation.tolist()
    else:
        permutation = plan['permutation']
    new = old.reindex(permutation)
    certificate = {'schema': 'fault-column-permutation-v1',
                   'old': old.fingerprint, 'new': new.fingerprint,
                   'permutation': list(permutation),
                   'transported_fields': list(plan.get('fields', ('h', 'logical', 'priors')))}
    return new, certificate
