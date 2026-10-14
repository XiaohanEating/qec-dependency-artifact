"""Native stateful control change certified from first-run RNG path margins."""
import contextlib
import hashlib
import inspect
import io
import json
from pathlib import Path
import sys
import time

import numpy as np

from kernel.route_path import check_route_path,source_sites


def main():
    root=Path(__file__).resolve().parents[1];workspace=root.parents[2]
    path=workspace/'third_party'/'qecc_routing-4ef18121c39492414b85ff36b3a61c83f9ebf95f'/'src_py'/'bivariate-bicycle'/'general.py'
    whole=path.read_text(encoding='utf-8');source=whole[:whole.index('lr_time = 5')]
    sites=source_sites(source)
    ns={'__name__':'routing_relation','__file__':str(path)}
    saved_path=list(sys.path);sys.path.insert(0,str(path.parent))
    try:
        with contextlib.redirect_stdout(io.StringIO()):exec(compile(source,str(path),'exec'),ns)
    finally:sys.path[:]=saved_path
    arrays={name:ns[name].copy() for name in {'x_check_succ_probs','z_check_succ_probs'}}
    original=np.random.random; trace=[]
    def observed(*args,**kwargs):
        frame=inspect.currentframe().f_back
        if frame.f_code.co_filename!=str(path) or frame.f_lineno not in sites:
            raise ValueError('uncertified random call')
        array,index_name=sites[frame.f_lineno];index=int(frame.f_locals[index_name])
        draw=float(original(*args,**kwargs))
        trace.append({'site':frame.f_lineno,'array':array,'index':index,'draw':draw,'old_threshold':float(ns[array][index])})
        trace[-1].update({'shape':[],'margin':abs(draw-trace[-1]['old_threshold']),
                          'old_guard':draw<trace[-1]['old_threshold']})
        return draw
    np.random.seed(2026);np.random.random=observed
    start=time.perf_counter_ns()
    try:old=ns['Simulation'](5,5);old.simulate()
    finally:np.random.random=original
    old_ns=time.perf_counter_ns()-start
    gap=min(abs(r['draw']-r['old_threshold']) for r in trace)
    delta=gap/2
    changed={name:np.clip(values+delta,0,1) for name,values in arrays.items()}
    proof={'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'trace':trace}
    trace_sha=hashlib.sha256(json.dumps(trace,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    start=time.perf_counter_ns(); checked=check_route_path(source,proof,changed,trace_sha);cost=time.perf_counter_ns()-start
    assert checked['accepted']
    for name,values in changed.items():ns[name]=values
    np.random.seed(2026);new=ns['Simulation'](5,5);new.simulate()
    assert str(old.c)==str(new.c)
    assert all(np.array_equal(value,getattr(new,key)) for key,value in old.__dict__.items() if isinstance(value,np.ndarray))
    # A single actual threshold crossing is a checkable failed relation.
    bad={name:values.copy() for name,values in changed.items()};row=trace[0]
    bad[row['array']][row['index']]=row['draw']-1e-9 if row['draw']<row['old_threshold'] else row['draw']+1e-9
    rejected=check_route_path(source,proof,bad,trace_sha);assert not rejected['accepted']
    shape_proof={**proof,'trace':[dict(row) for row in trace]};shape_proof['trace'][0]['shape']=[1]
    site_proof={**proof,'trace':[dict(row) for row in trace]};site_proof['trace'][0]['site']=99999
    extra_rejects={'rng_shape':not check_route_path(source,shape_proof,changed,trace_sha)['accepted'],
                   'rng_site':not check_route_path(source,site_proof,changed,trace_sha)['accepted'],
                   'missing_trusted_trace':not check_route_path(source,proof,changed)['accepted']}
    assert all(extra_rejects.values())
    # Strong baseline costs: actual native rerun versus identical trace checker.
    baselines={}
    for mode in ('native_route_guard_rerun','same_trace_certificate','proposed_trace_certificate'):
        samples=[]
        for _ in range(5):
            start=time.perf_counter_ns()
            if mode=='native_route_guard_rerun':
                np.random.seed(2026);rerun=ns['Simulation'](5,5);rerun.simulate()
                assert str(rerun.c)==str(old.c)
            else:
                assert check_route_path(source,proof,changed,trace_sha)['accepted']
            samples.append(time.perf_counter_ns()-start)
        baselines[mode]={'samples_ns':samples,'median_ns':float(np.median(samples))}
    out=root/'results'/'route-path';out.mkdir(exist_ok=True)
    np.savez_compressed(out/'thresholds.npz',**{'old_'+k:v for k,v in arrays.items()},**{'new_'+k:v for k,v in changed.items()})
    data={'source_sha256':proof['source_sha256'],'trusted_trace_sha256':trace_sha,'trace':trace,'proof':checked,'checker_ns':cost,'old_native_generation_ns':old_ns,
          'delta':delta,'minimum_margin':gap,'threshold_arrays_changed':any(not np.array_equal(arrays[k],changed[k]) for k in arrays),
          'native_circuit_equal':True,'native_array_state_equal':True,'crossing_rejected':rejected,
          'extra_rejections':extra_rejects,'baselines':baselines,
          'scope':'execution-specific relational guard certificate; complete original trace trusted, source coverage checked; no new producer needed for proof',
          'baseline_same_observation':'standard trace/guard incremental verifier with same margin assumptions can use the same certificate',
          'independent_algorithm_novelty_established':False}
    (out/'comparison.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print({k:data[k] for k in ['delta','minimum_margin','threshold_arrays_changed','native_circuit_equal','native_array_state_equal','checker_ns']})


if __name__=='__main__':main()
