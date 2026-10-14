"""Pivot 后的第一版形式化核心（OOPSLA PIVOT_NOTE §3 §4）。

语言语义层：对一个"运行时可组装"的组件系统，给出 spec → artifact 的指派
[[c]]，并使"替换组件 x"这件事既可陈述又可局部检查：

- 组件带声明读集合 R(c) 与义务 contract(artifact -> bool)；
- Definition（context-independence）：c 对 R(c) 纯；
- Theorem 1（local substitutability）：x, x' context-independent、签名相同、
  在 R(x) 上逐点相等 ⇒ assembly A[x'/x] 中 N∖({x}∪cone(x)) 的节点 artifact
  完全相同（x 自身在 (C4) 下亦不变，见 PIVOT_NOTE §6.1 Step 1），cone 内
  只需重跑并重验局部义务；
- Lemma 2（spec 决定 artifact）：全组件 context-independent 时，
  spec 域坐标一致的文档指派相同 artifact；
- Theorem 3（隐藏依赖原则可检测）：非纯组件 ⇒ 存在 env ~_{R(c)} env'
  使指派不同，判别性有限域上探测可报出 observed_reads ⊄ declared_reads。

P0 修复记录（2026-10-08）：
- P0-1：produce 的一般模型——produce : Spec × (前驱 artifact) → Artifact，
  实现与 PIVOT_NOTE §6 证明对齐（arity-1 的 produce 仍兼容）。
- P0-2：substitution_invariance_report 实际执行替换并比较 artifact。
- P0-3：Domain 扩到 QUITS 全部 code family（BB/HGP/mitten/BPC/LCS/QLP）；
  读集合仍为手工建模（完全自动化留作后续）。
- P0-4：detect_hidden_dependency 改为贪心最小扩展，修复 over-approximation 漏报。

P1/P2 修复记录（同日）：
- P1-4：cone 的严格定义（含环情形）——见 Assembly.cone 的文档串；新增
  cycles() / is_dag()（迭代 Tarjan）；evaluate 在环下抛异常；substitute 增加
  assembly_is_dag 这条 checker 条件（环下保守拒绝）。
- P2-3：DOMAIN["extractor"] 扩到源码实际支持的策略并集
  {cardinal, cardinalNSmerge, custom, hook_error_free, zxcoloration}
  （由 experiments/quant_evidence.py 自动解析，不手工断言）；新增
  DOMAIN_EXHAUSTIVE 逐坐标标注穷举性（arch/noise/decoder 为 PARTIAL）。

P2-2 动态半边 / P0-3 读集合自动提取（2026-10-09）：
- **P0-3 收尾**：读集合不再是手工建模。READ_SETS_FROM_SOURCE /
  ARTIFACT_READS_FROM_SOURCE / ASSEMBLY_EDGES_FROM_SOURCE 三张表由
  ``experiments/extract_read_sets.py`` 对 pinned QUITS 树做 AST 静态分析生成
  （组件粒度取自冻结的 gate_audit/protocol.md），并由
  ``experiments/test_quits_faithfulness.py`` 逐条锁定。手工声明与自动提取的
  **唯一**差异是 extractor 少了 noise 坐标（即 H3）。
- 新增 make_source_faithful_assembly()（自动提取的 R(c) + 自动导出的 DAG 边）；
  _mk_components 保留为**理想化对照基线**（每个组件只读自己的坐标）。
- **决策 1-4（2026-10-09，接上一轮）**：
  (1) 自动提取器定位为**交叉验证**，动态实测为 ground truth；
  (2) cone_table / artifact_invariance 的基线换成 make_source_faithful_assembly()，
      新增 theorem1_report()（一般模型下一次算全 (C1)-(C4)）与
      pointwise_equal_on_reads(..., inputs_for=)；
  (3) cone_table.make_quits_dataflow_assembly 补 ``arch <- code`` 边；
  (4) trigger-2 汇总在新基线上重算。
- 新增 ASSEMBLY_MODEL_SOURCES / BASELINE_ASSEMBLY / assembly_model_sources()：
  记录每个 assembly 的**读集合来源**与**边的来源**，实验脚本把它写进
  JSON metadata 与 Markdown 文件头，避免不同建模来源的数字被混读。
  cone 是**替换组件**的工作表；coordinate_impact 才是**改坐标**的影响面。
- 新增一般模型的 Definition：context_independence_with_inputs() /
  detect_hidden_dependency(..., inputs_for=) / predecessor_inputs() /
  Assembly.evaluate(spec, check_contracts=False)。没有它们，一个消费
  ``Layout(code)`` 这类 artifact 边的组件会被 arity-1 探测误报成 impure。
- 新增 coordinate_impact(A, coord)：**改坐标**的影响面
  （{x} ∪ {u : x ∈ R(u)} ∪ ⋃cone(v)），与 Theorem 1 的 cone（**替换组件**的
  影响面）是两个不同的量，见 PIVOT_NOTE §4.3。
- 新增 inadmissible_pairs() / admissible_spec()：把 H1（可组装性是隐藏的跨组件
  关系）从运行期 raise 变成**组装前可检查的义务**。

零三方依赖，可独立运行：python src/semantics.py
"""
from __future__ import annotations

import itertools
import sys
from dataclasses import dataclass, field

COORDINATES = ("code", "extractor", "arch", "noise", "decoder")


@dataclass(frozen=True)
class Spec:
    """Object =五维规格的有限乘积（value spec 组合）。"""
    code: str = "BB"
    extractor: str = "cardinal"
    arch: str = "free"
    noise: str = "SD6"
    decoder: str = "BP-OSD"

    def coords(self, names) -> dict:
        return {n: getattr(self, n) for n in names}


@dataclass
class Component:
    """带声明读集合与义务的标注函数。

    produce : Spec × (前驱 artifact 字典) → artifact（一般模型，PIVOT_NOTE §6）。
    也兼容 arity-1 的 produce : Spec → artifact（视为不依赖前驱）。

    ``coordinates`` is the coordinate set the component is *validated against*
    (Definition 3.3's ``R(c) ⊆ Coord``).  It defaults to the QUITS coordinate
    set so that every existing caller is unaffected; a second subject system
    with a different set of dimensions passes its own (``subject_system2.md``
    §4).  Nothing else in this module is specialised to QUITS.
    """
    name: str
    reads: tuple[str, ...]
    produce: callable
    contract: callable = None  # (artifact) -> bool；默认恒真
    writes: str = None
    coordinates: tuple[str, ...] = COORDINATES

    def __post_init__(self):
        if any(r not in self.coordinates for r in self.reads):
            raise ValueError(f"undeclared coordinate in reads={self.reads}")
        self.writes = self.name
        self.contract = self.contract or (lambda a: True)


