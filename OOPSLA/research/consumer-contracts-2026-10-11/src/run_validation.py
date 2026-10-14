"""One isolated entry point for real artifacts, baselines and provenance."""
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np
import stim
import quits
import ldpc
from quits.decoder.base import detector_error_model_to_matrix
from consumer_contracts.model import Bundle, array_digest, validate_fault_input
from consumer_contracts.producer import execute_plan, lossless_dem_bundle
from consumer_contracts.checker import check_relation, check_consumer
from consumer_contracts.consumers import (detector_action, logical_action, weighted_action,
                                        native_predictions, canonical_native_predictions)
from consumer_contracts.baselines import (ordinary_relational_assertion, canonical_semantic_stamp,
                                        canonical_projection_equal, full_boundary_relational_assertion)
from consumer_contracts.frontend import (lower_callable, generate_consumer_evidence,
                                        verify_consumer_evidence)

ROOT = Path(__file__).resolve().parents[4]
PACKAGE = Path(__file__).resolve().parents[1]
OLD = ROOT / 'OOPSLA/research/substitution-validation-2026-10-10/results'


def measure(action, repeats=9):
    action()  # Warmup is not included in the samples.
    samples = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        action()
        samples.append(time.perf_counter_ns() - start)
    return {'repeats': repeats, 'samples_ns': samples, 'median_ns': statistics.median(samples)}


