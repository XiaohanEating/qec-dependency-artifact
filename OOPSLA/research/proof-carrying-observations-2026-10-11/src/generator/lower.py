"""Strict lowering of Task lambda expressions from real research adapters.

No execution/imports and no optimistic fallback. IR operations require fixed
pure total semantics; Python input/type and binding obligations remain explicit.
"""
import ast

from kernel.terms import Term, call, constant, field, select


class Unknown(ValueError):
    pass


def lower(node, side, reader):
    if isinstance(node, ast.Constant):
        return constant(node.value)
    if isinstance(node, ast.Call):
        if (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                and node.func.value.id == reader and node.func.attr == "read"):
            if node.keywords or not node.args or not all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in node.args):
                raise Unknown("read requires fixed literal source and path")
            return field(".".join(a.value for a in node.args), side)
        raise Unknown("call requires separately verified fixed pure binding")
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        if not isinstance(node.ops[0], ast.Gt):
            raise Unknown("comparison operation")
        return call("scalar_gt", lower(node.left, side, reader), lower(node.comparators[0], side, reader))
    if isinstance(node, ast.IfExp):
        return select(*(lower(n, side, reader) for n in (node.test, node.body, node.orelse)))
    if isinstance(node, ast.Tuple):
        return Term("tuple", tuple(lower(x, side, reader) for x in node.elts))
    raise Unknown("syntax: " + type(node).__name__)


def tasks(source):
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Task":
            if len(node.args) < 2 or not isinstance(node.args[0], ast.Constant):
                continue
            name, consumer = node.args[0].value, node.args[1]
            if not isinstance(consumer, ast.Lambda):
                out.append((name, None, "named function requires separately validated lowering"))
                continue
            if (len(consumer.args.args) != 1 or consumer.args.kwarg or consumer.args.vararg
                    or consumer.args.kwonlyargs or consumer.args.defaults):
                out.append((name, None, "lambda signature")); continue
            try:
                old = lower(consumer.body, "old", consumer.args.args[0].arg)
                new = lower(consumer.body, "new", consumer.args.args[0].arg)
                out.append((name, (old, new), None))
            except Unknown as error:
                out.append((name, None, str(error)))
    return out
