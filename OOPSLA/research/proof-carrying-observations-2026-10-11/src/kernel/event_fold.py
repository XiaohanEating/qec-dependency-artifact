"""Event-fold producer relation checker for real instruction streams."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Event:
    kind: str
    targets: tuple
    observables: tuple
    probability: float


@dataclass(frozen=True)
class FoldResult:
    columns: tuple
    priors: tuple
    range_ok: bool
    first_label_steps: int
    merge_steps: int


def events_from_dem(dem):
    events = []
    for inst in dem.flattened():
        if inst.type == "error":
            targets = tuple(sorted(t.val for t in inst.targets_copy() if t.is_relative_detector_id()))
            obs = tuple(sorted(t.val for t in inst.targets_copy() if t.is_logical_observable_id()))
            events.append(Event("error", targets, obs, float(inst.args_copy()[0])))
        elif inst.type in {"detector", "logical_observable"}:
            events.append(Event(inst.type, tuple(str(t) for t in inst.targets_copy()), (), 0.0))
        else:
            raise ValueError("unsupported DEM event: " + inst.type)
    return tuple(events)


def fold(events):
    labels = {}
    columns = []
    priors = []
    range_ok = True
    first_label_steps = merge_steps = 0
    for event in events:
        if event.kind != "error":
            continue
        if not 0 < event.probability < 0.5 or not math.isfinite(event.probability):
            range_ok = False
        key = event.targets
        if key not in labels:
            labels[key] = len(columns)
            # Native QUITS semantics: detector set owns the column; the first
            # event's observable label is retained, later labels are ignored.
            columns.append((event.targets, event.observables))
            priors.append(event.probability)
            first_label_steps += 1
        else:
            i = labels[key]
            priors[i] = priors[i] * (1 - event.probability) + event.probability * (1 - priors[i])
            merge_steps += 1
            if not 0 < priors[i] < 0.5 or not math.isfinite(priors[i]):
                range_ok = False
    return FoldResult(tuple(columns), tuple(priors), range_ok, first_label_steps, merge_steps)


def check_probability_only(old_events, new_events):
    """Certificate is a proof obligation, not a hash of new artifact."""
    old, new = fold(old_events), fold(new_events)
    return {"accepted": old.columns == new.columns and old.range_ok and new.range_ok,
            "columns_equal": old.columns == new.columns,
            "old_range_ok": old.range_ok, "new_range_ok": new.range_ok,
            "old": old, "new": new,
            "events_compared": len(old_events) + len(new_events)}
