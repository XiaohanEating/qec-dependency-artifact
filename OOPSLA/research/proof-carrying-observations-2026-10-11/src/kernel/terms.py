"""Immutable first-order terms over arbitrary input domains."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Term:
    op: str
    args: tuple = ()
    atom: object = None


def field(name, side):
    return Term("field", atom=(side, name))


def constant(value):
    if not isinstance(value, (int, float, str, bool, type(None))):
        raise ValueError("constant must be immutable scalar")
    return Term("const", atom=value)


def call(name, *args):
    return Term("call", tuple(args), name)


def select(test, yes, no):
    return Term("if", (test, yes, no))