def case(name, source, permutation_kind, output, decode=True):
    content = source.read_text(encoding='utf-8')
    start = time.perf_counter_ns()
    dem = stim.DetectorErrorModel(content)
    old = lossless_dem_bundle(dem)
    first_parse_ns = time.perf_counter_ns() - start
    n = old.priors.size
    if permutation_kind == 'reverse':
        permutation = list(reversed(range(n)))
    elif permutation_kind == 'rotate':
        permutation = np.roll(np.arange(n), 1).tolist()
    else:
        permutation = np.random.default_rng(20261026).permutation(n).tolist()
    plan = {'permutation': permutation, 'fields': ['h', 'logical', 'priors']}
    start = time.perf_counter_ns()
    new, evidence = execute_plan(old, plan)
    first_generation_ns = time.perf_counter_ns() - start
    verdict = check_relation(old, new, evidence)
    assert verdict.status == 'accepted'
    directory = output / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'certificate.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    (directory / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
    # Fixed samples are only independent implementation checks. The algebraic
    # relation covers every binary input without input enumeration.
    faults = np.random.default_rng(20261025).integers(0, 2, (48, n), dtype=np.uint8)
    new_faults = faults[:, permutation]
    validate_fault_input(old, faults)
    validate_fault_input(new, new_faults)
    call_context = dict(old_bundle=old, new_bundle=new, old_faults=faults,
                        new_faults=new_faults, permutation=permutation, producer_certificate=evidence)
    observations = {}
    for rule, function in [('detector-action', detector_action), ('logical-action', logical_action),
                           ('weighted-action', weighted_action)]:
        before, after = function(old, faults), function(new, new_faults)
        assert np.array_equal(before, after)
        observations[rule] = {'verdict': check_consumer(rule, verdict, True).__dict__,
                              'independent_recompute_equal': True,
                              'old_hash': array_digest(before), 'new_hash': array_digest(after)}
        if rule in ('detector-action', 'logical-action'):
            lowered = lower_callable(function)
            consumer_evidence = generate_consumer_evidence(lowered, True)
            accepted = verify_consumer_evidence(inspect.getsource(function), consumer_evidence, verdict, **call_context)
            assert accepted == 'accepted'
            observations[rule]['automatic_frontend'] = {'lowered': lowered.__dict__,
                                                        'proof': consumer_evidence, 'check_status': accepted}
    observations['probability-range'] = {'verdict': check_consumer('probability-range', verdict).__dict__,
                                         'independent_recompute_equal': old.valid() == new.valid()}
    observations['raw-priors-by-column'] = {'verdict': check_consumer('raw-priors-by-column', verdict).__dict__,
                                           'equal': np.array_equal(old.priors, new.priors)}
    # An actual omitted-transport error, not merely a checker status.
    wrong_logical = logical_action(new, faults)
    missed_bits = int(np.count_nonzero(logical_action(old, faults) != wrong_logical))
    observations['logical-input-not-transported'] = {
        'verdict': check_consumer('logical-action', verdict, False).__dict__, 'differing_bits': missed_bits}
    assert missed_bits > 0
    observations['unmodelled-python-consumer'] = {'verdict': check_consumer('arbitrary-python', verdict, True).__dict__}
    observations['direct-native-decoder'] = {'verdict': check_consumer('direct-native-decoder', verdict, True).__dict__}

    attacks = {}
    for field in ('h', 'logical', 'priors'):
        arrays = {key: getattr(new, key).copy() for key in ('h', 'logical', 'priors')}
        if field == 'priors': arrays[field][0] += .00001
        else: arrays[field][0, 0] ^= 1
        bad = Bundle(**arrays)
        cert = deepcopy(evidence)
        cert['new'] = bad.fingerprint  # Attack bypasses trivial digest failure.
        attacks['false_' + field] = check_relation(old, bad, cert).__dict__
        assert attacks['false_' + field]['status'] == 'rejected'
    attacks['missing_evidence'] = check_relation(old, new, None).__dict__
    attacks['stale_binding'] = check_relation(new, old, evidence).__dict__
    incomplete = deepcopy(evidence)
    incomplete['transported_fields'] = ['h']
    attacks['incomplete_transport'] = check_relation(old, new, incomplete).__dict__

    # Strong baselines target the same coordinate relation, not raw bytes only.
    assert ordinary_relational_assertion(old, new, permutation)
    assert full_boundary_relational_assertion(old, new, evidence, faults, new_faults)
    assert canonical_projection_equal(old, new, permutation)
    identity = list(range(n))
    old_stamp = canonical_semantic_stamp(old, identity)
    new_stamp = canonical_semantic_stamp(new, permutation)
    assert old_stamp == new_stamp
    timings = {
        'parse_and_lossless_fold': measure(lambda: lossless_dem_bundle(stim.DetectorErrorModel(content))),
        'producer_artifact_and_evidence': measure(lambda: execute_plan(old, plan)),
        'independent_relation_check': measure(lambda: check_relation(old, new, evidence)),
        'eight_consumer_obligations_only': measure(lambda: [check_consumer(rule, verdict, True) for rule in observations]),
        'ordinary_relational_assertion': measure(lambda: ordinary_relational_assertion(old, new, permutation)),
        'ordinary_full_boundary_relation_and_input': measure(lambda: full_boundary_relational_assertion(old, new, evidence, faults, new_faults)),
        'proposed_relation_and_input': measure(lambda: (check_relation(old, new, evidence),
            validate_fault_input(old, faults), validate_fault_input(new, new_faults),
            np.array_equal(new_faults, faults[:, permutation]))),
        'canonical_projection_comparison': measure(lambda: canonical_projection_equal(old, new, permutation)),
        'semantic_stamp_new_construction': measure(lambda: canonical_semantic_stamp(new, permutation)),
        'semantic_stamp_cached_comparison': measure(lambda: old_stamp == new_stamp),
        'recompute_three_numerical_consumers': measure(lambda: [f(new, new_faults) for f in (detector_action, logical_action, weighted_action)]),
        'runtime_input_domain_check': measure(lambda: validate_fault_input(new, new_faults)),
        'two_consumer_frontend_and_evidence_generation': measure(lambda: [generate_consumer_evidence(lower_callable(f), True) for f in (detector_action, logical_action)]),
        'two_consumer_source_and_proof_checks': measure(lambda: [verify_consumer_evidence(inspect.getsource(f),
            generate_consumer_evidence(lower_callable(f), True), verdict, **call_context) for f in (detector_action, logical_action)]),
    }
    groups = defaultdict(set)
    for inst in dem.flattened():
        if inst.type == 'error':
            groups[tuple(sorted(t.val for t in inst.targets_copy() if t.is_relative_detector_id()))].add(
                tuple(sorted(t.val for t in inst.targets_copy() if t.is_logical_observable_id())))
    response_audit = {'detector_signatures_with_multiple_logical_labels': sum(len(labels) > 1 for labels in groups.values()),
                      'full_response_fault_columns': n,
                      'native_detector_only_columns': len(groups),
                      'converter_joint_semantics_require_full_response': True}
    # A second optimization path: compose producer reindex operations before
    # materializing, then reuse the original consumer rule set unchanged.
    second = np.roll(np.arange(n), 2).tolist()
    staged_plan = {'steps': [{'operation': 'reindex-fault-columns', 'permutation': permutation},
                             {'operation': 'reindex-fault-columns', 'permutation': second}]}
    staged, staged_evidence = execute_plan(old, staged_plan)
    direct_staged = old.reindex(permutation).reindex(second)
    assert staged.fingerprint == direct_staged.fingerprint
    assert check_relation(old, staged, staged_evidence).status == 'accepted'
    composed_faults = faults[:, staged_evidence['permutation']]
    assert np.array_equal(logical_action(old, faults), logical_action(staged, composed_faults))
    timings['two_stage_plan_normalized_materialization'] = measure(lambda: execute_plan(old, staged_plan))
    timings['two_stage_direct_materialization_no_evidence'] = measure(lambda: old.reindex(permutation).reindex(second))
    native = {'executed': False}
    native_arrays = {}
    if decode:
        # Saved syndromes are real Stim sampling results of the stress circuit.
        syndromes = np.load(OLD / 'quits/decoder-evidence.npz')['detectors'][:16].astype(np.uint8)
        assert syndromes.shape[1] == old.h.shape[0]
        start = time.perf_counter_ns()
        native_errors, predictions = native_predictions(old, syndromes)
        first_native_ns = time.perf_counter_ns() - start
        transported_errors, transported = canonical_native_predictions(new, permutation, syndromes)
        direct_errors, direct = native_predictions(new, syndromes)
        assert np.array_equal(native_errors[:, permutation], transported_errors)
        assert np.array_equal(predictions, transported)
        native = {'executed': True, 'shots': len(syndromes), 'input_source': 'quits/decoder-evidence.npz:detectors[:16]',
                  'consumer': 'ldpc.BpOsdDecoder.decode with explicit coordinate boundary',
                  'max_iter': 2, 'osd_method': 'OSD_0', 'scaling': .625,
                  'first_native_execution_ns': first_native_ns,
                  'canonical_transport_equal': True,
                  'direct_native_differing_predictions': int(np.count_nonzero(predictions != direct)),
                  'direct_native_differing_faults_after_transport': int(np.count_nonzero(native_errors[:, permutation] != direct_errors)),
                  'scientific_accuracy_or_native_equivariance_claimed': False}
        observations['canonical-native-decoder'] = {'verdict': check_consumer('canonical-native-decoder', verdict, True).__dict__,
                                                     'independent_recompute_equal': True}
        native_arrays = dict(syndromes=syndromes, native_errors=native_errors,
                             native_predictions=predictions, transported_errors=transported_errors,
                             transported_predictions=transported, direct_predictions=direct)
        timings['canonical_native_full_execution'] = measure(lambda: canonical_native_predictions(new, permutation, syndromes), 5)
    np.savez_compressed(directory / 'evidence.npz', old_h=old.h, old_logical=old.logical, old_priors=old.priors,
                        new_h=new.h, new_logical=new.logical, new_priors=new.priors,
                        faults=faults, transported_faults=new_faults, **native_arrays)
    return {'source': str(source.relative_to(ROOT)), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'phase': 'development' if name == 'normal-reverse' else 'post-rule-check',
            'permutation': permutation_kind, 'shape_h': old.h.shape, 'shape_l': old.logical.shape,
            'old_snapshot': old.fingerprint, 'new_snapshot': new.fingerprint,
            'artifact_changed': old.fingerprint != new.fingerprint,
            'producer_relation': verdict.__dict__, 'consumer_results': observations,
            'full_response_audit': response_audit,
            'second_path_composed_plan': {'relation_accepted': True, 'direct_artifact_equal': True,
                                         'logical_observation_equal': True, 'additional_consumer_rules': 0,
                                         'operation_count': 2, 'materialization_count': 1},
            'attacks': attacks, 'native_decoder': native, 'timings': timings,
            'first_parse_ns': first_parse_ns, 'first_artifact_and_evidence_ns': first_generation_ns,
            'per_case_relation_or_consumer_code_changes': 0,
            'per_case_input_annotations': ['source path', 'permutation plan'],
            'ordinary_assertion_relation_equal': True, 'canonical_projection_relation_equal': True,
            'semantic_stamp_relation_equal': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, source, kind, decode in [
        ('normal-reverse', OLD / 'quits/normal.dem', 'reverse', True),
        ('lower-rotate', OLD / 'quits/lower.dem', 'rotate', True),
        ('stress-shuffle', OLD / 'quits/stress.dem', 'shuffle', True),
        ('qecc-reverse', OLD / 'qecc/baseline.dem', 'reverse', False),
    ]:
        results[name] = case(name, source, kind, args.out, decode)
        print(name, results[name]['shape_h'], 'accepted; consumers and attacks checked', flush=True)
    source_files = list((PACKAGE / 'src').rglob('*.py')) + list((PACKAGE / 'tests').glob('*.py'))
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    native_path = Path(inspect.getfile(detector_error_model_to_matrix))
    result = {'environment': {'python': sys.version, 'stim': stim.__version__, 'quits': str(quits.__file__),
                              'ldpc': str(ldpc.__file__), 'native_converter_sha256': hashlib.sha256(native_path.read_bytes()).hexdigest()},
              'scope': 'restricted DEM fold and column-reindex plans; controlled consumer rules, one native decoder adapter',
              'source_manifest': manifest, 'cases': results,
              'heldout_note': 'Cases selected before this run; source rules unchanged across cases. Same author, known corpus, not external blind evaluation.',
              'novel_algorithm_or_unique_expressiveness_established': False}
    (args.out / 'validation.json').write_text(json.dumps(result, indent=2,
        default=lambda value: value.item() if isinstance(value, np.generic) else None) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
