"""Counterexamples for false acceptance and independent finite-domain oracles."""
import itertools
from copy import deepcopy
import numpy as np
import pytest
import stim
from consumer_contracts.model import Bundle, validate_fault_input
from consumer_contracts.producer import execute_plan, lossless_dem_bundle
from consumer_contracts.checker import check_relation, check_consumer
from consumer_contracts.consumers import detector_action, logical_action
from consumer_contracts.frontend import lower_linear_source, generate_consumer_evidence, verify_consumer_evidence


def test_multistage_plan_and_inverse_cancel_without_new_proof_rules():
    old = fixture()
    p, q = [2, 0, 1], [1, 2, 0]
    new, cert = execute_plan(old, {'steps': [
        {'operation': 'reindex-fault-columns', 'permutation': p},
        {'operation': 'reindex-fault-columns', 'permutation': q}]})
    assert cert['permutation'] == [0, 1, 2]
    assert new.fingerprint == old.fingerprint
    assert check_relation(old, new, cert).status == 'accepted'


@pytest.mark.parametrize('source', [
    'def renamed(x, y): return (y @ x.h.T) % 2',
    'def renamed(x, y): return (y @ x.logical.T) % 2',
])
def test_frontend_renaming_without_rule_changes(source):
    lowered = lower_linear_source(source)
    assert lowered.status == 'accepted'
    old = fixture()
    new, cert = execute_plan(old, {'permutation': [2, 0, 1]})
    evidence = generate_consumer_evidence(lowered, True)
    faults = np.array([[1, 0, 0]], dtype=np.uint8)
    context = dict(old_bundle=old, new_bundle=new, old_faults=faults,
                   new_faults=faults[:, [2, 0, 1]], permutation=[2, 0, 1], producer_certificate=cert)
    assert verify_consumer_evidence(source, evidence, check_relation(old, new, cert), **context) == 'accepted'
    assert verify_consumer_evidence(source, evidence, check_relation(old, new, cert)) == 'unknown'
    wrong = dict(context, new_faults=faults)
    assert verify_consumer_evidence(source, evidence, check_relation(old, new, cert), **wrong) == 'rejected'
    evidence['field'] = 'priors'
    assert verify_consumer_evidence(source, evidence, check_relation(old, new, cert)) == 'rejected'


@pytest.mark.parametrize('source', [
    'def f(x,y): return (y @ x.h.T) % 3',
    'def f(x,y): return (helper(y) @ x.h.T) % 2',
    'def f(x,y):\n x.h[0,0]=1\n return (y @ x.h.T) % 2',
    '@custom\ndef f(x,y): return (y @ x.h.T) % 2',
    'def f(x,y,z=2): return (y @ x.h.T) % 2',
    'def f(x,x): return (x @ x.h.T) % 2',
    'def f(x: callback(),y): return (y @ x.h.T) % 2',
])
def test_frontend_unknown_not_fake_proof(source):
    assert lower_linear_source(source).status == 'unknown'


def test_runtime_array_boundary_rejects_overloaded_and_nonbinary_inputs():
    class Evil(np.ndarray):
        def __matmul__(self, other):
            return 'forged'
    old = fixture()
    valid = np.zeros((1, 3), dtype=np.uint8)
    assert validate_fault_input(old, valid) is valid
    with pytest.raises(ValueError): validate_fault_input(old, valid.view(Evil))
    with pytest.raises(ValueError): validate_fault_input(old, np.full((1, 3), 2, dtype=np.uint8))
    with pytest.raises(ValueError): validate_fault_input(old, np.zeros((1, 2), dtype=np.uint8))


def fixture():
    return Bundle(np.array([[1, 0, 1], [0, 1, 1]], dtype=np.uint8),
                  np.array([[1, 0, 0]], dtype=np.uint8), np.array([.1, .2, .3]))


def test_all_bijections_all_binary_inputs():
    old = fixture()
    faults = np.array(list(itertools.product((0, 1), repeat=3)), dtype=np.uint8)
    for permutation in itertools.permutations(range(3)):
        new, cert = execute_plan(old, {'permutation': permutation})
        assert check_relation(old, new, cert).status == 'accepted'
        assert np.array_equal(detector_action(old, faults), detector_action(new, faults[:, permutation]))
        assert np.array_equal(logical_action(old, faults), logical_action(new, faults[:, permutation]))


