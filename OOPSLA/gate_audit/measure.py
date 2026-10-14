"""QUITS boundary audit: static measurement of modification surface per dimension.

Reads the pinned QUITS source tree (third_party/) and, for each dimension's
standard change task (protocol.md), reports the packages that must be touched,
required abstract members, and registry points. Emits gate verdict.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

QUITS_SRC = Path(__file__).resolve().parents[2] / "third_party" / (
    "quits-0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452") / "src" / "quits"
OUT = Path(__file__).resolve().parent / "audit_results.json"

PACKAGES = ["qldpc_code", "layout", "noise", "decoder", "simulation", "api", "circuit"]


def list_package_files(pkg: str) -> list[str]:
    d = QUITS_SRC / pkg
    if not d.exists():
        return []
    return sorted(p.name for p in d.glob("*.py"))


def count_abstract_members(pkg: str, cls_pattern: str) -> dict:
    """For the main class in a package: count methods a subclass must implement."""
    d = QUITS_SRC / pkg
    if not d.exists():
        return {}
    result = {}
    for p in d.glob("*.py"):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and re.match(cls_pattern, node.name):
                raises = [m.name for m in node.body
                          if isinstance(m, ast.FunctionDef)
                          and any(isinstance(s, ast.Raise) for s in ast.walk(m))]
                if raises:
                    result[node.name] = {"file": p.name, "must_implement": raises}
    return result


def registry_points(pkg: str, key: str) -> list[str]:
    """Find dispatch/registration sites referencing a strategy name."""
    hits = []
    for p in (QUITS_SRC / pkg).glob("*.py") if (QUITS_SRC / pkg).exists() else []:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if key in text and ("get_builder" in text or "strategy" in text.lower()):
            hits.append(p.name)
    return hits


def main():
    code_modules = list_package_files("qldpc_code")
    audit = {
        "quits_src": str(QUITS_SRC),
        "packages_found": {p: list_package_files(p) for p in PACKAGES},
        "dimensions": {
            "code": {
                "task": "add one new code family module",
                "existing_family_modules": [f for f in code_modules if f not in ("base.py", "__init__.py")],
                "abstract_members_required": count_abstract_members("qldpc_code", r"QldpcCode|Code"),
                "touched_packages_est": ["qldpc_code", "circuit"],
            },
            "extraction": {
                "task": "add one new circuit strategy",
                "registry_points": registry_points("qldpc_code", "strategy"),
                "touched_packages_est": ["qldpc_code", "circuit"],
            },
            "architecture": {
                "task": "add one new topology/layout constraint",
                "layout_files": list_package_files("layout"),
                "touched_packages_est": ["layout"],
            },
            "noise": {
                "task": "add one new noise model",
                "noise_files": list_package_files("noise"),
                "touched_packages_est": ["noise"],
            },
            "decoder": {
                "task": "add one new decoder (e.g. BP-LSD as standalone)",
                "decoder_files": list_package_files("decoder"),
                "simulation_files": list_package_files("simulation"),
                "touched_packages_est": ["decoder", "simulation"],
            },
        },
    }
    OUT.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    for dim, info in audit["dimensions"].items():
        print(f"  {dim:12s} touched_est={info['touched_packages_est']}")
    print("NOTE: gate verdict (>70% coverage -> kill) is drawn from these numbers"
          " against the rubric in protocol.md — fill est_loc after the first two"
          " change tasks are actually executed on the pinned tree.")


if __name__ == "__main__":
    main()