@dataclass
class Assembly:
    """组件 DAG：name -> (Component, 依赖名列表)。assignment 按拓扑序求值。

    **模型要求（PIVOT_NOTE §6.0）**：`Assembly` 按定义是**有限 DAG**——指派
    `⟦A⟧` 靠"拓扑序归纳"定义。环（cycle）不在本文的形式模型里：
    `evaluate` 在检测到环时**抛异常**而不是给出一个任意（依赖遍历顺序的）
    结果；`cone` 在环下仍良定义（见 `cone` 的文档串），但 Theorem 1 的结论
    只对无环 assembly 陈述（见 `substitute` 的 `assembly_is_dag` 检查）。
    """
    nodes: dict[str, Component]
    edges: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def dependencies(self, name: str) -> tuple[str, ...]:
        return self.edges.get(name, ())

    def evaluate(self, spec: Spec, check_contracts: bool = True) -> dict[str, object]:
        """按拓扑序求值 ``⟦A⟧(spec)``。

        ``check_contracts=False`` 只用于**纯性探测**（``predecessor_inputs``）：
        探测要在整个有限域上枚举，其中必然包含 H1 意义上的**不可装配**的
        ``(code, extractor)`` 组合；此时我们关心的是 artifact 是否依赖未声明
        坐标，而不是该组合是否可装配。可装配性由 ``evaluate`` 默认路径的
        contract 检查负责。
        """
        if not self.is_dag():
            raise ValueError(
                "Assembly.evaluate: assembly contains a cycle; PIVOT_NOTE §6.0 "
                f"defines Assembly as a finite DAG.  cycles={self.cycles()}")
        order = self._topo_order()
        art: dict[str, object] = {}
        for n in order:
            inputs = {d: art[d] for d in self.dependencies(n)}
            art[n] = self._produce(self.nodes[n], spec, inputs)
            if check_contracts and not self.nodes[n].contract(art[n]):
                raise ValueError(f"contract violated: {n}")
        return art

    @staticmethod
    def _produce(c: Component, spec: Spec, inputs: dict) -> object:
        try:
            return c.produce(spec, inputs)
        except TypeError:
            return c.produce(spec)

    def cone(self, target: str) -> set[str]:
        """cone(target) = {u ∈ N : target ∈ Reach⁺(u)}——替换 target 需要重跑的节点上包络。

        **精确定义（含环情形，P1-4）**
        -----------------------------------
        记 `deps(u) = edges[u]`（"u 依赖谁"），`Reach⁺(u)` 为
        `u` 在**反向图**（边 `u → deps(u)`，即"被依赖 → 依赖者"）上从 `u`
        出发的可达点集，**排除长度 0 的路径**，即

            Reach⁺(u) = { v : 存在有向路径 u ⇝ v，长度 ≥ 1 }.

        于是 `cone(x) = { u ∈ N : x ∈ Reach⁺(u) } =` 反向图上从 `x` 出发的
        可达闭包。这一定义与 PIVOT_NOTE §6.0 的 `Reach(u)`（"u 的传递依赖集"）
        **互为对偶**：那里 `cone(x) = {u : x ∈ Reach(u)}` 且 `Reach(u)` 是
        `u` 沿依赖边的正向传递闭包；两个定义给出**同一个集合**
        （`x` 在 `u` 的依赖闭包中 ⟺ `u` 在 `x` 的反向依赖闭包中）。

        两条关键性质（对有环、无环都成立）：

        1. **终止性**：实现是带 `seen` 集合的工作表算法（DFS/BFS 迭代），
           每个节点至多入栈一次，因此即使边关系成环也**必然终止**，
           返回的是最小的传递闭包（不是无界搜索）。
        2. **`x ∈ cone(x)` ⟺ `x` 在某个有向环上**。无环时 `x ∉ cone(x)`
           （PIVOT_NOTE §6.1 Step 2 的基础情形即依赖这一点）；有环时，
           `x` 若在环上则环上每个节点都在 `cone(x)` 中——因为存在从 `x`
           出发回到 `x` 的路径，把"自身"重新纳入受影响集合。
           换言之：**环不会让 cone 变大，只会沿环"闭合"**。

        **为什么 Theorem 1 仍然只对无环 assembly 陈述**：环下 `⟦A⟧` 无法
        良定义（拓扑归纳失去良基），而不是 cone 定义有问题。`cone` 在环下
        良定义且可用于诊断（"这个替换的影响会绕回来"），但
        `substitute` 会因 `assembly_is_dag=False` 而**拒绝**给出
        "cone 外不变" 的结论。见 `cycles()` / `is_dag()`。
        """
        dependents: dict[str, set[str]] = {}
        for u, deps in self.edges.items():
            for d in deps:
                dependents.setdefault(d, set()).add(u)
        seen, stack = set(), [target]
        while stack:
            n = stack.pop()
            for u in dependents.get(n, ()):
                if u not in seen:
                    seen.add(u)
                    stack.append(u)
        return seen

    # -- cycle detection (iterative Tarjan SCC; cycle-safe by construction) ----

    def cycles(self) -> set[str]:
        """返回处于某个有向环上的节点集合（自环也算）。

        用迭代式 Tarjan 强连通分量：分量大小 > 1，或单点自环，则该分量内
        每个节点都在环上。迭代写法避免递归深度限制，且无环时 O(V+E)。
        """
        succ: dict[str, list[str]] = {n: [] for n in self.nodes}
        for u, deps in self.edges.items():
            succ.setdefault(u, [])
            for d in deps:
                if d in self.nodes:
                    succ[u].append(d)
        index: dict[str, int] = {}
        low: dict[str, int] = {}
        on_stack: set[str] = set()
        stack: list[str] = []
        result: set[str] = set()
        counter = 0

        for root in self.nodes:
            if root in index:
                continue
            # work item: (node, iterator over successors)
            work: list[tuple[str, int]] = [(root, 0)]
            index[root] = low[root] = counter
            counter += 1
            stack.append(root)
            on_stack.add(root)
            while work:
                v, pi = work[-1]
                if pi < len(succ.get(v, ())):
                    work[-1] = (v, pi + 1)
                    w = succ[v][pi]
                    if w not in index:
                        index[w] = low[w] = counter
                        counter += 1
                        stack.append(w)
                        on_stack.add(w)
                        work.append((w, 0))
                    elif w in on_stack:
                        low[v] = min(low[v], index[w])
                    continue
                # done with v
                if low[v] == index[v]:
                    comp: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        comp.append(w)
                        if w == v:
                            break
                    if len(comp) > 1 or v in succ.get(v, ()):
                        result.update(comp)
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
        return result

    def is_dag(self) -> bool:
        """有限 DAG？（PIVOT_NOTE §6.0 的模型要求）"""
        return not self.cycles()

    def _topo_order(self) -> list[str]:
        order, seen = [], set()

        def visit(n):
            if n in seen:
                return
            for d in self.dependencies(n):
                visit(d)
            seen.add(n)
            order.append(n)

        for n in self.nodes:
            visit(n)
        return order


# ---------------------------------------------------------------------------
# Definition / Lemmas / Theorems as executable operations
# ---------------------------------------------------------------------------

def _call_produce(c: Component, spec: Spec, inputs: dict | None = None) -> object:
    """统一调用入口：优先一般模型 (spec, inputs)，兼容 arity-1 的 produce。"""
    if inputs is None:
        inputs = {}
    try:
        return c.produce(spec, inputs)
    except TypeError:
        return c.produce(spec)


def _probe(c: Component, spec: Spec) -> str:
    """把 artifact 转成可哈希的规范字符串用于探测。"""
    return str(_call_produce(c, spec))


def observed_env_diff(component: Component, envs: list[Spec]) -> bool:
    """False ⇒ 在 envs 上探测不到显式读集合以外的依赖（over-approximation 下）。"""
    return _collisions(component, envs, set(component.reads)) > 0


