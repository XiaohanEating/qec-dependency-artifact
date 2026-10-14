"""Adversarial witnesses for the source analysis trust boundary."""
import sys

from certificates.source_flow import Flow, Unsupported
from common import ROOT, write_json


CASES = {
    "zero_loop_target": '''def detector_error_model_to_matrix(dem):
    for inst in dem.flattened():
        x = inst.args_copy()
        for x in []:
            pass
    return x, x, x
''',
    "zero_loop_body": '''def detector_error_model_to_matrix(dem):
    for inst in dem.flattened():
        x = inst.args_copy()
        for y in []:
            x = 0
    return x, x, x
''',
    "mutable_helper_return": '''def identity(a):
    return a
def detector_error_model_to_matrix(dem):
    a = []
    b = identity(a)
    for inst in dem.flattened():
        b.append(inst.args_copy()[0])
    return a, a, a
''',
    "tuple_alias": '''def detector_error_model_to_matrix(dem):
    a = []
    box = (a,)
    b = box[0]
    for inst in dem.flattened():
        b.append(inst.args_copy()[0])
    return a, a, a
''',
    "nested_alias": '''def detector_error_model_to_matrix(dem):
    a = []
    box = [a]
    b = box[0]
    for inst in dem.flattened():
        b.append(inst.args_copy()[0])
    return a, a, a
''',
    "swapped_keywords": '''def select(first, second):
    return first
def detector_error_model_to_matrix(dem):
    x = []
    for inst in dem.flattened():
        x.append(select(second=inst.targets_copy(), first=inst.args_copy()))
    return x, x, x
''',
    "dynamic_caller_scope": '''def leak():
    return hidden
def detector_error_model_to_matrix(dem):
    hidden = []
    for inst in dem.flattened():
        hidden = inst.args_copy()
        x = leak()
    return x, x, x
''',
}


def main():
    records = {}
    for name, source in CASES.items():
        try:
            result = Flow(source).analyze()
            records[name] = {"result": result, "accepted": result["probability_independent_structure"]}
        except Unsupported as error:
            records[name] = {"accepted": False, "unknown": str(error)}
    stage = "before" if "--before" in sys.argv else "after"
    write_json(ROOT / "results" / ("analyzer-boundaries-" + stage + ".json"), records)
    print(records)
    if stage == "after":
        assert all(not row["accepted"] for row in records.values())


if __name__ == "__main__":
    main()
