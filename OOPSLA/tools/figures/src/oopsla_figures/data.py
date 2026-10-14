"""Load and verify display data without importing or executing experiments."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

FIGURE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = FIGURE_ROOT.parents[1]
EXPERIMENT_ROOT = PROJECT_ROOT / "experiments"
ARTIFACTS = (
    "code_matrices", "layout_positions", "noise_model", "stim_circuit",
    "detector_error_model", "logical_observables", "decoder_output",
)
DIMENSIONS = ("code", "extractor", "arch", "noise", "decoder")
STRATEGIES = (
    "config_diff", "logbook", "declarative_naive",
    "declarative_omniscient", "checker", "full_rerun",
)
Z95 = 1.959963984540054


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def wilson(errors: int, samples: int) -> tuple[float, float]:
    if not 0 <= errors <= samples or samples <= 0:
        raise ValueError("Invalid binomial event counts")
    p = errors / samples
    denominator = 1 + Z95**2 / samples
    center = (p + Z95**2 / (2 * samples)) / denominator
    half = Z95 * math.sqrt(p * (1 - p) / samples + Z95**2 / (4 * samples**2)) / denominator
    return max(0, center - half), min(1, center + half)


def verify_rate(record: dict) -> None:
    if not math.isclose(record["errors"] / record["shots"], record["rate"], abs_tol=1e-12):
        raise ValueError("Recorded error rate differs from its event counts")
    interval = wilson(record["errors"], record["shots"])
    if not all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(
        interval, (record["wilson95_low"], record["wilson95_high"])
    )):
        raise ValueError("Historical Wilson interval differs from registered formula")


def load_data() -> dict:
    names = ("dynamic_impact", "practice_comparison", "semantic_replacements", "silent_error")
    sources = {name: EXPERIMENT_ROOT / f"{name}.json" for name in names}
    raw = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in sources.items()}
    registered = json.loads((PROJECT_ROOT / "tools/figures/data/input-hashes.json").read_text(encoding="utf-8"))
    expected = {Path(item["path"]).name: item["sha256"] for item in registered["input_sha256"]}
    source_hashes = {name: {"path": str(path), "sha256": sha256(path)} for name, path in sources.items()}
    for item in source_hashes.values():
        if item["sha256"] != expected[Path(item["path"]).name]:
            raise ValueError(f"Experiment source has changed: {item['path']}")

    dynamic = raw["dynamic_impact"]
    selected = {item["name"]: item for item in dynamic["substitutions"] if item["name"] in DIMENSIONS}
    if len(selected) != 5 or dynamic["metadata"]["artifact_owner"]["logical_observables"] != "extractor":
        raise ValueError("Dynamic comparison selection or artifact ownership changed")
    owner = dynamic["metadata"]["artifact_owner"]
    matrices = []
    for model in ("source_faithful_cone", "source_faithful_coord", "dataflow_cone"):
        rows = []
        for dimension in DIMENSIONS:
            item = selected[dimension]
            if set(item["changed_artifacts"]) | set(item["unchanged_artifacts"]) != set(ARTIFACTS):
                raise ValueError("Dynamic result is missing a measured artifact")
            if set(item["changed_artifacts"]) & set(item["unchanged_artifacts"]):
                raise ValueError("Artifact cannot be both changed and unchanged")
            nodes = item["predicted_nodes_to_rerun"][model]
            cells = [{"artifact": artifact, "changed": artifact in item["changed_artifacts"],
                      "predicted": owner[artifact] in nodes} for artifact in ARTIFACTS]
            rows.append({"dimension": dimension, "cells": cells})
        matrices.append({"model": model, "rows": rows})

    practice = raw["practice_comparison"]
    denominator = sum(sum(bool(changed) for changed in row["changed"].values())
                      for row in practice["ground_truth"])
    if denominator != 43 or len(practice["sequence"]) != 12:
        raise ValueError("The registered sequence or miss-rate denominator changed")
    strategies = []
    for key in STRATEGIES:
        item = practice["strategies"][key]
        totals = item["totals"]
        misses = [len(step["missed"]) for step in item["per_step"]]
        if sum(misses) != totals["missed"]:
            raise ValueError("Per-step misses disagree with strategy totals")
        if not math.isclose(item["miss_rate"], totals["missed"] / denominator, abs_tol=5.1e-5):
            raise ValueError("Stored rounded miss rate differs from total")
        strategies.append({"key": key, "missed": totals["missed"],
                           "miss_rate": totals["missed"] / denominator,
                           "builds": totals["builds"], "over_rebuilds": totals["over_rebuilds"],
                           "changed_rebuilt": totals["builds"] - totals["over_rebuilds"],
                           "step_misses": misses})
    if practice["strategies"]["checker"]["per_step"] != practice["strategies"]["declarative_omniscient"]["per_step"]:
        raise ValueError("The checker and complete declaration no longer produce equal steps")

    semantic = raw["semantic_replacements"]
    if semantic["metadata"]["shots"] != 12000:
        raise ValueError("Physical shot count changed")
    physical = []
    for item in semantic["substitutions"]:
        if item["dimension"] not in ("extractor", "arch", "noise", "decoder"):
            continue
        rates = {}
        for role in ("base", "alt"):
            record = item["rate"][role]
            verify_rate(record)
            if record["shots"] != 144000:
                raise ValueError("Per-bit observation count changed")
            if not math.isclose(record["any_observable_errors"] / 12000,
                                record["any_observable_rate"], abs_tol=1e-12):
                raise ValueError("Any-observable rate differs from shot-level counts")
            rates[role] = {**record, "any_interval": wilson(record["any_observable_errors"], 12000)}
        physical.append({"dimension": item["dimension"], "rates": rates})

    silent = raw["silent_error"]
    dem = silent["stale_dem_cases"]
    if len(dem) != 4 or silent["metadata"]["shots"] != 9600:
        raise ValueError("Cache experiment selection changed")
    cache = []
    for item in dem:
        verify_rate(item["fresh"])
        verify_rate(item["stale"])
        if item["individual_predictions_total"] != 115200 or not math.isclose(
            item["individual_predictions_differing"] / item["individual_predictions_total"],
            item["individual_fraction_changed"], abs_tol=1e-12
        ):
            raise ValueError("Prediction difference fraction differs from its counts")
        cache.append({"label": item["label"], "fresh": item["fresh"], "stale": item["stale"],
                      "different": item["individual_predictions_differing"],
                      "total": item["individual_predictions_total"],
                      "percent_different": 100 * item["individual_fraction_changed"]})
    circuit = silent["stale_circuit_cases"][0]
    cached = silent["cached_predictions"]
    for correct, stale in ((circuit["declared"], circuit["consumed"]), (cached["correct"], cached["base"])):
        verify_rate(correct)
        verify_rate(stale)
        cache.append({"fresh": correct, "stale": stale})
    return {"sources": source_hashes, "figure2": matrices,
            "figure3": {"denominator": denominator, "strategies": strategies, "sequence": practice["sequence"]},
            "figure4": physical, "figure5": cache, "wilson_z": Z95}