def context_independence(component: Component, domain_values: dict[str, list],
                         spec_cls=Spec) -> bool:
    """Definition（arity-1 特例）：component 对 R(component) 纯 ⇒ 任何两个在
    R 上一致的 spec 给出相同 artifact。"""
    envs = _cartesian(domain_values, spec_cls)
    return not observed_env_diff(component, envs)


# --- the general model's Definition (P0-3, needed by the faithful assembly) ---
#
# `observed_env_diff` / `context_independence` above are the **arity-1** probe:
# they vary the whole spec with no predecessor artifacts.  A component that
# consumes another component's *artifact* (e.g. `Layout(code)`, or
# `get_codecap_pL(code, ...)`) is pure in the sense of Theorem 1 only when the
# predecessor artifact is also held fixed -- that is exactly the induction
# invariant of Step 2.  The two functions below implement the general-model
# Definition, so a component whose `produce` reads `inp[...]` (a DAG edge) is
# *not* falsely reported as impure.

def _inputs_key(inputs: dict | None) -> tuple:
    if not inputs:
        return ()
    return tuple(sorted((k, str(v)) for k, v in inputs.items()))


def observed_env_diff_with_inputs(component: Component, envs: list[Spec],
                                  inputs_for) -> bool:
    """False ⇒ 在 ``inputs_for(spec)`` 给定前驱 artifact 时，探测不到 R(c) 以外的依赖。"""
    return _collisions(component, envs, set(component.reads), inputs_for) > 0


def artifact_equal(left: object, right: object) -> bool:
    """Compare values directly; display strings are not semantic equality.

    Containers are compared recursively. Objects must provide meaningful ==;
    Array artifacts require identical shape and dtype before element equality.
    """
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            artifact_equal(left[k], right[k]) for k in left)
    if isinstance(left, (list, tuple)) and isinstance(right, type(left)):
        return len(left) == len(right) and all(
            artifact_equal(a, b) for a, b in zip(left, right))
    if hasattr(left, "shape") or hasattr(right, "shape"):
        if getattr(left, "shape", None) != getattr(right, "shape", None):
            return False
        if getattr(left, "dtype", None) != getattr(right, "dtype", None):
            return False
    result = left == right
    return bool(result.all()) if hasattr(result, "all") else bool(result)


def context_independence_with_inputs(component: Component, domain_values: dict[str, list],
                                     inputs_for, spec_cls=Spec) -> bool:
    """Definition（一般模型）：``s|R(c)`` 一致**且前驱 artifact 一致** ⇒ 输出相同。"""
    envs = _cartesian(domain_values, spec_cls)
    return not observed_env_diff_with_inputs(component, envs, inputs_for)


def predecessor_inputs(A: "Assembly", name: str):
    """``inputs_for`` closure: 前驱 artifact 由 ``A`` 在该 spec 上求值得到。

    ``check_contracts=False``：见 ``Assembly.evaluate`` 的说明——纯性探测必须
    在包含不可装配组合的整个有限域上跑完。
    """
    deps = A.dependencies(name)

    def inputs_for(spec: Spec) -> dict:
        if not deps:
            return {}
        art = A.evaluate(spec, check_contracts=False)
        return {d: art[d] for d in deps}

    return inputs_for


def _collisions(component: Component, envs: list[Spec], reads: set[str],
                inputs_for=None) -> int:
    """在 reads 上分组后，组内 artifact 不一致的总数（越小越纯）。"""
    # Coordinate values are keys; predecessor artifacts use their actual
    # equality relation. Opaque objects with equal str() stay distinct.
    keyed: dict[tuple, list] = {}
    for spec in envs:
        inputs = inputs_for(spec) if inputs_for else {}
        key = tuple(sorted(spec.coords(sorted(reads)).items()))
        groups = keyed.setdefault(key, [])
        group = next((g for g in groups if artifact_equal(g[0], inputs)), None)
        if group is None:
            group = (inputs, [])
            groups.append(group)
        output = _call_produce(component, spec, inputs)
        if not any(artifact_equal(output, old) for old in group[1]):
            group[1].append(output)
    return sum(len(g[1]) - 1 for groups in keyed.values() for g in groups)


def detect_hidden_dependency(component: Component, domain_values: dict[str, list],
                             inputs_for=None, coordinates=None,
                             spec_cls=Spec) -> dict:
    """Theorem 3：非纯 ⇒ 探测可报出 observed_reads ⊄ declared_reads。

    P0-4 修复：贪心最小扩展——从 declared 出发，每次加入能使组件变纯（或最大程度
    减少碰撞）的未声明坐标，直到纯或无可加。修复原 over-approximation：原实现只
    检查 declared ∪ {coord} 是否纯，若组件读了多个未声明坐标则全部漏报。

    P0-3 扩展：``inputs_for`` 是可选的前驱 artifact 供给函数（一般模型）。不传
    时退化为 arity-1 探测。

    ``coordinates`` defaults to the component's own coordinate set (Definition
    3.3); passing it explicitly lets a subject system probe against a
    different dimension set without touching this function.  ``spec_cls``
    likewise defaults to QUITS's five-coordinate ``Spec``.
    """
    envs = _cartesian(domain_values, spec_cls)
    declared = set(component.reads)

    def pure(reads: set[str]) -> bool:
        return _collisions(component, envs, reads, inputs_for) == 0

    if pure(declared):
        return {
            "declared_reads": sorted(declared),
            "observed_extensions": [],
            "observed_reads_subset_declared": True,
            "verdict": "pure",
        }

    universe = set(coordinates if coordinates is not None
                   else getattr(component, "coordinates", COORDINATES))
    ext: set[str] = set()
    remaining = universe - declared
    while remaining and not pure(declared | ext):
        # 优先找"一加就纯"的坐标；否则取减少碰撞最多的
        best = next((c for c in remaining if pure(declared | ext | {c})), None)
        if best is None:
            best = min(remaining,
                       key=lambda c: _collisions(component, envs,
                                                 declared | ext | {c}, inputs_for))
        ext.add(best)
        remaining.discard(best)

    return {
        "declared_reads": sorted(declared),
        "observed_extensions": sorted(ext),
        "observed_reads_subset_declared": False,
        "verdict": "impure (hidden reads)",
    }


def _cartesian(domain_values: dict[str, list], spec_cls=Spec) -> list:
    keys = sorted(domain_values)
    return [spec_cls(**dict(zip(keys, combo)))
            for combo in itertools.product(*[domain_values[k] for k in keys])]


def signature_ok(x: Component, x_prime: Component) -> bool:
    return x.reads == x_prime.reads and x.writes == x_prime.writes


def pointwise_equal_on_reads(x: Component, x_prime: Component,
                             domain_values: dict[str, list],
                             inputs_for=None, spec_cls=Spec) -> bool:
    """side condition：x 与 x' 在 R(x) 上逐点相等。

    ``inputs_for`` is the general-model closure from :func:`predecessor_inputs`:
    it supplies the *predecessor artifacts*, which are held fixed while the
    declared coordinates are varied (the induction invariant of
    PIVOT_NOTE §6.1 Step 2).  Without it this is the arity-1 probe, which is
    only meaningful for components that consume no DAG edge.
    """
    if x.reads != x_prime.reads:
        return False
    # Artifact inputs can vary through coordinates outside R(x). Enumerate
    # every full spec and its reachable predecessor inputs, never defaults.
    for spec in _cartesian(domain_values, spec_cls):
        inputs = inputs_for(spec) if inputs_for is not None else None
        if not artifact_equal(_call_produce(x, spec, inputs),
                              _call_produce(x_prime, spec, inputs)):
            return False
    return True


