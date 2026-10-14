"""Fair dependency baselines with exact snapshots at object or field granularity.

Every consumer, including a contract predicate, is an ordinary deterministic
task. The fine baseline is identical to projection-key incremental reuse.
"""
from dataclasses import dataclass

from common import snapshot


def field_value(value, path):
    for key in path:
        value = value[key] if isinstance(value, (dict, list, tuple)) else getattr(value, key)
    return value


@dataclass
class Task:
    name: str
    run: callable
    is_contract: bool = False


class Reads:
    def __init__(self, artifacts, granularity):
        self.artifacts = artifacts
        self.granularity = granularity
        self.trace = {}
        self.actual_fields = []

    def read(self, source, *path):
        value = field_value(self.artifacts[source], path)
        key = (source, path if self.granularity == "fields" else ())
        observed = value if self.granularity == "fields" else self.artifacts[source]
        self.trace[key] = snapshot(observed)
        self.actual_fields.append([source, list(path)])
        return value


class Engine:
    def __init__(self, sources, tasks, mode):
        self.artifacts = dict(sources)
        self.sources = set(sources)
        self.tasks = tasks
        self.mode = mode
        self.cache = {}
        self._initialise()

    def _execute(self, task):
        reader = Reads(self.artifacts, "fields" if self.mode in {"fields", "contracts", "proposed"} else "whole")
        result = task.run(reader)
        self.artifacts[task.name] = result
        self.cache[task.name] = {"trace": reader.trace, "fields": reader.actual_fields,
                                 "output": snapshot(result)}

    def _initialise(self):
        for task in self.tasks:
            self._execute(task)

    def update(self, replacements):
        changed = set(replacements)
        self.artifacts.update(replacements)
        actions, certificates_checked = [], 0
        structural_dirty = set(changed)
        for task in self.tasks:
            old = self.cache[task.name]
            if self.mode == "graph":
                dirty = any(source in structural_dirty for source, _ in old["trace"])
            else:
                dirty = False
                # Check all recorded paths. Certificates contain immutable
                # values, so mutation via another alias is detected too.
                for (source, path), value in old["trace"].items():
                    certificates_checked += 1
                    if snapshot(field_value(self.artifacts[source], path)) != value:
                        dirty = True
            if dirty:
                self._execute(task)
                same = self.cache[task.name]["output"] == old["output"]
                actions.append({"node": task.name, "contract": task.is_contract,
                                "output_equal": same, "reads": self.cache[task.name]["fields"]})
                if self.mode == "graph" or not same:
                    structural_dirty.add(task.name)
        return {"mode": self.mode, "recomputed": [a["node"] for a in actions],
                "producer_runs": sum(not a["contract"] for a in actions),
                "contract_runs": sum(a["contract"] for a in actions),
                "certificate_comparisons": certificates_checked,
                "actions": actions,
                "outputs": {task.name: self.cache[task.name]["output"] for task in self.tasks}}


def compare(sources, replacements, tasks):
    rows = []
    reference = None
    for mode in ("graph", "whole", "fields", "contracts", "proposed"):
        engine = Engine(sources, tasks, mode)
        row = engine.update(replacements)
        outputs = row.pop("outputs")
        if reference is None:
            reference = outputs
        row["equals_full_recompute"] = outputs == reference
        rows.append(row)
    # Full replay uses the same task definitions, no hand-coded result oracle.
    replay = Engine({**sources, **replacements}, tasks, "fields")
    expected = {task.name: replay.cache[task.name]["output"] for task in tasks}
    assert reference == expected
    assert all(row["equals_full_recompute"] for row in rows)
    assert rows[-1]["recomputed"] == rows[-2]["recomputed"] == rows[-3]["recomputed"]
    return rows
