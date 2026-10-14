"""Explicit snapshots and provenance for the research experiments."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import platform
import sys

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[1]
WORKSPACE = PROJECT.parent


def snapshot(value):
    if sparse.issparse(value):
        matrix = value.tocsc(copy=True)
        matrix.sort_indices()
        return ("csc", matrix.shape, snapshot(matrix.indptr),
                snapshot(matrix.indices), snapshot(matrix.data))
    if isinstance(value, np.ndarray):
        return ("array", value.dtype.str, value.shape, value.tobytes())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return ("dict", tuple(sorted((str(k), snapshot(v)) for k, v in value.items())))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(snapshot(v) for v in value))
    if isinstance(value, (str, int, float, bool, bytes, type(None))):
        return value
    raise TypeError(f"No exact snapshot protocol for {type(value).__name__}")


def digest(value):
    return hashlib.sha256(repr(snapshot(value)).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def environment():
    packages = ["numpy", "scipy", "stim", "ldpc", "qldpc", "quits", "galois", "pytest"]
    return {"python": sys.version, "executable": sys.executable,
            "platform": platform.platform(), "hash_seed": os.environ.get("PYTHONHASHSEED"),
            "packages": {p: importlib.metadata.version(p) for p in packages}}