def memoize_inputs(inputs_for) -> "callable":
    """Wrap an ``inputs_for`` closure with a per-spec memo.

    ``theorem1_report`` probes the same component against the same finite
    domain three times ((C1), (C2), (C4)); each probe walks the whole domain
    and re-evaluates the assembly once per point.  The memo makes those three
    walks cost one instead of three.  It does not change any result:
    ``inputs_for`` is a deterministic function of the spec.
    """
    cache: dict = {}

    def memo(spec: Spec) -> dict:
        key = tuple(sorted(spec.__dict__.items()))
        if key not in cache:
            cache[key] = inputs_for(spec)
        return cache[key]

    return memo


def _pure_on(node: Component, domain_values: dict[str, list], inputs_for,
             spec_cls=Spec) -> bool:
    """``context_independence_with_inputs`` that never raises.

    On a cyclic assembly the predecessor artifacts cannot be produced at all
    (``Assembly.evaluate`` refuses), so purity cannot be *established*; we
    report False (the conservative answer) instead of propagating the cycle
    error out of the checker.
    """
    try:
        return context_independence_with_inputs(node, domain_values, inputs_for,
                                                spec_cls)
    except ValueError:
        return False


def substitute(A: Assembly, x: str, x_prime: Component,
               inputs_for=None) -> dict:
    """Theorem 1 的可执行化：检查 side condition，报 cone / 不变节点 / 重验节点。

    除 (C1)–(C4) 外，还检查一条**前提**：`assembly_is_dag`。PIVOT_NOTE §6.0
    把 assembly 定义为有限 DAG，Theorem 1 的证明是对拓扑序的归纳；环下
    `⟦A⟧` 不良定义，故 checker 在环上**不给**任何局部性结论（保守拒绝），
    尽管 `cone` 本身在环下仍良定义（见 `Assembly.cone` 的文档串 / P1-4）。

    ``inputs_for``（可选）把 (C2) 从 arity-1 探测升级为**一般模型**的探测
    （`context_independence_with_inputs`）。必须传，否则一个消费 DAG 边的
    组件（例如 `Layout(code)`）会被 arity-1 探测误报成 impure。见
    `theorem1_report`（推荐的入口：它把 (C1)–(C4) 一次算全）。
    """
    return theorem1_report(A, x, x_prime, inputs_for=inputs_for)


def theorem1_report(A: Assembly, x: str, x_prime: Component,
                    domain_values: dict[str, list] | None = None,
                    inputs_for=None, spec_cls=Spec) -> dict:
    """The **complete** Theorem-1 side-condition report, general model.

    ``substitute`` delegates to this report, which checks all four conditions:

    ========  ==========================================================
    (C1)      ``x``  is context-independent  (``_pure_on``)
    (C2)      ``x'`` is context-independent  (``_pure_on``)
    (C3)      ``signature_ok(x, x')``       — same reads, same output coordinate
    (C4)      ``pointwise_equal_on_reads``   — same on all reachable contexts
    ========  ==========================================================

    plus ``assembly_is_dag`` (PIVOT_NOTE §6.0's model requirement).

    **The invariant worksheet is ``N ∖ ({x} ∪ cone(x))``** (2026-10-12
    soundness fix, novelty-audit §3.1): ``cone(x)`` never contains ``x``
    itself on a DAG, and when (C4) is not certified the substituted node's
    own artifact may change — so ``provably_unchanged_nodes`` excludes ``x``
    whether or not the report is applicable.  Under ``applicable`` (C4) also
    pins ``x``'s artifact (PIVOT_NOTE §6.1 Step 1), which is recorded in
    ``all_nodes_provably_unchanged`` instead.

    **The report does not depend on any spec**: every check quantifies over the
    finite domain, so the experiments call this **once per (assembly, dimension)**
    and reuse the verdict for every configuration (see ``cone_table.run_all``
    and ``artifact_invariance.run``).

    ``inputs_for`` defaults to :func:`predecessor_inputs`, i.e. the general
    model of PIVOT_NOTE §6.0: predecessor artifacts are held fixed while the
    declared coordinates vary.  Pass ``None`` explicitly only if you really
    want the arity-1 probe.
    """
    dom = domain_values if domain_values is not None else DOMAIN
    node = A.nodes[x]
    if inputs_for is None:
        inputs_for = predecessor_inputs(A, x)
    probe_inputs = memoize_inputs(inputs_for)
    checks = {
        "signature_ok": signature_ok(node, x_prime),
        "x_context_independent": _pure_on(node, dom, probe_inputs, spec_cls),
        "x_prime_context_independent": _pure_on(x_prime, dom, probe_inputs, spec_cls),
        "pointwise_equal_on_reads": A.is_dag() and pointwise_equal_on_reads(
            node, x_prime, dom, probe_inputs, spec_cls),
        "assembly_is_dag": A.is_dag(),
    }
    # 不变工作表 = N ∖ ({x} ∪ cone(x))：无环时 x ∉ cone(x)，而 (C4) 未成立时
    # x 自己的 artifact 可能变，故无论 applicable 与否都不把 x 报成不变。
    unchanged = sorted(set(A.nodes) - {x} - A.cone(x))
    rerun = sorted(A.cone(x))
    ok = all(checks.values())
    return {
        "substituted": x,
        "checks": checks,
        "applicable": ok,
        "semantics_revision": "2026-10-12-sound-worksheet",
        "equality_scope": "all full specs in supplied finite domain and their reachable predecessor inputs",
        "unchanged_region": "N \\ ({x} ∪ cone(x)); x itself is unchanged only under applicable (C4), PIVOT_NOTE §6.1 Step 1",
        "all_nodes_provably_unchanged": sorted(A.nodes) if ok else [],
        "necessary_output_reruns": [] if ok else None,
        "new_target_contract_requires_check": True,
        "legacy_workspace_is_conservative": True,
        "cone_nodes_rerun": rerun,
        "provably_unchanged_nodes": unchanged,
        "cycles": sorted(A.cycles()),
        "declared_reads": list(node.reads),
        "assembly_edges": list(A.dependencies(x)),
        "n_nodes": len(A.nodes),
        "cone_covers_every_node": len(rerun) >= len(A.nodes),
        "note": ("有限可达域内精确替换：全图产物相同；不变工作表为 N∖({x}∪cone(x))，"
                 "新组件契约另验" if ok else "前提失败：不给精确替换保证"),
    }


def behavior_change_report(A: Assembly, x: str) -> dict:
    """Structural impact when the target's output may change.

    Conditional on deterministic, side-effect-free nodes and complete edges.
    It neither checks replacement equivalence nor guarantees new contracts.
    The target belongs to the impact set even though a DAG cone excludes it.
    """
    impact = {x} | A.cone(x)
    return {
        "target": x,
        "assembly_is_dag": A.is_dag(),
        "potentially_changed_nodes": sorted(impact),
        "structurally_unchanged_nodes": sorted(set(A.nodes) - impact),
        "requires": "deterministic side-effect-free nodes; complete artifact dependencies; fixed spec and graph",
        "contracts_preserved_in_impact": False,
    }


