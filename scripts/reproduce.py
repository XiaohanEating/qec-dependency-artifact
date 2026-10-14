"""Execute supplementary checks in a copy, preserving all published inputs."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SUBSTITUTION = Path('OOPSLA/research/substitution-validation-2026-10-10/src')
SYMBOLIC = Path('OOPSLA/research/proof-carrying-observations-2026-10-11/src')
CONSUMERS = Path('OOPSLA/research/consumer-contracts-2026-10-11')
JOBS = {
    'certificates': [(SUBSTITUTION / name, []) for name in (
        'check_analyzer_boundaries.py', 'check_property_projection.py',
        'run_dem_certificate.py', 'run_constructive_certificate.py',
        'run_formal_kernel.py', 'run_source_certificate.py')],
    'symbolic': [(SYMBOLIC / name, []) for name in (
        'run_kernel.py', 'run_coverage.py', 'run_event_fold.py',
        'run_event_costs.py', 'run_trust_failures.py', 'run_native_rules.py')],
    'native': [(SYMBOLIC / name, []) for name in (
        'run_simulation_relation.py', 'run_route_path.py')],
    'consumers': [(CONSUMERS / 'src/run_validation.py',
                   ['--out', '.reproduction/consumer-validation'])],
    'costs': [(Path('OOPSLA/tools/costs/benchmark.py'),
               ['--out', '.reproduction/costs', '--repetitions', '7'])],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', nargs='+', choices=tuple(JOBS),
                        default=['certificates', 'symbolic', 'consumers'])
    args = parser.parse_args()
    work = ROOT / '.reproduction/work'
    for name in ('OOPSLA', 'shared', 'third_party'):
        shutil.copytree(ROOT / name, work / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache',
                                                     'regenerated', 'outputs', 'provenance'))
    logs = ROOT / '.reproduction/logs'
    logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONHASHSEED='0', MPLBACKEND='Agg', PYTHONIOENCODING='utf-8')
    for job in args.only:
        for script, extra in JOBS[job]:
            print(f'Running {script}', flush=True)
            result = subprocess.run([sys.executable, str(work / script), *extra],
                                    cwd=work, env=env, capture_output=True, text=True)
            log = logs / f'{job}-{script.stem}.txt'
            log.write_text(result.stdout + result.stderr, encoding='utf-8')
            if result.returncode:
                print(result.stdout + result.stderr)
                raise SystemExit(result.returncode)
    print(f'Completed {", ".join(args.only)}; logs in .reproduction/logs/')


if __name__ == '__main__':
    main()
