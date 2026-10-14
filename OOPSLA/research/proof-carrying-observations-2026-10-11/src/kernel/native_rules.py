"""Fail-closed exact native syntax rules; independent of source_flow.

These rules prove stated mathematical transitions under fixed built-in/NumPy
semantics. Exact syntax matching is deliberately narrow and rejects variants.
"""
import ast
from fractions import Fraction


def stripped(node):
    """Annotations/docstrings have no role in the stated transition relation."""
    class Strip(ast.NodeTransformer):
        def visit_AnnAssign(self, n):
            return ast.Assign(targets=[n.target], value=n.value) if n.value is not None else None
        def visit_FunctionDef(self, n):
            n.returns = None
            for a in n.args.args:
                a.annotation = None
            n.body = [s for s in n.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
            return self.generic_visit(n)
    return ast.dump(Strip().visit(node), include_attributes=False)


HANDLE = '''def handle_error(prob, detectors, observables):
    dets = frozenset(detectors)
    obs = frozenset(observables)
    if dets not in dem_dict:
        dem_dict[dets] = len(dem_dict)
        priors.append(prob)
        Logical_dict[dem_dict[dets]] = obs
    else:
        syndrome_id = dem_dict[dets]
        priors[syndrome_id] = priors[syndrome_id] * (1 - prob) + prob * (1 - priors[syndrome_id])
'''

COMMUTE = '''def commute(x, z, n):
    x1 = x[:n]
    x2 = x[n:]
    z1 = z[:n]
    z2 = z[n:]
    return (x1 @ z2 % 2) ^ (x2 @ z1 % 2)
'''


def check_native_rule(source, function, rule):
    candidates = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == function]
    if len(candidates) != 1:
        return {"accepted": False, "reason": "missing or ambiguous function"}
    template = HANDLE if rule == "ordered_first_label_xor_fold" else COMMUTE if rule == "mod_two_bilinear" else None
    if template is None:
        return {"accepted": False, "reason": "unknown inference rule"}
    expected = ast.parse(template).body[0]
    matches = stripped(candidates[0]) == stripped(expected)
    return {"accepted": matches, "rule": rule,
            "reason": "exact native transition syntax" if matches else "unknown syntax variation",
            "premises": (["ordered target sequence preserved", "first observable retained", "same detector count and observable count", "all error p in (0,1/2)", "fixed built-ins and caller-owned dictionaries/lists"] if rule == "ordered_first_label_xor_fold" else
                         ["fixed integer ndarray semantics", "same n and array length", "no object dtype", "x and xprime agree modulo 2", "z and zprime agree modulo 2"])}


def probability_identity():
    # Coefficient-normalized polynomial check of 1-2(q xor p) factorization.
    left = {(0, 0): Fraction(1), (1, 0): Fraction(-2), (0, 1): Fraction(-2), (1, 1): Fraction(4)}
    factors = ({(0, 0): Fraction(1), (1, 0): Fraction(-2)},
               {(0, 0): Fraction(1), (0, 1): Fraction(-2)})
    right = {}
    for (i,j), a in factors[0].items():
        for (k,l), b in factors[1].items():
            right[(i+k,j+l)] = right.get((i+k,j+l), Fraction(0)) + a*b
    return left == right