def substitution_invariance_report(A: Assembly, x: str, x_prime: Component,
                                   spec: Spec, report: dict | None = None) -> dict:
    """P0-2：实际执行替换，比较替换前后各节点 artifact。

    Theorem 1 结论的可执行验证：applicable 时 N∖({x}∪cone(x)) 节点 artifact 必须
    逐点相同；cone 内节点允许不同但必须仍满足 contract。

    ``report`` 可传入 :func:`theorem1_report` 预先算好的判定（side condition
    与 spec 无关，实验里按 (assembly, dimension) 复用），避免在每个配置上重跑
    整个有限域上的纯性/逐点相等探测。
    """
    base = dict(report) if report is not None else substitute(A, x, x_prime)
    report = dict(base)
    if not base["applicable"]:
        report["artifact_invariance"] = None
        return report
    art_before = A.evaluate(spec)
    A2 = Assembly(nodes={**A.nodes, x: x_prime}, edges=A.edges)
    art_after = A2.evaluate(spec)
    cone = set(base["cone_nodes_rerun"])
    report["artifact_invariance"] = {
        "spec": spec.__dict__,
        "unchanged_nodes_artifact_equal": all(
            art_before[u] == art_after[u] for u in base["provably_unchanged_nodes"]),
        "cone_nodes_before_after": {
            u: {"before": str(art_before[u]), "after": str(art_after[u])}
            for u in cone},
        "all_contracts_hold_after": all(
            A2.nodes[u].contract(art_after[u]) for u in A2.nodes),
    }
    return report


# 判别性有限域（QUITS-faithful 模型的坐标取值）。
#
# 穷举性（PIVOT_NOTE §6.3 "枚举完备性"）逐坐标标注，来源见
# experiments/quant_evidence.py 自动解析（不再依赖本注释的手工断言）：
#
#   code      : 6/6 个 QUITS code family 类（BbCode, BpcCode, HgpCode,
#               LcsCode, MittenCode, QlpCode, QlpPolyCode 中去重后的族名）
#               → 穷举（EXHAUSTIVE）
#   extractor : 各族 supported_strategies 白名单的**并集**
#               {cardinal, cardinalNSmerge, custom, hook_error_free,
#                zxcoloration} → 穷举（P2-3 修复；此前只取 {cardinal,
#               zxcoloration}，漏掉 custom / hook_error_free / cardinalNSmerge）
#   arch      : {free, grid2d} —— **刻意欠近似**（QUITS layout/ 还有 toric /
#               transversal 系列），标为 PARTIAL
#   noise     : {SD6, SI1000} —— 结构性取值，QUITS 的 ErrorModel 是参数化
#               dataclass 而非有限枚举，标为 PARTIAL
#   decoder   : {BP-OSD, BP-LSD} —— QUITS 侧只有**函数**没有类型
#               （decoder/ 包 0 个 class、0 个 ABC/Protocol），故这是外部
#               ldpc 包提供的名义取值，标为 PARTIAL
DOMAIN: dict[str, list] = {
    "code": ["BB", "HGP", "mitten", "BPC", "LCS", "QLP"],
    # P2-3：扩到 QUITS 源码实际支持的策略并集（quant_evidence.py 自动解析）
    "extractor": ["cardinal", "cardinalNSmerge", "custom",
                  "hook_error_free", "zxcoloration"],
    "arch": ["free", "grid2d"],
    "noise": ["SD6", "SI1000"],
    "decoder": ["BP-OSD", "BP-LSD"],
}

DOMAIN_EXHAUSTIVE: dict[str, bool] = {
    "code": True,       # 由 pinned tree 的 qldpc_code/* 自动枚举
    "extractor": True,  # 由 pinned tree 的 supported_strategies 并集自动枚举
    "arch": False,      # PARTIAL：只取 2 个代表，未覆盖 toric/transversal
    "noise": False,     # PARTIAL：ErrorModel 参数化，无有限枚举
    "decoder": False,   # PARTIAL：QUITS decoder/ 无类型，取外部 ldpc 名义值
}


# ---------------------------------------------------------------------------
# P0-3: R(c) 从 QUITS 源码自动提取（不再手工建模）
# ---------------------------------------------------------------------------
#
# 下面三张表由 ``experiments/extract_read_sets.py`` 对 pinned tree 做 AST 静态
# 分析**自动生成**（组件粒度取自 gate_audit/protocol.md，锚点按 AST 搜索定位，
# 不写死行号），并由 ``experiments/test_semantics.py`` 锁定：一旦 QUITS 源码
# 改动而这三张表没跟着改，pytest 会失败。
#
# **三张表回答三个不同的问题**（这正是 PIVOT_NOTE §6.0 一般模型
# ``produce : Spec × (前驱 artifact) → Artifact`` 的两个自变量）：
#
# 1. ``READ_SETS_FROM_SOURCE[c]`` —— 组件 c 的 artifact 的取值依赖哪些
#    **spec 坐标**。这是 Theorem 1 的 (C1)/(C2) 与 Lemma 2 里的 ``R(c)``。
#    与源码的对应关系：``extractor`` 读 ``noise``，因为
#    ``qldpc_code/base.py:115 build_circuit(strategy, error_model=..., **opts)``
#    把 noise 坐标烤进了 circuit（H3）；``extractor`` 读 ``code``，因为同一函数
#    在 ``base.py:124`` 读 ``self.supported_strategies``——一个由 code 族决定的
#    类属性（H1）。
# 2. ``ARTIFACT_READS_FROM_SOURCE[c]`` —— 组件 c 消费了哪些**别的组件的 artifact
#    对象**（QldpcCode 实例、stim.Circuit、hz/hx/lz/lx）。在一般模型里这是
#    DAG 的**边**，不是坐标读：``arch`` 与 ``decoder`` 都消费 code artifact，
#    ``decoder`` 还消费 extractor 产出的 circuit。
# 3. ``ASSEMBLY_EDGES_FROM_SOURCE[u]`` —— 由 (2) 去掉自环得到的 DAG 依赖。
#
# **不要**把 (2) 折进 (1)：折进去就是 P0-1 之前的 arity-1 特例，会把
# "读一个 artifact 对象" 误报成 "读那个对象的 spec 坐标"。
READ_SETS_FROM_SOURCE: dict[str, tuple[str, ...]] = {
    "code": ("code",),
    "extractor": ("code", "extractor", "noise"),
    "arch": ("arch",),
    "noise": ("noise",),
    "decoder": ("decoder",),
}

ARTIFACT_READS_FROM_SOURCE: dict[str, tuple[str, ...]] = {
    "code": ("code",),            # 家族 __init__ 内部的 hz/hx 自引用（自环）
    # `build_circuit` 是 QldpcCode 的方法，`self` 就是 code artifact
    # （extract_read_sets 把 `self` 解析成 receiver 的 artifact）。
    "extractor": ("code",),
    "arch": ("code", "arch"),      # Layout(code) / TransversalLayout(code, ...)
    "noise": ("noise",),          # __post_init__ 读 self 的字段（自环）
    "decoder": ("code", "extractor"),   # hz/lz 来自 code，circuit 来自 extractor
}

#: DAG 依赖：由 ``ARTIFACT_READS_FROM_SOURCE`` 去掉自环得到。
#: ``extractor -> noise`` 之所以**不在**这里，是因为 ``build_circuit`` 收到的是
#: noise 坐标的**值**（一个纯函数作用后的 ErrorModel）；把它建成边会得到一个
#: 保守但更宽的 cone。cone_table 的 ``quits_dataflow`` assembly 刻意选了保守
#: 那一侧（``extractor <- (code, noise)``），本表选精确那一侧。
ASSEMBLY_EDGES_FROM_SOURCE: dict[str, tuple[str, ...]] = {
    "code": (),
    "noise": (),
    "extractor": ("code",),
    "arch": ("code",),
    "decoder": ("code", "extractor"),
}

