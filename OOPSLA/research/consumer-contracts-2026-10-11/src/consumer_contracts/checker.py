"""Independent relation checker: verifies actual arrays, not plan assertions."""
from dataclasses import dataclass
import numpy as np
from .model import Bundle


@dataclass(frozen=True)
class Verdict:
    status: str
    reason: str


def check_relation(old, new, certificate):
    if certificate is None:
        return Verdict('unknown', 'missing permutation evidence')
    if type(old) is not Bundle or type(new) is not Bundle or not old.valid() or not new.valid():
        return Verdict('rejected', 'invalid snapshot domain')
    if not isinstance(certificate, dict) or certificate.get('schema') != 'fault-column-permutation-v1':
        return Verdict('unknown', 'unsupported evidence schema')
    if 'permutation' not in certificate:
        return Verdict('unknown', 'missing permutation')
    p = certificate['permutation']
    n = old.priors.size
    if not isinstance(p, list) or len(p) != n or any(type(x) is not int for x in p) or sorted(p) != list(range(n)):
        return Verdict('rejected', 'not a total column bijection')
    if certificate.get('old') != old.fingerprint or certificate.get('new') != new.fingerprint:
        return Verdict('rejected', 'snapshot binding mismatch')
    if certificate.get('transported_fields') != ['h', 'logical', 'priors']:
        return Verdict('rejected', 'incomplete field transport')
    if old.h.shape != new.h.shape or old.logical.shape != new.logical.shape:
        return Verdict('rejected', 'shape mismatch')
    if not (np.array_equal(new.h, old.h[:, p]) and np.array_equal(new.logical, old.logical[:, p])
            and np.array_equal(new.priors, old.priors[p])):
        return Verdict('rejected', 'declared coordinate relation is false')
    return Verdict('accepted', 'H, L and priors transported by the same bijection')


def check_consumer(rule, relation, input_transport=False):
    """Closed consumer language; unsupported Python is explicitly unknown."""
    if relation.status != 'accepted':
        return Verdict(relation.status, relation.reason)
    if rule == 'probability-range':
        return Verdict('accepted', 'permutation preserves range predicate')
    if rule in ('detector-action', 'logical-action', 'weighted-action'):
        if input_transport:
            return Verdict('accepted', 'same map and input coordinate bijection')
        return Verdict('rejected', 'fault input transport omitted')
    if rule == 'canonical-native-decoder':
        return Verdict('accepted' if input_transport else 'rejected',
                       'canonical decoder coordinate boundary required')
    if rule == 'raw-priors-by-column':
        return Verdict('revalidate', 'positional prior observation changed')
    if rule == 'direct-native-decoder':
        return Verdict('unknown', 'native heuristic equivariance not proved')
    return Verdict('unknown', 'consumer outside closed rule language')
