"""Native Simulation source-generated producer relation and stateful replay."""
import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import time

import numpy as np

from generator.simulation import candidate
from kernel.simulation import check_source


def main():
    root=Path(__file__).resolve().parents[1]
    workspace=root.parents[2]
    source_file=workspace/'third_party'/'qecc_routing-4ef18121c39492414b85ff36b3a61c83f9ebf95f'/'src_py'/'bivariate-bicycle'/'general.py'
    whole=source_file.read_text(encoding='utf-8')
    source=whole[:whole.index('lr_time = 5')]
    start=time.perf_counter_ns(); proof=candidate(source,'idle_error'); generation=time.perf_counter_ns()-start
    start=time.perf_counter_ns(); checked=check_source(source,proof); checking=time.perf_counter_ns()-start
    assert checked['accepted'],checked
    # Definition loading preserves original source; the million-shot driver is
    # excluded, all native functions/class bodies are unmodified.
    before_path=list(sys.path)
    ns={'__name__':'native_simulation_proof','__file__':str(source_file)}
    sys.path.insert(0,str(source_file.parent))
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(source,str(source_file),'exec'),ns)
    finally:
        sys.path[:]=before_path
    records=[]
    original_random=np.random.random
    for idle in (.0002,.0004):
        ns['idle_error']=idle
        np.random.seed(2026)
        rng=[]
        def observed_random(*args,**kwargs):
            value=original_random(*args,**kwargs)
            rng.append(float(value));return value
        np.random.random=observed_random
        start=time.perf_counter_ns()
        try:
            sim=ns['Simulation'](5,5);sim.simulate()
        finally:
            np.random.random=original_random
        elapsed=time.perf_counter_ns()-start
        circuit=sim.c
        events=[(i.name,tuple(str(t) for t in i.targets_copy())) for i in circuit.flattened()]
        state={k:v.copy() for k,v in sim.__dict__.items() if isinstance(v,np.ndarray)}
        records.append({'idle':idle,'rng':rng,'events':events,'state':state,
                        'circuit':str(circuit),'noise_free':str(circuit.without_noise()),'elapsed_ns':elapsed})
    a,b=records
    assert a['rng']==b['rng'] and a['events']==b['events']
    assert a['state'].keys()==b['state'].keys() and all(np.array_equal(a['state'][k],b['state'][k]) for k in a['state'])
    assert a['circuit']!=b['circuit'] and a['noise_free']==b['noise_free']
    failures={}
    for label,mutant in {
        'parameter_in_route_guard':source.replace('if (i%self.lr_time==0):','if (idle_error > 0.0003):'),
        'parameter_changes_rng':source.replace('np.random.random() < z_check_succ_probs[z]','np.random.random() < idle_error'),
        'parameter_alias':source.replace('for i in range(1,self.num_rounds+1):','alias = idle_error\n        for i in range(1,self.num_rounds+1):'),
        'external_callback':source.replace('for i in range(1,self.num_rounds+1):','external_callback()\n        for i in range(1,self.num_rounds+1):'),
        'nested_scope':source.replace('def simulate(self):','def simulate(self):\n        def other():\n            self.c.append("DEPOLARIZE1", [], idle_error)'),
        'parameter_shadow':source.replace('def simulate(self):','def simulate(self, idle_error=0):'),
    }.items():
        rejection=check_source(mutant,candidate(mutant,'idle_error'))
        failures[label]=not rejection['accepted']
    assert all(failures.values())
    out=root/'results'/'simulation'
    out.mkdir(exist_ok=True)
    for i,row in enumerate(records):
        (out/f'noise-{i}.stim').write_text(row['circuit'],encoding='utf-8')
        np.savez_compressed(out/f'state-{i}.npz',**row['state'])
    data={'source':str(source_file),'full_source_sha256':hashlib.sha256(source_file.read_bytes()).hexdigest(),
          'definition_sha256':proof['source_sha256'],'generator_ns':generation,'checker_ns':checking,
          'proof':checked,'rng_count':len(a['rng']),'rng_values_identical':True,'rng_values':a['rng'],
          'ordered_events_equal':True,'event_count':len(a['events']),'array_state_equal':True,
          'state_fields':list(a['state']),'full_circuit_changed':True,'native_noise_free_equal':True,
          'native_generation_ns':[r['elapsed_ns'] for r in records],'failure_witnesses':failures,
          'manual_field_relation_E_supplied':False,'source_external_semantics_assumptions_explicit':True,
          'scope':'source-certified idle parameter erasure under fixed native append/RNG bindings; not arbitrary Python soundness'}
    (out/'comparison.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print({k:data[k] for k in ['rng_count','event_count','rng_values_identical','ordered_events_equal','array_state_equal','full_circuit_changed','failure_witnesses']})


if __name__=='__main__':
    main()