#: 一次"手工建模 vs 自动提取"的逐维度差异说明（由 experiments/read_sets.json
#: 复核，pytest 逐条锁定）。
READ_SETS_FROM_SOURCE_NOTES = {
    "code": "no difference: the family constructors read only their own "
            "coordinate.  Their `hz`/`hx` self-references are a self-loop and "
            "are dropped from the DAG edges.",
    "extractor": "**the only hand-modelling gap**: the hand-declared "
                 "R(extractor) omitted `noise`; the AST extraction finds it at "
                 "qldpc_code/*:build_circuit (parameter / keyword "
                 "`error_model`).  This is H3.",
    "arch": "no missing coordinate: the dependency on `code` is an *artifact* "
            "read (`Layout(code)`, `TransversalLayout(code, ...)`), i.e. a DAG "
            "edge, not a coordinate read.  The dynamic measurement confirms "
            "it: swapping the code family changes `layout_positions`.",
    "noise": "no difference: `ErrorModel` reads only its own coordinate "
             "(its own dataclass fields are a self-loop).",
    "decoder": "no missing coordinate: `code` (hz/lz) and `extractor` (the "
               "stim.Circuit) enter as artifact objects, i.e. DAG edges, not "
               "coordinate reads.",
}

#: ``QUITS_CALL_SITES`` names the dimensions ``extraction`` / ``architecture``
#: while the spec coordinates are ``extractor`` / ``arch``.  This mapping keeps
#: the static call-site table and the dynamic experiment joinable.
CALL_SITE_DIMENSIONS = {
    "extraction": "extractor",
    "architecture": "arch",
    "code": "code",
    "noise": "noise",
    "decoder": "decoder",
}


# ---------------------------------------------------------------------------
# Which assembly produced which number?  (decisions 1-4, 2026-10-09)
# ---------------------------------------------------------------------------
#
# Four assemblies appear in the experiments and they are **not**
# interchangeable: they disagree about ``R(extractor)`` (does it read `noise`?)
# and about the DAG edges.  Every experiment therefore stamps the provenance of
# the assemblies it uses into its JSON (``metadata.assembly_model_sources``) and
# prints it in its Markdown header, so a number can never be read without knowing
# which modelling produced it.
#
# ``baseline: true`` marks the assembly the *published* claims are about since
# 2026-10-09: the trigger-2 verdict and the artifact-invariance witnesses are
# reported against ``source_faithful``.
ASSEMBLY_MODEL_SOURCES: dict[str, dict] = {
    "clean": {
        "baseline": False,
        "builder": "semantics.make_assembly()",
        "read_sets": "hand-declared, idealised: every component reads only its "
                     "own coordinate",
        "edges": "none (all five dimension components are leaves)",
        "faithfulness": "not faithful to the source; it is the deliberately "
                        "minimal contrast baseline",
        "note": "kept so the pre-2026-10-09 numbers stay reproducible",
    },
    "quits_faithful": {
        "baseline": False,
        "builder": "semantics.make_assembly(with_quits_style=True)",
        "read_sets": "hand-declared, plus the H1 counterexample: the extractor "
                     "declares reads=('code',) but its registry lookup also "
                     "reads the `extractor` coordinate",
        "edges": "none",
        "faithfulness": "a *counterexample*, not a model of QUITS: it shows what "
                        "Theorem 3 reports when a component under-declares",
        "note": "the only assembly with unbounded cones by construction",
    },
    "quits_dataflow": {
        "baseline": False,
        "builder": "experiments.cone_table.make_quits_dataflow_assembly()",
        "read_sets": "hand-declared conservative H3 model: R(extractor) contains "
                     "`noise` (build_circuit bakes the error model into the "
                     "circuit) and R(decoder) is everything embedded in the "
                     "circuit plus its own coordinate",
        "edges": "hand-set, deliberately over-approximating: "
                 "extractor <- (code, noise); decoder <- (code, extractor, "
                 "arch, noise); arch <- code (added 2026-10-09 -- the dynamic "
                 "measurement shows a code substitution changes "
                 "`layout_positions`, so this edge is real)",
        "faithfulness": "conservative over-approximation of the source, and "
                        "still *wider* than the auto-extracted one",
        "note": "kept as the hand-modelled counterpart of `source_faithful`",
    },
    "source_faithful": {
        "baseline": True,
        "builder": "semantics.make_source_faithful_assembly()",
        "read_sets": "auto-extracted from the pinned QUITS tree by "
                     "experiments/extract_read_sets.py "
                     "(READ_SETS_FROM_SOURCE)",
        "edges": "auto-derived: ARTIFACT_READS_FROM_SOURCE minus self-loops "
                 "(ASSEMBLY_EDGES_FROM_SOURCE): extractor <- code, "
                 "arch <- code, decoder <- (code, extractor)",
        "faithfulness": "faithful by construction (AST-extracted), "
                        "cross-validated against the dynamic measurements in "
                        "experiments/dynamic_impact.json",
        "note": "the published baseline since 2026-10-09 (decisions 2 and 4)",
        # dimensions carried by this assembly; consumed by extract_read_sets.py
        # to label the published-baseline rows of its diff report.
        "_baseline_dimensions": list(COORDINATES),
    },
}

#: The assembly the trigger-2 verdict and the artifact-invariance witnesses are
#: reported against.
BASELINE_ASSEMBLY = "source_faithful"


def assembly_model_sources(names=None) -> dict:
    """Provenance record for the assemblies used by an experiment.

    Experiment scripts embed this verbatim in their JSON ``metadata`` and print
    it in their Markdown header, so that "which assembly produced this cone?" is
    answerable from the artifact itself rather than from the paper's prose.
    """
    keys = list(ASSEMBLY_MODEL_SOURCES) if names is None else list(names)
    out = {k: dict(ASSEMBLY_MODEL_SOURCES[k])
           for k in keys if k in ASSEMBLY_MODEL_SOURCES}
    out["_baseline"] = BASELINE_ASSEMBLY
    return out


def coordinate_impact(A: "Assembly", coord: str) -> set[str]:
    """改一个 **spec 坐标** 会波及哪些节点（与替换一个节点不同）。

    Theorem 1 的 ``cone(x)`` 回答的是"**替换组件 x** 需要重跑谁"：spec 不变，
    只有 ``produce_x`` 换实现。而"**改坐标 x 的取值**"是另一件事，正确的传播
    规则是::

        impact(x) = {x}
                  ∪ {u : x ∈ R(u)}                     # 显式声明的坐标读
                  ∪ ⋃_{v ∈ impact-so-far} cone(v)      # 再沿 artifact DAG 传播

    第三步不可省：``noise ∈ R(extractor)``，而 ``extractor → decoder`` 是 DAG 边，
    所以改 noise 会连带改 decoder 的产物。``dynamic_impact.py`` 的实测正是这一
    条（noise 替换同时改变 stim_circuit、detector_error_model 和
    decoder_output），而只报 ``cone(noise)`` 会漏掉 extractor 与 decoder。
    """
    readers = {u for u in A.nodes
               if coord in set(A.nodes[u].reads)}
    seed = {coord} | readers
    out = set(seed)
    frontier = set(seed)
    while frontier:
        nxt: set[str] = set()
        for v in frontier:
            for u in A.cone(v):
                if u not in out:
                    nxt.add(u)
        out |= nxt
        frontier = nxt
    return out


