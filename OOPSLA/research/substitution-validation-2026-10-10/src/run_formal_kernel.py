"""Generate and independently check finite certificates and failures."""
import json
import time

from certificates.formal_kernel import Combine, Copy, Emit, If, Program, Return, check
from common import ROOT, environment, write_json


def main():
    ret = Return(("structure", "probability"))
    old = Program((Emit("structure", 1), Emit("probability", 1), ret))
    new = Program((Emit("structure", 1), Emit("probability", 2), ret))
    bad = Program((Emit("structure", 1), If("probability", (Emit("structure", 2),), ()),
                   Emit("probability", 2), ret))
    unknown = Program((Combine(Copy("structure"), Copy("probability")),))
    certificate = {"projection": ("structure",), "generator": "finite-kernel-v1"}
    records = {}
    for name, left, right in (("probability_only", old, new), ("structure_branch", old, bad),
                              ("unsupported", old, unknown)):
        t0 = time.perf_counter_ns()
        try:
            result = check(left, right, certificate)
        except Exception as error:
            result = {"accepted": False, "reason": str(error), "witnesses": []}
        result["check_ns"] = time.perf_counter_ns() - t0
        records[name] = result
    assert records["probability_only"]["accepted"]
    assert not records["structure_branch"]["accepted"]
    assert not records["unsupported"]["accepted"]
    out = ROOT / "results" / "formal-kernel"
    out.mkdir(exist_ok=True)
    write_json(out / "comparison.json", {"environment": environment(), "records": records,
        "language": "finite immutable label programs", "input_count": 9,
        "generator_and_checker_separated": True,
        "arbitrary_python_soundness_claimed": False,
        "real_quits_certificate_import": "adapter only; unknown source summaries rejected"})
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
