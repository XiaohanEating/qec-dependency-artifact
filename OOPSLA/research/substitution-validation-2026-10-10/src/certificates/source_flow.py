"""Finite abstract dependency interpretation for the real QUITS converter.

Probability sources are DEM args_copy; structure sources are targets and counts.
The analysis includes control dependence, mutable-container aliases, local
functions and whitelisted pure library primitives. Unsupported syntax/calls
raise rather than receive an optimistic summary. This is a proof prototype
for the stated abstract semantics, not a verified arbitrary-Python analyzer.
"""
import ast
from dataclasses import dataclass


class Unsupported(ValueError):
    pass


@dataclass(frozen=True)
class Value:
    deps: frozenset = frozenset()
    refs: frozenset = frozenset()
    kind: str = ""
    items: tuple = ()


def union(*values):
    return Value(frozenset().union(*(v.deps for v in values)),
                 frozenset().union(*(v.refs for v in values)))


class Flow:
    PURE = {"len", "sum", "frozenset", "int", "range", "np.array", "np.zeros",
            "np.ones", "csc_matrix"}

    def __init__(self, source):
        self.tree = ast.parse(source)
        self.functions = {n.name: n for n in self.tree.body if isinstance(n, ast.FunctionDef)}
        self.scopes = {name: {"np": Value(kind="trusted-module")}
                       for name in self.functions}
        self.heap = {}
        self.calls = []
        self.branches = []
        self.writes = []
        self.depth = 0

    def labels(self, v):
        return v.deps | frozenset().union(*(self.heap.get(r, frozenset()) for r in v.refs))

    def allocate(self, node, v):
        ref = (id(node), self.depth)
        self.heap[ref] = self.heap.get(ref, frozenset()) | self.labels(v)
        return Value(v.deps, frozenset({ref}), v.kind, v.items)

    def expr(self, node, env):
        if isinstance(node, ast.Constant):
            return Value()
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise Unsupported("Unbound dynamic value: " + node.id)
            return env[node.id]
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            vs = tuple(self.expr(x, env) for x in node.elts)
            if not isinstance(node, ast.Tuple) and any(v.refs for v in vs):
                raise Unsupported("Nested mutable-container escape")
            v = Value(union(*vs).deps, union(*vs).refs, items=vs)
            return self.allocate(node, v) if not isinstance(node, ast.Tuple) else v
        if isinstance(node, ast.Dict):
            vs = [self.expr(x, env) for x in node.keys + node.values if x]
            if any(v.refs for v in vs):
                raise Unsupported("Nested mutable-container escape")
            return self.allocate(node, union(*vs))
        if isinstance(node, ast.Attribute):
            parent = self.expr(node.value, env)
            return Value(self.labels(parent), kind=parent.kind)
        if isinstance(node, ast.Subscript):
            p, k = self.expr(node.value, env), self.expr(node.slice, env)
            return Value(self.labels(p) | self.labels(k))
        if isinstance(node, (ast.BinOp, ast.BoolOp, ast.Compare, ast.UnaryOp)):
            vs = [self.expr(c, env) for c in ast.iter_child_nodes(node)
                  if isinstance(c, ast.expr)]
            return Value(frozenset().union(*(self.labels(v) for v in vs)))
        if isinstance(node, ast.IfExp):
            vs = [self.expr(n, env) for n in (node.test, node.body, node.orelse)]
            return Value(frozenset().union(*(self.labels(v) for v in vs)))
        if isinstance(node, ast.Call):
            return self.call(node, env)
        if isinstance(node, ast.GeneratorExp):
            local = dict(env)
            for g in node.generators:
                if g.ifs or g.is_async:
                    raise Unsupported("Filtered/async comprehension")
                self.assign(g.target, self.expr(g.iter, local), local, frozenset())
            return self.expr(node.elt, local)
        raise Unsupported("Expression: " + type(node).__name__)

    def call(self, node, env):
        caller_pc = self.pc
        name = ast.unparse(node.func)
        args = [self.expr(a, env) for a in node.args]
        args += [self.expr(k.value, env) for k in node.keywords]
        if name in self.functions or (name in env and env[name].kind.startswith("function:")):
            fn_name = name if name in self.functions else env[name].kind.split(":")[1]
            fn = self.functions[fn_name]
            parameters = [a.arg for a in fn.args.args]
            if fn.args.vararg or fn.args.kwarg or fn.args.kwonlyargs or fn.args.defaults:
                raise Unsupported("Function variadic/default arguments")
            if len(node.args) > len(parameters):
                raise Unsupported("Function arity/defaults")
            bindings = dict(zip(parameters, args[:len(node.args)]))
            for keyword, value in zip(node.keywords, args[len(node.args):]):
                if keyword.arg not in parameters or keyword.arg in bindings:
                    raise Unsupported("Invalid or expanded keyword arguments")
                bindings[keyword.arg] = value
            if set(bindings) != set(parameters):
                raise Unsupported("Missing function argument")
            if self.depth >= 8:
                raise Unsupported("Recursive call")
            self.calls.append(fn_name)
            local = dict(self.scopes[fn_name])
            local.update(bindings)
            self.depth += 1
            result = self.block(fn.body, local, caller_pc)
            self.depth -= 1
            return result or Value()
        if isinstance(node.func, ast.Attribute):
            owner = self.expr(node.func.value, env) if name not in self.PURE else Value()
            method = node.func.attr
            if owner.kind == "dem" and method == "flattened":
                return Value(frozenset({"structure"}), kind="instruction")
            if owner.kind == "instruction" and method == "args_copy":
                return Value(frozenset({"probability"}))
            if owner.kind == "instruction" and method == "targets_copy":
                return Value(frozenset({"structure"}), kind="target")
            if owner.kind == "target" and method in {"is_relative_detector_id", "is_logical_observable_id"}:
                return Value(frozenset({"structure"}))
            if method in {"append"}:
                if any(a.refs for a in args):
                    raise Unsupported("Nested mutable-container escape")
                self.mutate(owner, union(*args), caller_pc)
                return Value()
            if method in {"items", "keys", "values"}:
                # Mutable children are rejected on every store, so iteration
                # returns scalar labels, not an alias to the parent container.
                return Value(self.labels(owner))
        if name in self.PURE:
            v = Value(frozenset().union(*(self.labels(a) for a in args)))
            return self.allocate(node, v) if name in {"np.array", "np.zeros", "np.ones"} else v
        if name == "print":
            # Logging is outside the returned artifact relation, but is recorded.
            self.calls.append("print [unobserved logging]")
            return Value()
        raise Unsupported("Unknown call: " + name)

    def mutate(self, target, value, pc):
        labels = self.labels(value) | pc
        for r in target.refs:
            self.heap[r] = self.heap.get(r, frozenset()) | labels
        self.writes.append(sorted(labels))

    def assign(self, target, value, env, pc):
        if isinstance(target, ast.Name):
            if value.items and any(item.refs for item in value.items):
                raise Unsupported("Stored tuple containing mutable aliases")
            previous = env.get(target.id)
            env[target.id] = Value(value.deps | pc, value.refs, value.kind, value.items)
            if previous is not None:
                for scope in self.scopes.values():
                    if scope.get(target.id) == previous:
                        scope[target.id] = env[target.id]
        elif isinstance(target, (ast.Tuple, ast.List)):
            items = value.items if len(value.items) == len(target.elts) else [value] * len(target.elts)
            for t, v in zip(target.elts, items):
                self.assign(t, v, env, pc)
        elif isinstance(target, ast.Subscript):
            if value.refs:
                raise Unsupported("Nested mutable-container escape")
            owner = self.expr(target.value, env)
            key = self.expr(target.slice, env)
            self.mutate(owner, Value(self.labels(value) | self.labels(key)), pc)
        else:
            raise Unsupported("Assignment target")

    def block(self, statements, env, pc):
        for node in statements:
            self.pc = pc
            if isinstance(node, ast.FunctionDef):
                self.functions[node.name] = node
                self.scopes[node.name] = dict(env)
                env[node.name] = Value(kind="function:" + node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                if node.value is None:
                    continue
                v = self.expr(node.value, env)
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    self.assign(target, v, env, pc)
            elif isinstance(node, ast.AugAssign):
                v = union(self.expr(node.target, env), self.expr(node.value, env))
                self.assign(node.target, v, env, pc)
            elif isinstance(node, ast.Expr):
                self.expr(node.value, env)
            elif isinstance(node, ast.If):
                cond = self.labels(self.expr(node.test, env))
                self.branches.append({"line": node.lineno, "deps": sorted(cond)})
                left, right = dict(env), dict(env)
                ra = self.block(node.body, left, pc | cond)
                rb = self.block(node.orelse, right, pc | cond)
                for key in left.keys() | right.keys():
                    a, b = left.get(key, Value()), right.get(key, Value())
                    if a == b:
                        env[key] = a
                    else:
                        env[key] = union(a, b)
                if ra is not None or rb is not None:
                    # A conditional return affects all future control flow.
                    raise Unsupported("Conditional return")
            elif isinstance(node, ast.For):
                iterable = self.expr(node.iter, env)
                zero = dict(env)
                # Taints form a finite lattice. Iterate to an actual fixed point.
                for _ in range(32):
                    before = (dict(env), dict(self.heap))
                    self.assign(node.target, iterable, env, pc)
                    self.block(node.body, env, pc | self.labels(iterable))
                    for key, original in {**zero, **before[0]}.items():
                        current = env.get(key, original)
                        if current != original:
                            merged = union(current, original)
                            env[key] = Value(merged.deps, merged.refs,
                                             current.kind if current.kind == original.kind else "")
                    if before == (env, self.heap):
                        break
                else:
                    raise Unsupported("Loop analysis did not converge")
                if node.orelse:
                    raise Unsupported("Loop else")
            elif isinstance(node, ast.Return):
                v = self.expr(node.value, env)
                # Resolve heap dependencies before local scope disappears.
                if v.items:
                    return Value(items=tuple(Value(self.labels(x) | pc, x.refs, x.kind, x.items) for x in v.items))
                return Value(self.labels(v) | pc, v.refs, v.kind, v.items)
            elif isinstance(node, (ast.Pass, ast.Raise)):
                if isinstance(node, ast.Raise) and "probability" in pc:
                    raise Unsupported("Probability-dependent failure")
            else:
                raise Unsupported("Statement: " + type(node).__name__)
        return None

    def analyze(self):
        env = {"dem": Value(frozenset({"structure"}), kind="dem"), "np": Value(kind="trusted-module")}
        result = self.block(self.functions["detector_error_model_to_matrix"].body, env, frozenset())
        deps = [sorted(v.deps) for v in result.items]
        return {"output_dependencies": deps,
                "probability_independent_structure": all("probability" not in ds for ds in deps[:2]),
                "branches": self.branches, "calls": sorted(set(self.calls)),
                "abstract_heap_locations": len(self.heap)}
