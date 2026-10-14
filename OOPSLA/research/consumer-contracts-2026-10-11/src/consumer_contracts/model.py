"""Immutable binary fault-matrix snapshots; columns denote fault variables."""
from dataclasses import dataclass
import hashlib
import numpy as np


def array_digest(array):
    a = np.ascontiguousarray(array)
    return hashlib.sha256(str((a.shape, a.dtype.str)).encode() + a.tobytes()).hexdigest()


@dataclass(frozen=True)
class Bundle:
    h: np.ndarray
    logical: np.ndarray
    priors: np.ndarray

    def __post_init__(self):
        # Arrays backed by bytes cannot be made writable by a caller.
        for name in ('h', 'logical', 'priors'):
            a = np.ascontiguousarray(getattr(self, name))
            a = np.frombuffer(a.tobytes(), dtype=a.dtype).reshape(a.shape)
            object.__setattr__(self, name, a)

    @property
    def fingerprint(self):
        return hashlib.sha256(''.join(array_digest(a) for a in (self.h, self.logical, self.priors)).encode()).hexdigest()

    def valid(self):
        return (all(type(a) is np.ndarray for a in (self.h, self.logical, self.priors))
                and self.h.ndim == self.logical.ndim == 2 and self.priors.ndim == 1
                and self.h.dtype == self.logical.dtype == np.uint8
                and self.priors.dtype == np.float64
                and self.h.shape[1] == self.logical.shape[1] == self.priors.size
                and np.all((self.h == 0) | (self.h == 1))
                and np.all((self.logical == 0) | (self.logical == 1))
                and np.all(np.isfinite(self.priors))
                and np.all((self.priors > 0) & (self.priors < 0.5)))

    def reindex(self, permutation):
        permutation = list(permutation)
        return Bundle(self.h[:, permutation], self.logical[:, permutation], self.priors[permutation])


def validate_fault_input(bundle, faults):
    """Disallow object operator overloading at the restricted Python boundary."""
    if (type(faults) is not np.ndarray or faults.dtype != np.uint8 or faults.ndim != 2
            or faults.shape[1] != bundle.priors.size
            or not np.all((faults == 0) | (faults == 1))):
        raise ValueError('fault input outside the binary ndarray domain')
    return faults
