"""Measure unchanged source recovery and checking on freshly built real artifacts."""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib.metadata
import inspect
import io
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINNED = ROOT.parent / 'third_party/quits-0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452/src'
DEFAULT_OUT = ROOT / 'benchmarks/costs/regenerated'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def worker(out, index):
    sys.path[:0] = [str(PINNED), str(ROOT / 'src'), str(ROOT / 'experiments')]
    import numpy as np
    import semantics as S
    import extract_read_sets as extractor
    import qec_measure as Q
    import quits
    from quits.layout import TransversalLayout

    assert Path(quits.__file__).resolve().is_relative_to(PINNED)
    # Explicit location binding accommodates this checkout's directory layout.
    extractor.find_quits_src = lambda: PINNED / 'quits'
    protocol = {'code': ['BB', 'HGP', 'QLP'], 'extractor': ['zxcoloration'],
                'arch': ['free'], 'noise': ['SD6', 'SI1000'], 'decoder': ['BP-OSD']}
    specs = S._cartesian(protocol)

    t0 = time.perf_counter()
    recovery = extractor.collect()
    t1 = time.perf_counter()
    recovered = {name: tuple(recovery['summary']['auto_read_sets'][name])
                 for name in S.COORDINATES}
    assert {k: set(v) for k, v in recovered.items()} == {
        k: set(v) for k, v in S.READ_SETS_FROM_SOURCE.items()}
    recovered_edges = {
        name: tuple(p for p in recovery['summary']['auto_artifact_reads'][name] if p != name)
        for name in S.COORDINATES}
    assert {k: set(v) for k, v in recovered_edges.items()} == {
        k: set(v) for k, v in S.ASSEMBLY_EDGES_FROM_SOURCE.items()}

    materialized = {}
    bundles = {}
    def key(s):
        return tuple(getattr(s, k) for k in S.COORDINATES)
    def dense(a):
        return a.toarray() if hasattr(a, 'toarray') else np.asarray(a)
    with contextlib.redirect_stdout(io.StringIO()):
        for s in specs:
            bundle = Q.build(s.code, s.extractor, s.noise, num_rounds=2)
            obj = bundle['code_obj']
            mapping = TransversalLayout(obj).mapping()
            prediction = Q.decode(bundle, shots=16, seed=7, W=3, F=1)
            materialized[key(s)] = {
                'code': {n: dense(getattr(obj, n)).copy() for n in ('hz', 'hx', 'lz', 'lx')},
                'noise': dict(Q.NOISE_PARAMS[s.noise]),
                'extractor': {'circuit': str(bundle['circuit']), 'dem': str(bundle['dem'])},
                'arch': {'data': mapping.data, 'zcheck': mapping.zcheck, 'xcheck': mapping.xcheck},
                'decoder': prediction.copy()}
            bundles[key(s)] = bundle
    t2 = time.perf_counter()
    # Cache raw outputs once; all later grouping uses the original checker and equality.
    nodes = {name: S.Component(name, recovered[name],
                              lambda s, inputs, n=name: materialized[key(s)][n])
             for name in S.COORDINATES}
    assembly = S.Assembly(nodes, recovered_edges)
    reports = {
        name: S.detect_hidden_dependency(nodes[name], protocol,
                                         inputs_for=S.predecessor_inputs(assembly, name))
        for name in S.COORDINATES}
    undeclared = S.Component('extractor', ('code', 'extractor'), nodes['extractor'].produce)
    negative = S.detect_hidden_dependency(undeclared, protocol,
                                          inputs_for=S.predecessor_inputs(assembly, 'extractor'))
    t3 = time.perf_counter()
    assert all(r['verdict'] == 'pure' for r in reports.values())
    assert negative['observed_extensions'] == ['noise']

    # Independent repeat controls are outside the reported timing stages.
    repeats_equal = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for s in specs:
            prediction = Q.decode(bundles[key(s)], shots=16, seed=7, W=3, F=1)
            repeats_equal['/'.join(key(s))] = np.array_equal(
                materialized[key(s)]['decoder'], prediction)
        native = Q.agreement_check(bundles[key(specs[0])], shots=16, seed=7)
    assert all(repeats_equal.values()) and native['bitwise_identical']

    equality_lines = inspect.getsource(S.artifact_equal).splitlines()
    equality_tree = ast.parse(inspect.getsource(S.artifact_equal)).body[0]
    doc = equality_tree.body[0]
    doc_lines = set(range(doc.lineno, doc.end_lineno + 1)) if isinstance(doc, ast.Expr) else set()
    code_lines = sum(bool(line.strip()) and not line.lstrip().startswith('#')
                     and i not in doc_lines for i, line in enumerate(equality_lines, 1))
    manual_inputs = {'producer_packages': len(extractor.DIMENSION_FILES),
                     'entry_search_patterns': len(extractor.ANCHOR_SPECS),
                     'cross_package_exceptions': len(extractor.CROSS_PACKAGE_ANCHORS),
                     'coordinate_carriers': len(extractor._COORDINATE_NAMES),
                     'artifact_aliases': len(extractor._ARTIFACT_ALIASES),
                     'generic_name_exclusions': len(extractor._GENERIC_IDENTIFIERS),
                     'equality_code_lines': code_lines,
                     'historical_person_hours': None}
    evidence = out / f'evidence-{index:02d}'
    evidence.mkdir(parents=True, exist_ok=True)
    arrays = {}
    for i, s in enumerate(specs):
        artifact = materialized[key(s)]
        (evidence / f'{i:02d}.stim').write_text(artifact['extractor']['circuit'], encoding='utf-8')
        (evidence / f'{i:02d}.dem').write_text(artifact['extractor']['dem'], encoding='utf-8')
        arrays.update({f'{i:02d}_{n}': a for n, a in artifact['code'].items()})
        arrays[f'{i:02d}_predictions'] = artifact['decoder']
    np.savez_compressed(evidence / 'arrays.npz', **arrays)
    write_json(evidence / 'source-recovery.json', recovery)
    record = {'index': index, 'domain': protocol, 'specifications': len(specs),
              'producer_reports': reports, 'omitted_noise_control': negative,
              'source_s': t1 - t0, 'generation_s': t2 - t1, 'checking_s': t3 - t2,
              'staged_total_s': t3 - t0, 'repeated_predictions_equal': repeats_equal,
              'native_path_control': native, 'manual_inputs': manual_inputs,
              'evidence_sha256': {str(p.relative_to(out)): sha(p) for p in evidence.iterdir()}}
    write_json(out / f'run-{index:02d}.json', record)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--repetitions', type=int, default=7)
    parser.add_argument('--worker', type=int)
    args = parser.parse_args()
    if args.worker is not None:
        worker(args.out, args.worker)
        return
    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    for i in range(args.repetitions):
        started = time.perf_counter()
        env = dict(os.environ, PYTHONHASHSEED='0', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        command = [sys.executable, str(Path(__file__).resolve()), '--out', str(args.out), '--worker', str(i)]
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        (args.out / f'worker-{i:02d}.stdout.txt').write_text(result.stdout, encoding='utf-8')
        (args.out / f'worker-{i:02d}.stderr.txt').write_text(result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(result.stderr)
        elapsed = time.perf_counter() - started
        record = json.loads((args.out / f'run-{i:02d}.json').read_text(encoding='utf-8'))
        record['process_wall_s'] = elapsed
        write_json(args.out / f'run-{i:02d}.json', record)
        records.append(record)
        print(f'Run {i + 1}: source={record["source_s"]:.3f}s generation={record["generation_s"]:.3f}s checking={record["checking_s"]:.3f}s', flush=True)
    summary = {}
    for field in ('source_s', 'generation_s', 'checking_s', 'staged_total_s', 'process_wall_s'):
        values = [r[field] for r in records]
        quartiles = statistics.quantiles(values, n=4)
        summary[field] = {'median': statistics.median(values), 'q1': quartiles[0],
                          'q3': quartiles[2], 'min': min(values), 'max': max(values), 'raw': values}
    evidence = {'protocol': {'repetitions': args.repetitions, 'serial': True, 'hash_seed': 0,
                            'shots': 16, 'sampler_seed': 7, 'rounds': 2, 'W': 3, 'F': 1,
                            'materialize_once_then_check': True,
                            'timing_excludes_evidence_serialization_and_repeat_controls': True,
                            'process_wall_includes_imports_repeat_controls_and_serialization': True},
                'environment': {'python': sys.version, 'executable': sys.executable,
                                'platform': platform.platform(), 'processor': platform.processor(),
                                'cpu_count': os.cpu_count(),
                                'versions': {n: importlib.metadata.version(n) for n in
                                             ('numpy', 'scipy', 'stim', 'ldpc', 'networkx')}},
                'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in
                                  (ROOT / 'src/semantics.py', ROOT / 'experiments/extract_read_sets.py',
                                   ROOT / 'experiments/qec_measure.py', Path(__file__).resolve())},
                'domain': records[0]['domain'], 'manual_inputs': records[0]['manual_inputs'],
                'summary': summary, 'runs': records}
    write_json(args.out / 'summary.json', evidence)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
