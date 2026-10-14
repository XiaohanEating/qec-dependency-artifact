"""Same-artifact, same-relation baselines, including strong projected stamps."""
import numpy as np
from .model import Bundle, array_digest, validate_fault_input


def ordinary_relational_assertion(old, new, permutation):
    n = old.priors.size
    return (len(permutation) == n and sorted(permutation) == list(range(n))
            and np.array_equal(new.h, old.h[:, permutation])
            and np.array_equal(new.logical, old.logical[:, permutation])
            and np.array_equal(new.priors, old.priors[permutation]))


def canonical_semantic_stamp(bundle, permutation):
    canonical = bundle.reindex(np.argsort(permutation))
    return tuple(array_digest(a) for a in (canonical.h, canonical.logical, canonical.priors))


def canonical_projection_equal(old, new, permutation):
    canonical = new.reindex(np.argsort(permutation))
    return (np.array_equal(old.h, canonical.h) and np.array_equal(old.logical, canonical.logical)
            and np.array_equal(old.priors, canonical.priors))


def full_boundary_relational_assertion(old, new, certificate, old_faults, new_faults):
    """Ordinary predicate with the same value/domain/binding obligations.

    Shares no relation-checker implementation. Consumer source translation is
    common infrastructure and separately timed, not counted as an advantage.
    """
    try:
        if type(old) is not Bundle or type(new) is not Bundle:
            return False
        if not old.valid() or not new.valid() or certificate['schema'] != 'fault-column-permutation-v1':
            return False
        if certificate['old'] != old.fingerprint or certificate['new'] != new.fingerprint:
            return False
        if certificate['transported_fields'] != ['h', 'logical', 'priors']:
            return False
        p = certificate['permutation']
        if not isinstance(p, list) or any(type(x) is not int for x in p):
            return False
        validate_fault_input(old, old_faults)
        validate_fault_input(new, new_faults)
        return ordinary_relational_assertion(old, new, p) and np.array_equal(new_faults, old_faults[:, p])
    except (KeyError, IndexError, ValueError, TypeError):
        return False
