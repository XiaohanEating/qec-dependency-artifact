"""Recognize a tiny, explicit Python fragment for binary linear observers.

    def f(bundle, faults): return (faults @ bundle.h.T) % 2

Only two positional arguments, one return, ndarray matmul and literal modulo
two are supported. Object overloading, globals, decorators and helper calls
are excluded. This is a restricted translation, not general Python analysis.
"""
import ast
import hashlib
import inspect
import textwrap
import numpy as np
from .model import validate_fault_input
from .checker import check_relation
from dataclasses import dataclass


@dataclass(frozen=True)
class Lowered:
    status: str
    field: str | None
    source_sha256: str
    reason: str


def lower_linear_source(source):
    digest = hashlib.sha256(source.encode()).hexdigest()
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return Lowered('unknown', None, digest, 'syntax outside supported fragment')
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        return Lowered('unknown', None, digest, 'expected one plain function')
    f = tree.body[0]
    args = f.args
    if (f.decorator_list or len(args.args) != 2 or args.posonlyargs or args.kwonlyargs
            or args.defaults or args.kw_defaults or args.vararg or args.kwarg
            or f.returns is not None or any(a.annotation is not None for a in args.args)
            or len({a.arg for a in args.args}) != 2
            or len(f.body) != 1 or not isinstance(f.body[0], ast.Return)):
        return Lowered('unknown', None, digest, 'unsupported function envelope')
    expr = f.body[0].value
    if not (isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Mod)
            and isinstance(expr.right, ast.Constant) and type(expr.right.value) is int and expr.right.value == 2):
        return Lowered('unknown', None, digest, 'not binary modular action')
    action = expr.left
    if not (isinstance(action, ast.BinOp) and isinstance(action.op, ast.MatMult)
            and isinstance(action.left, ast.Name) and action.left.id == args.args[1].arg):
        return Lowered('unknown', None, digest, 'unexpected fault input')
    operand = action.right
    if not (isinstance(operand, ast.Attribute) and operand.attr == 'T'
            and isinstance(operand.value, ast.Attribute) and operand.value.attr in ('h', 'logical')
            and isinstance(operand.value.value, ast.Name) and operand.value.value.id == args.args[0].arg):
        return Lowered('unknown', None, digest, 'unsupported matrix expression')
    return Lowered('accepted', operand.value.attr, digest, 'translated to binary linear observer')


def lower_callable(function):
    return lower_linear_source(inspect.getsource(function))


def generate_consumer_evidence(lowered, input_transport):
    if lowered.status != 'accepted':
        return {'status': 'unknown', 'reason': lowered.reason}
    return {'status': 'generated', 'rule': 'binary-matvec-coordinate-transport-v1',
            'field': lowered.field, 'consumer_source_sha256': lowered.source_sha256,
            'fault_transport': bool(input_transport)}


def verify_consumer_evidence(actual_source, certificate, producer_verdict, *,
                            old_bundle=None, new_bundle=None, old_faults=None,
                            new_faults=None, permutation=None, producer_certificate=None):
    # Check the source again independently; generator cannot add a field/rule.
    actual = lower_linear_source(actual_source)
    if actual.status != 'accepted' or certificate.get('status') != 'generated':
        return 'unknown'
    if (certificate.get('rule') != 'binary-matvec-coordinate-transport-v1'
            or certificate.get('field') != actual.field
            or certificate.get('consumer_source_sha256') != actual.source_sha256):
        return 'rejected'
    if producer_verdict.status != 'accepted':
        return producer_verdict.status
    if certificate.get('fault_transport') is not True:
        return 'rejected'
    if any(value is None for value in (old_bundle, new_bundle, old_faults, new_faults, permutation, producer_certificate)):
        return 'unknown'
    checked = check_relation(old_bundle, new_bundle, producer_certificate)
    if checked.status != 'accepted':
        return checked.status
    if permutation != producer_certificate.get('permutation'):
        return 'rejected'
    try:
        validate_fault_input(old_bundle, old_faults)
        validate_fault_input(new_bundle, new_faults)
        if len(permutation) != old_bundle.priors.size or sorted(permutation) != list(range(old_bundle.priors.size)):
            return 'rejected'
        if not np.array_equal(new_faults, old_faults[:, permutation]):
            return 'rejected'
    except (ValueError, TypeError, IndexError):
        return 'rejected'
    return 'accepted'