def _mk_components():
    """**理想化对照基线**：五个维度的组件 + 装配层，每个组件只读自己的坐标。

    这不是 QUITS-faithful 模型，而是一个刻意的对照基线：所有组件都是 DAG 的
    叶子（除 ``experiment`` 外无依赖），所以每个维度的替换都只影响
    ``experiment`` 一个节点。QUITS-faithful 的读集合与数据流见
    ``READ_SETS_FROM_SOURCE`` / ``ARTIFACT_READS_FROM_SOURCE`` /
    ``ASSEMBLY_EDGES_FROM_SOURCE``（P0-3 自动提取），对应的装配见
    ``make_source_faithful_assembly()``。

    **2026-10-09 决策 2 之后它不再是实验基线**：`cone_table` /
    `artifact_invariance` 的主数字改挂在 ``source_faithful`` 上，本函数只作为
    ``clean`` 对照列与 ``quits_faithful``（H1 反例）保留，见
    ``ASSEMBLY_MODEL_SOURCES``。保留它是为了让 2026-10-09 之前发布过的数字
    仍可复现，而不是因为它更接近 QUITS。
    """
    code = Component("code", ("code",),
                     lambda s, inp: {"kind": "code", "family": s.code},
                     contract=lambda a: a["kind"] == "code")
    extractor = Component("extractor", ("code", "extractor"),
                          lambda s, inp: f"{s.extractor}@{s.code}")
    arch = Component("arch", ("arch",),
                     lambda s, inp: {"constraints": {"grid2d": [16, 16]}.get(s.arch, [])})
    noise = Component("noise", ("noise",),
                      lambda s, inp: {"model": s.noise,
                                      "p": {"SD6": 1e-3, "SI1000": 2e-4}[s.noise]})
    decoder = Component("decoder", ("decoder",),
                        lambda s, inp: {"name": s.decoder, "osd_order": 0},
                        contract=lambda a: a["name"] in {"BP-OSD", "BP-LSD"})
    # 反数据点：QUITS 风格的 extractor——声明只读 code，实际还读 extractor 坐标
    # （模拟 family-specific strategy 经全局 registry 查表的隐藏依赖）
    extraction_quits_style = Component(
        "extractor_quits", ("code",),
        lambda s, inp: f"{s.extractor}@{s.code}" + ("+Native" if s.extractor in {"cardinal", "custom"} else ""))
    return dict(code=code, extractor=extractor, arch=arch, noise=noise,
                decoder=decoder, extractor_quits=extraction_quits_style)


def make_assembly(with_quits_style: bool = False) -> Assembly:
    comps = _mk_components()
    if with_quits_style:
        comps["extractor"] = comps.pop("extractor_quits")
    nodes = {n: c for n, c in comps.items()}
    nodes["experiment"] = Component(
        "experiment", ("code", "extractor", "arch", "noise", "decoder"),
        lambda s, inp: tuple(sorted(
            (n, str(inp.get(n))) for n in comps)))
    edges = {n: () for n in comps}
    edges["experiment"] = tuple(comps)
    return Assembly(nodes=nodes, edges=edges)


# --- the QUITS-faithful component inventory (P0-3, auto-extracted) ---------
#
# These four tables say what the *source* does, and `experiments/read_sets.json`
# is the report that justifies them.  `experiments/dynamic_impact.py` measures
# the same inventory by *executing* QUITS, so the static and the dynamic views
# of the same object can be compared.

#: One representative instance per QUITS code family, with the **number of data
#: qubits** the representative contributes (from `shared/C0/corpus.json` and the
#: QUITS constructors).  Used by the faithful `arch` / `decoder` components to
#: make their dependence on the code artifact concrete.
CODE_FAMILY_DATA_QUBITS: dict[str, int] = {
    "BB": 72, "HGP": 13, "QLP": 120, "BPC": 60, "LCS": 72, "mitten": 36,
}

#: Per-family extraction whitelist = QUITS' ``supported_strategies`` class
#: attribute.  Copied from the pinned tree (qldpc_code/{bb,bpc,hgp,lcs,mitten,
#: qlp}.py) and locked by ``test_read_sets_from_source_matches_extractor`` so
#: it cannot drift.  It is the mechanism behind H1: the extractor's
#: admissibility is a property of the *code* component.
FAMILY_STRATEGIES: dict[str, tuple[str, ...]] = {
    "BB": ("custom", "zxcoloration"),
    "HGP": ("cardinal", "cardinalNSmerge", "zxcoloration"),
    "QLP": ("cardinal", "cardinalNSmerge", "zxcoloration"),
    "BPC": ("cardinal", "cardinalNSmerge", "zxcoloration"),
    "LCS": ("cardinal", "cardinalNSmerge", "zxcoloration"),
    "mitten": ("custom", "hook_error_free", "zxcoloration"),
}

#: Noise parameterisations the faithful `noise` component can produce.
NOISE_MODEL_PARAMS: dict[str, dict] = {
    "SD6": {"idle_error": 1e-4, "sqgate_error": 1e-3,
            "tqgate_error": 1e-3, "spam_error": 1e-3},
    "SI1000": {"idle_error": 2e-5, "sqgate_error": 2e-4,
               "tqgate_error": 2e-4, "spam_error": 2e-4},
}


def admissible_spec(**overrides) -> Spec:
    """A default spec whose ``(code, extractor)`` pair satisfies H1.

    ``Spec()`` defaults to ``code="BB", extractor="cardinal"``, which QUITS
    *rejects* (``BbCode.supported_strategies == {"custom", "zxcoloration"}``).
    The faithful extractor's contract therefore refuses to build it -- that is
    H1 being caught by the semantic layer rather than by a runtime raise.
    """
    base = {"code": "HGP", "extractor": "cardinal", "arch": "grid2d",
            "noise": "SD6", "decoder": "BP-OSD"}
    base.update(overrides)
    return Spec(**base)


