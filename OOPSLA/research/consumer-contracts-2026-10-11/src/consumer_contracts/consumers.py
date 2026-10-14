"""Actual numerical consumers and a deterministic native decoder boundary."""
import numpy as np
from ldpc import BpOsdDecoder


def detector_action(bundle, faults):
    return (faults @ bundle.h.T) % 2


def logical_action(bundle, faults):
    return (faults @ bundle.logical.T) % 2


def weighted_action(bundle, faults):
    # Order-independent sorting fixes floating reduction order as well.
    ordered = np.ascontiguousarray(np.sort(faults * bundle.priors, axis=1))
    return np.sum(ordered, axis=1)


def native_predictions(bundle, syndromes):
    decoder = BpOsdDecoder(bundle.h, error_channel=bundle.priors.tolist(), max_iter=2,
                           bp_method='minimum_sum', ms_scaling_factor=0.625,
                           osd_method='OSD_0', osd_order=0, omp_thread_count=1)
    faults = np.array([np.array(decoder.decode(row), dtype=np.uint8, copy=True) for row in syndromes])
    return faults, logical_action(bundle, faults)


def canonical_native_predictions(bundle, permutation, syndromes):
    """Execute the native decoder in original coordinates, then transport.

    Requires a checked relation to the original snapshot. No claim that a
    native decoder rerun on a permuted matrix is itself equivariant.
    """
    inverse = np.argsort(permutation)
    canonical = bundle.reindex(inverse)
    old_faults, _ = native_predictions(canonical, syndromes)
    new_faults = old_faults[:, permutation]
    return new_faults, logical_action(bundle, new_faults)