@pytest.mark.parametrize('field', ['h', 'logical', 'priors'])
def test_consistent_binding_does_not_hide_false_relation(field):
    old = fixture()
    new, cert = execute_plan(old, {'permutation': [2, 0, 1]})
    arrays = {name: getattr(new, name).copy() for name in ('h', 'logical', 'priors')}
    if field == 'priors':
        arrays[field][0] += .01
    else:
        arrays[field][0, 0] ^= 1
    bad = Bundle(**arrays)
    cert['new'] = bad.fingerprint
    assert check_relation(old, bad, cert).status == 'rejected'


@pytest.mark.parametrize('permutation', [[0, 0, 1], [0, 1], [0, 1, 5], [True, 1, 2], [0., 1, 2]])
def test_non_bijection_rejected(permutation):
    old = fixture()
    new, cert = execute_plan(old, {'permutation': [2, 0, 1]})
    cert['permutation'] = permutation
    assert check_relation(old, new, cert).status == 'rejected'


def test_snapshots_cannot_be_mutated_through_original_alias():
    old = fixture()
    with pytest.raises(ValueError):
        old.h.setflags(write=True)
    with pytest.raises(ValueError):
        old.h[0, 0] = 0


def test_bundle_subclass_cannot_override_trusted_snapshot_properties():
    class Forged(Bundle):
        def valid(self): return True
    old = fixture()
    new, cert = execute_plan(old, {'permutation': [2, 0, 1]})
    forged = Forged(old.h, old.logical, old.priors)
    assert check_relation(forged, new, cert).status == 'rejected'


def test_missing_evidence_and_unsupported_consumer_are_unknown():
    old = fixture()
    new, cert = execute_plan(old, {'permutation': [2, 0, 1]})
    assert check_relation(old, new, None).status == 'unknown'
    relation = check_relation(old, new, cert)
    assert check_consumer('arbitrary-python', relation, True).status == 'unknown'
    assert check_consumer('logical-action', relation, False).status == 'rejected'


def test_stale_binding_and_incomplete_transport_rejected():
    old = fixture()
    new, cert = execute_plan(old, {'permutation': [2, 0, 1]})
    bad = deepcopy(cert)
    bad['old'] = 'forged'
    assert check_relation(old, new, bad).status == 'rejected'
    bad = deepcopy(cert)
    bad['transported_fields'] = ['h']
    assert check_relation(old, new, bad).status == 'rejected'


def joint_from_dem(dem):
    errors = [e for e in dem.flattened() if e.type == 'error']
    distribution = {}
    for bits in itertools.product((0, 1), repeat=len(errors)):
        d = l = 0
        weight = 1.
        for bit, instruction in zip(bits, errors):
            p = instruction.args_copy()[0]
            weight *= p if bit else 1 - p
            if bit:
                for target in instruction.targets_copy():
                    if target.is_relative_detector_id(): d ^= 1 << target.val
                    elif target.is_logical_observable_id(): l ^= 1 << target.val
        distribution[d, l] = distribution.get((d, l), 0) + weight
    return distribution


def joint_from_bundle(bundle):
    distribution = {}
    faults = np.array(list(itertools.product((0, 1), repeat=bundle.priors.size)), dtype=np.uint8)
    ds, ls = detector_action(bundle, faults), logical_action(bundle, faults)
    for bits, detectors, observables in zip(faults, ds, ls):
        weight = np.prod(np.where(bits, bundle.priors, 1 - bundle.priors))
        d = sum(int(bit) << i for i, bit in enumerate(detectors))
        l = sum(int(bit) << i for i, bit in enumerate(observables))
        distribution[d, l] = distribution.get((d, l), 0) + weight
    return distribution


@pytest.mark.parametrize('model', [
    'error(.1) D0 L0\nerror(.2) D0 L1',
    'error(.1) D0 L0\nerror(.2) D0 L0\nerror(.1) L1',
    'error(.1) D0 L0 ^ D1 L1\nerror(.2) D0 D0 L0 L0',
    'error(.1) D0 L0\nshift_detectors 1\nrepeat 2 {\nerror(.2) D0 L1\nshift_detectors 1\n}',
])
def test_lossless_fold_against_independent_joint_distribution(model):
    dem = stim.DetectorErrorModel(model)
    expected = joint_from_dem(dem)
    actual = joint_from_bundle(lossless_dem_bundle(dem))
    assert set(expected) == set(actual)
    assert all(abs(expected[k] - actual[k]) < 1e-14 for k in expected)


def test_previously_lost_pure_logical_event_preserved():
    bundle = lossless_dem_bundle(stim.DetectorErrorModel('error(.1) D0 L0\nerror(.2) D0 L1'))
    assert bundle.priors.size == 2
    assert abs(joint_from_bundle(bundle)[0, 3] - .02) < 1e-14