def make_source_faithful_components() -> dict[str, Component]:
    """The five dimensions with the **auto-extracted** read sets R(c).

    Each ``produce`` consumes exactly what its declared read set says:
    coordinates are read off ``Spec`` and predecessor *artifacts* off the
    second argument.  So ``context_independence_with_inputs`` on these
    components must return True, and ``detect_hidden_dependency`` with the
    assembly's ``inputs_for`` must report ``pure`` -- a non-trivial check of the
    auto-extracted model.
    """
    code = Component(
        "code", READ_SETS_FROM_SOURCE["code"],
        lambda s, inp: {"kind": "code", "family": s.code,
                        "n_data": CODE_FAMILY_DATA_QUBITS[s.code]},
        contract=lambda a: a["kind"] == "code")
    extractor = Component(
        "extractor", READ_SETS_FROM_SOURCE["extractor"],
        # build_circuit(strategy, error_model=...): the noise coordinate is
        # baked into the circuit (H3), and the strategy must be admissible for
        # the family (H1: `self.supported_strategies`).
        lambda s, inp: {"kind": "circuit",
                        "strategy": s.extractor,
                        "family": s.code,
                        "admissible": s.extractor in FAMILY_STRATEGIES[s.code],
                        "noise": s.noise},
        contract=lambda a: a["kind"] == "circuit" and a["admissible"])
    arch = Component(
        "arch", READ_SETS_FROM_SOURCE["arch"],
        # Layout(code) -> positions: the dependence on `code` is an *artifact*
        # read, i.e. the DAG edge arch <- code, NOT a coordinate read.
        lambda s, inp: {"kind": "layout", "arch": s.arch,
                        "n_positions": int(inp["code"]["n_data"])},
        contract=lambda a: a["kind"] == "layout")
    noise = Component(
        "noise", READ_SETS_FROM_SOURCE["noise"],
        lambda s, inp: {"kind": "noise", "model": s.noise,
                        "params": tuple(sorted(NOISE_MODEL_PARAMS[s.noise].items()))},
        contract=lambda a: a["kind"] == "noise")
    decoder = Component(
        "decoder", READ_SETS_FROM_SOURCE["decoder"],
        # get_codecap_pL(code, p, ..., decoder, dict): hz/lz come from the code
        # artifact, the DEM from the extractor (circuit) artifact, and the
        # decoder implementation is the decoder coordinate.
        lambda s, inp: {"kind": "decoder", "name": s.decoder,
                        "hz_shape": (inp["code"]["n_data"] // 2,
                                     inp["code"]["n_data"]),
                        "circuit": inp["extractor"]["strategy"]},
        contract=lambda a: a["kind"] == "decoder"
        and a["name"] in {"BP-OSD", "BP-LSD"})
    return {"code": code, "extractor": extractor, "arch": arch,
            "noise": noise, "decoder": decoder}


def make_source_faithful_assembly() -> Assembly:
    """The QUITS-faithful assembly: auto-extracted R(c) + auto-derived edges.

    ``edges[u]`` is ``ASSEMBLY_EDGES_FROM_SOURCE[u]`` (which components' artifact
    objects ``u`` consumes).  The cone of this assembly is therefore *derived
    from the source*, not asserted: ``cone(code) = {arch, decoder, experiment}``
    because ``Layout(code)`` and ``get_codecap_pL(code, ...)`` both consume the
    code artifact.
    """
    comps = make_source_faithful_components()
    nodes = dict(comps)
    nodes["experiment"] = Component(
        "experiment", COORDINATES,
        lambda s, inp: tuple(sorted((n, str(inp.get(n))) for n in comps)))
    edges = {n: ASSEMBLY_EDGES_FROM_SOURCE[n] for n in comps}
    edges["experiment"] = tuple(comps)
    return Assembly(nodes=nodes, edges=edges)


def inadmissible_pairs(domain_values: dict[str, list] | None = None) -> list[tuple]:
    """H1 in the semantic layer: which ``(code, extractor)`` pairs are refused.

    The faithful extractor's contract is ``strategy ∈ family.supported_strategies``
    -- exactly the runtime raise at ``qldpc_code/base.py:124-131``.  Here it is a
    *stated, checkable* obligation rather than an exception, and this function
    enumerates the refusals over the finite domain, so a caller can check
    admissibility **before** assembling.
    """
    dom = domain_values or DOMAIN
    out = []
    for code in dom["code"]:
        for strategy in dom["extractor"]:
            if strategy not in FAMILY_STRATEGIES[code]:
                out.append((code, strategy))
    return out


# ---------------------------------------------------------------------------
# QUITS 真实调用点（PIVOT_NOTE §4）：file:line + 判定
# ---------------------------------------------------------------------------

QUITS_CALL_SITES = [
    {"dimension": "extraction", "site": "circuit_construction/__init__.py:9-14,17-23",
     "quits_native": "字符串 registry + 每族 class-attr 白名单；隐藏跨组件依赖 "
                     "（base.py:124-131 cardinal→BbCode 抛 NotImplementedError）",
     "model_checkable": True,
     "semantic_check": "hidden-dependency 探测报 observed ⊄ declared → cone unbounded"},
    {"dimension": "decoder", "site": "simulation.py:50-56",
     "quits_native": "无 ABC；decoder(...) + .decode() 纯 duck typing",
     "model_checkable": True,
     "semantic_check": "义务写成 contract 可检查（syndrome 语义保持）"},
    {"dimension": "noise", "site": "noise/error_model.py:37-42",
     "quits_native": "仅校验结构（实数 / 长度 3 或 15）；无 builder 性质义务",
     "model_checkable": True,
     "semantic_check": "contract = circuit builder 依赖的性质，而非形状"},
    {"dimension": "code", "site": "qldpc_code/__init__.py:3-10, base.py:30-50",
     "quits_native": "家族类共享 set_parity_checks 隐式契约",
     "model_checkable": True,
     "semantic_check": "contract = CSS 对易（hz·hxᵀ ≡ hx·hzᵀ）"},
    {"dimension": "architecture", "site": "layout/base.py:22; qldpc_code/base.py:55-57",
     "quits_native": "唯一用 Layout ABC 的维度（Layout/AbstractToricLayout）；"
                     "QldpcCode.get_layout() 默认返回 None",
     "model_checkable": True,
     "semantic_check": "读集合显式包含 arch 坐标"},
]


def _reconfigure_stdout() -> None:
    """让 stdout 能打印非 ASCII（本模块输出含中文与箭头）。

    Windows 控制台默认 cp1252/gbk，直接 print 会 UnicodeEncodeError。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):          # pragma: no cover - platform dep.
            pass


def main() -> int:
    _reconfigure_stdout()
    A = make_assembly()
    spec = Spec()
    art = A.evaluate(spec)
    print(f"baseline experiment artifact nodes: {len(art)}")

    for n, c in A.nodes.items():
        hid = detect_hidden_dependency(c, DOMAIN)
        print(f"  {n:12s} reads={hid['declared_reads']} verdict={hid['verdict']}")

    code_alt = Component("code", ("code",),
                         lambda s, inp: {"family": s.code, "kind": "code"},
                         contract=lambda a: a["kind"] == "code")
    v = substitution_invariance_report(A, "code", code_alt, spec)
    print("substitute(code → code-alt):", {k: v[k] for k in ("applicable", "cone_nodes_rerun")})
    print("artifact invariance:", v["artifact_invariance"]["unchanged_nodes_artifact_equal"])

    A2 = make_assembly(with_quits_style=True)
    hid2 = detect_hidden_dependency(A2.nodes["extractor"], DOMAIN)
    print("quits-style extractor hidden dependency:", hid2)

    # P0-3 / P2-2：源码自动提取的 QUITS-faithful 模型
    F = make_source_faithful_assembly()
    print("\nsource-faithful assembly (R(c) auto-extracted from the pinned tree):")
    for n in sorted(F.nodes):
        print(f"  {n:12s} reads={F.nodes[n].reads} "
              f"edges={F.edges[n]} cone={sorted(F.cone(n))} "
              f"impact={sorted(coordinate_impact(F, n)) if n in COORDINATES else '-'}")
    spec_f = admissible_spec()
    F.evaluate(spec_f)
    print("  admissible spec evaluates:", spec_f.__dict__)
    try:
        F.evaluate(Spec(code="BB", extractor="cardinal"))
        print("  BB+cardinal: assembled (unexpected)")
    except ValueError as exc:
        print(f"  BB+cardinal refused by contract: {exc}")
    print(f"  inadmissible (code, extractor) pairs in DOMAIN: "
          f"{len(inadmissible_pairs())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
