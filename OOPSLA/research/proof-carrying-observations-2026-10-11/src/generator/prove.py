"""Untrusted generator; every emitted derivation is checked independently."""
from kernel.checker import Step
from kernel.terms import Term


def normalize(term, relation):
    if term.op == "field" and term.atom[0] == "new" and term.atom[1] in relation:
        out = Term("field", atom=("old", term.atom[1]))
        return out, Step("relation", term, out)
    if not term.args:
        return term, Step("refl", term, term)
    children = tuple(normalize(t, relation)[1] for t in term.args)
    out = Term(term.op, tuple(c.after for c in children), term.atom)
    congruence = Step("congruence", term, out, children)
    if out.op == "if" and out.args[1] == out.args[2]:
        target = out.args[1]
        return target, Step("chain", term, target,
                            (congruence, Step("if_same", out, target)))
    return out, congruence


def prove(old, new, relation):
    target, derivation = normalize(new, relation)
    return derivation if target == old else None
