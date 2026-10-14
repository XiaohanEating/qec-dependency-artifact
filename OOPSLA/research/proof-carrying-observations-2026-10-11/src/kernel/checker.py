"""Independent proof-step checker; no source-flow or sampling dependencies.

Inference rules are reflexivity, congruence, declared relation substitution,
and if(t,x,x)=x for total evaluation. Symbols are uninterpreted pure total
functions. Arbitrary Python binding is outside this kernel's semantics.
"""
from dataclasses import dataclass

from .terms import Term
from .context import valid_context


@dataclass(frozen=True)
class Step:
    rule: str
    before: Term
    after: Term
    children: tuple = ()


def validate_term(term):
    if not isinstance(term, Term) or term.op not in {"const", "field", "call", "tuple", "if"}:
        return False
    if term.op == "field":
        return not term.args and isinstance(term.atom, tuple) and len(term.atom) == 2 and term.atom[0] in {"old", "new"}
    if term.op == "const":
        return not term.args and isinstance(term.atom, (int, float, str, bool, type(None)))
    if term.op == "if" and len(term.args) != 3:
        return False
    if term.op == "call" and not isinstance(term.atom, str):
        return False
    return all(validate_term(t) for t in term.args)


def check_step(step, equal_fields):
    if not isinstance(step, Step) or not validate_term(step.before) or not validate_term(step.after):
        return False
    left, right = step.before, step.after
    if step.rule == "refl":
        return left == right and not step.children
    if step.rule == "relation":
        return (left.op == right.op == "field" and not step.children and
                left.atom == ("new", right.atom[1]) and right.atom[0] == "old" and
                right.atom[1] in equal_fields)
    if step.rule == "congruence":
        return (left.op == right.op and left.atom == right.atom and
                len(left.args) == len(right.args) == len(step.children) and
                all(child.before == a and child.after == b and check_step(child, equal_fields)
                    for a, b, child in zip(left.args, right.args, step.children)))
    if step.rule == "if_same":
        return not step.children and left.op == "if" and left.args[1] == left.args[2] == right
    if step.rule == "chain":
        if not step.children:
            return False
        cursor = left
        for child in step.children:
            if child.before != cursor or not check_step(child, equal_fields):
                return False
            cursor = child.after
        return cursor == right
    return False


def check_certificate(old, new, relation, certificate, *, producer_hash=None,
                      consumer_hash=None, snapshot_id=None, expected_snapshot=None,
                      actual_context=None, required_context=None):
    # Explicit relation is an assumption, not something the proof can add.
    if not isinstance(relation, frozenset) or not all(isinstance(k, str) for k in relation):
        return False
    if not producer_hash or not consumer_hash or snapshot_id is None or snapshot_id != expected_snapshot:
        return False
    if not valid_context(actual_context, required_context):
        return False
    return (certificate.before == new and certificate.after == old and
            check_step(certificate, relation))
