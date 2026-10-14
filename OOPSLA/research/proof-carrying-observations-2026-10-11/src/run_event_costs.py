"""Single-process end-to-end event production and same-capability baselines."""
import json
from pathlib import Path
import statistics
import time

import stim
from quits.decoder.base import detector_error_model_to_matrix

from kernel.event_fold import Event, events_from_dem, fold, check_probability_only


def main():
    root = Path(__file__).resolve().parents[1]
    source = root.parent/"substitution-validation-2026-10-10"/"results"/"quits"/"normal.dem"
    dem = stim.DetectorErrorModel(source.read_text(encoding="utf-8"))
    start = time.perf_counter_ns(); original = events_from_dem(dem); initial = time.perf_counter_ns()-start
    old_fold = fold(original)
    modes = ("full_converter", "event_fold_checker", "same_event_certificate_cache")
    rows = {}
    for mode in modes:
        samples=[]
        for _ in range(9):
            start=time.perf_counter_ns()
            events=tuple(Event(e.kind,e.targets,e.observables,float(format(e.probability*.2,'.16g')) if e.kind=='error' else e.probability) for e in original)
            new_dem=stim.DetectorErrorModel()
            for event in events:
                if event.kind=='error':
                    targets=[stim.target_relative_detector_id(t) for t in event.targets]+[stim.target_logical_observable_id(t) for t in event.observables]
                    new_dem.append('error',event.probability,targets)
            # Preserve metadata counts. Native source has detector declarations.
            for inst in dem.flattened():
                if inst.type!='error':
                    new_dem.append(inst)
            text=str(new_dem)
            if mode=='full_converter':
                result=detector_error_model_to_matrix(stim.DetectorErrorModel(text))
                assert len(result[2])==len(old_fold.priors)
            else:
                certificate=check_probability_only(original,events)
                assert certificate['accepted']
            samples.append(time.perf_counter_ns()-start)
        rows[mode]={'samples_ns':samples,'median_ns':statistics.median(samples),'includes_new_event_and_dem_production':True}
    (root/'results'/'event-costs.json').write_text(json.dumps({'initial_event_parse_ns':initial,'modes':rows,
        'same_capability_baseline_has_identical_proof_algorithm':True,'algorithm_advantage_established':False,
        'scope':'end-to-end probability-only DEM construction plus native matrix conversion or event relation fold; source initialization separately counted'},indent=2),encoding='utf-8')
    print({mode:round(row['median_ns']/1e6,3) for mode,row in rows.items()})


if __name__=='__main__':
    main()
