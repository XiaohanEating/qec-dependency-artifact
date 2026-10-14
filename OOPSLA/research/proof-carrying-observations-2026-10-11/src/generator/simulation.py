"""Untrusted candidate extraction for the actual native Simulation source."""
import ast
import hashlib


def candidate(source, parameter):
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    loads = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == parameter and isinstance(node.ctx, ast.Load):
            current = node
            while current in parents and not isinstance(current, ast.Call):
                current = parents[current]
            loads.append({"line": node.lineno, "call_line": current.lineno if isinstance(current, ast.Call) else None})
    return {"source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "parameter": parameter, "loads": sorted(loads, key=lambda r:r["line"]),
            "rule": "noise-payload-erasure-v1"}
