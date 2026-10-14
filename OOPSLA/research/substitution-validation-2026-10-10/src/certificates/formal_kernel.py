"""Tiny finite semantics and independent certificate checker.

The checker is intentionally separate from source_flow.py. It validates a
restricted certificate language by concrete finite execution; it makes no
claim about arbitrary Python.
"""
from dataclasses import dataclass
from itertools import product


LABELS = ("structure", "probability")
DOMAIN = (0, 1, 2)


class Reject(ValueError):
    pass


@dataclass(frozen=True)
class Emit:
    label: str
    value: int


@dataclass(frozen=True)
class Copy:
    label: str


@dataclass(frozen=True)
class Combine:
    left: object
    right: object


@dataclass(frozen=True)
class If:
    label: str
    yes: tuple
    no: tuple


@dataclass(frozen=True)
class Return:
    fields: tuple


@dataclass(frozen=True)
class Program:
    body: tuple


def _label(name):
    if name not in LABELS:
        raise Reject("unknown label")


def value(expr, env):
    if isinstance(expr, Emit):
        _label(expr.label)
        if expr.value not in DOMAIN:
            raise Reject("value outside finite domain")
        return expr.value
    if isinstance(expr, Copy):
        _label(expr.label)
        return env[expr.label]
    if isinstance(expr, Combine):
        return (value(expr.left, env) + value(expr.right, env)) % len(DOMAIN)
    raise Reject("bad expression")


def execute(program, env):
    if not isinstance(program, Program):
        raise Reject("bad program")
    out = {"structure": None, "probability": None}

    def block(nodes, require_return=False):
        for node in nodes:
            if isinstance(node, Emit):
                _label(node.label); out[node.label] = value(node, env)
            elif isinstance(node, If):
                _label(node.label)
                branch_result = block(node.yes if env[node.label] else node.no)
                if branch_result is not None:
                    return branch_result
            elif isinstance(node, Return):
                if tuple(node.fields) != LABELS:
                    raise Reject("return must expose both fields")
                return dict(out)
            else:
                raise Reject("unsupported statement")
        if require_return:
            raise Reject("missing return")
        return None

    result = block(program.body, require_return=True)
    if any(result[label] is None for label in LABELS):
        raise Reject("uninitialized output")
    return result


def check(program_old, program_new, certificate):
    """Independent finite checker; certificate cannot skip concrete checks."""
    accepted = True
    witnesses = []
    for structure, probability in product(DOMAIN, repeat=2):
        env = {"structure": structure, "probability": probability}
        try:
            old, new = execute(program_old, env), execute(program_new, env)
        except (Reject, KeyError) as error:
            return {"accepted": False, "reason": str(error), "witnesses": witnesses}
        if old["structure"] != new["structure"]:
            accepted = False
            witnesses.append({"env": env, "old": old, "new": new})
    if certificate.get("projection") != ("structure",):
        return {"accepted": False, "reason": "certificate projection is not structure", "witnesses": witnesses}
    return {"accepted": accepted, "reason": "finite concrete relation checked",
            "witnesses": witnesses, "input_count": len(DOMAIN) ** 2}
