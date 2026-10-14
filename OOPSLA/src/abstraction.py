"""Minimal compositional abstraction skeleton (OOPSLA PLAN §4).

Five first-class components + Experiment assembly. Dataclasses now; DSL
parser later. This iteration adds:

1. Component signatures per PLAN §4 plus compose/parallel (tensor)
   operators with executable equality tests for the monoidal laws.
2. A declarative specification example: one set of specification
   dataclasses composes >=2 codes x >=2 strategies from C0 corpus.json
   into experiment configurations (config dicts; no StimJob run needed).
3. A change-locality measurement skeleton measure_cl(change_spec).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Protocol

CORPUS_PATH = Path(__file__).resolve().parents[2] / "shared" / "C0" / "corpus.json"


@dataclass(frozen=True)
class CodeSpec:
    family: str          # "BB" | "HGP" | "QLP" | ...
    name: str
    ctor: dict           # quits constructor kwargs (family-specific, hidden behind this spec)


@dataclass(frozen=True)
class ArchSpec:
    topology: str        # "free" | "grid2d" | ...
    constraints: dict = field(default_factory=dict)


@dataclass(frozen=True)
class NoiseSpec:
    model: str           # "SD6" | "SI1000" | "uniform"
    eps: float = 1e-3


@dataclass(frozen=True)
class DecoderSpec:
    name: str            # "BP-OSD" | "BP-LSD" | ...
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractorSpec:
    strategy: str        # "cardinal" | "zxcoloration" | "custom" | ...
    num_rounds: int = 3


class CodeComponent(Protocol):
    def materialize(self, spec: CodeSpec): ...
    def logicals(self, code): ...


class ExtractorComponent(Protocol):
    def circuit(self, code, spec: ExtractorSpec, arch: ArchSpec): ...


class NoiseComponent(Protocol):
    def error_model(self, spec: NoiseSpec): ...


class DecoderComponent(Protocol):
    def decode(self, samples, circuit, code, spec: DecoderSpec): ...


@dataclass
class Experiment:
    """Assembly: compose(C, E, A, N, D) -> executable Stim job."""
    code: CodeSpec
    extractor: ExtractorSpec
    arch: ArchSpec
    noise: NoiseSpec
    decoder: DecoderSpec

    def describe(self) -> str:
        return (f"Experiment(C={self.code.name}/{self.code.family}, "
                f"E={self.extractor.strategy}, A={self.arch.topology}, "
                f"N={self.noise.model}@{self.noise.eps}, D={self.decoder.name})")

    def to_config(self) -> dict:
        """Declarative description of the StimJob (no circuit build)."""
        return {
            "code": {"family": self.code.family, "name": self.code.name, "ctor": self.code.ctor},
            "extractor": {"strategy": self.extractor.strategy, "num_rounds": self.extractor.num_rounds},
            "arch": {"topology": self.arch.topology, "constraints": self.arch.constraints},
            "noise": {"model": self.noise.model, "eps": self.noise.eps},
            "decoder": {"name": self.decoder.name, "params": self.decoder.params},
        }


# ---------------------------------------------------------------------------
# Monoidal composition (PLAN §4): components are morphisms between specs
# (objects). compose = sequential assembly; parallel = disjoint tensor.
# ---------------------------------------------------------------------------

# A morphism is a namespaced context transformer: dict -> dict.
# "Objects" are context keys held by the morphism's namespace.
Morphism = Callable[[dict], dict]


def _touches(f: Morphism, ctx: dict) -> set:
    """Keys f reads or writes: their values differ after applying f."""
    out = f(dict(ctx))
    return {k for k in set(ctx) | set(out) if out.get(k) != ctx.get(k)}


def compose(f: Morphism, g: Morphism) -> Morphism:
    """Sequential assembly: (compose(f, g))(x) == g(f(x))."""
    return lambda ctx: g(f(ctx))


def parallel(f: Morphism, g: Morphism) -> Morphism:
    """Tensor: f and g act on disjoint context keys and merge their results."""
    def _par(ctx: dict) -> dict:
        a, b = f(dict(ctx)), g(dict(ctx))
        keys = set(ctx) | set(a) | set(b)
        changed_a = {k for k in keys if a.get(k) != ctx.get(k)}
        changed_b = {k for k in keys if b.get(k) != ctx.get(k)}
        overlap = changed_a & changed_b
        if overlap:
            raise ValueError(f"parallel: f and g both write {sorted(overlap)}")
        merged = dict(ctx)
        for k in changed_a:
            merged[k] = a[k]
        for k in changed_b:
            merged[k] = b[k]
        return merged
    return _par


def unit_sequential() -> Morphism:
    """Unit for compose: the no-op assembly."""
    return lambda ctx: dict(ctx)


UnitSpec: dict = {}  # tensor unit object


def tensor_unit() -> Morphism:
    """Unit for parallel: leaves the context untouched (UnitSpec)."""
    return lambda ctx: dict(ctx)


def swap(ctx: dict, left: str = "left", right: str = "right") -> dict:
    """Symmetry braiding sigma : A x B -> B x A on the two tagged channels."""
    out = dict(ctx)
    out[left], out[right] = ctx[right], ctx[left]
    return out


# --- Executable equational law tests (PLAN §4): each returns True iff both
# sides of the equation produce the same result on random-ish instances. ---

def _sample_ctx() -> dict:
    return {"code": "BB", "arch": "free", "noise": "SD6", "left": [1, 2], "right": [3, 4]}


def _f(ctx: dict) -> dict:
    out = dict(ctx)
    out["code"] = out["code"] + "->E1"
    return out


def _g(ctx: dict) -> dict:
    out = dict(ctx)
    out["arch"] = out["arch"] + "->E2"
    return out


def _h(ctx: dict) -> dict:
    out = dict(ctx)
    out["noise"] = out["noise"] + "->E3"
    return out


def _left(ctx: dict) -> dict:
    out = dict(ctx)
    out["left"] = out["left"] + [0]
    return out


def _right(ctx: dict) -> dict:
    out = dict(ctx)
    out["right"] = out["right"] + [9]
    return out


def test_compose_assoc() -> bool:
    ctx = _sample_ctx()
    lhs = compose(_f, compose(_g, _h))(ctx)
    rhs = compose(compose(_f, _g), _h)(ctx)
    assert lhs == rhs, (lhs, rhs)
    return True


def test_compose_unit() -> bool:
    ctx = _sample_ctx()
    assert compose(_f, unit_sequential())(ctx) == _f(ctx)
    assert compose(unit_sequential(), _f)(ctx) == _f(ctx)
    return True


def test_tensor_assoc() -> bool:
    ctx = _sample_ctx()
    lhs = parallel(parallel(_f, _g), _left)(ctx)
    rhs = parallel(_f, parallel(_g, _left))(ctx)
    assert lhs == rhs, (lhs, rhs)
    return True


def test_tensor_unit() -> bool:
    ctx = _sample_ctx()
    assert parallel(_f, tensor_unit())(ctx) == _f(ctx)
    assert parallel(tensor_unit(), _f)(ctx) == _f(ctx)
    return True


def test_interchange() -> bool:
    """(f ⊗ g) ∘ (h ⊗ k) == (f ∘ h) ⊗ (g ∘ k), when types allow assembly."""
    ctx = _sample_ctx()
    lhs = parallel(compose(_f, _h), compose(_g, _left))(ctx)
    rhs = compose(parallel(_f, _g), parallel(_h, _left))(ctx)
    assert lhs == rhs, (lhs, rhs)
    return True


def test_symmetry_involution() -> bool:
    """sigma ∘ sigma == id."""
    ctx = _sample_ctx()
    assert swap(swap(ctx)) == ctx
    return True


LAW_TESTS = [
    test_compose_assoc,
    test_compose_unit,
    test_tensor_assoc,
    test_tensor_unit,
    test_interchange,
    test_symmetry_involution,
]


# ---------------------------------------------------------------------------
# Declarative specification example (>= 2 codes x >= 2 strategies)
# ---------------------------------------------------------------------------

def load_corpus(path: Path = CORPUS_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def specs_from_corpus(corpus: dict) -> tuple[list[CodeSpec], dict[str, list[ExtractorSpec]]]:
    """One set of specification dataclasses derived from C0 corpus."""
    codes: list[CodeSpec] = []
    strategies: dict[str, list[ExtractorSpec]] = {}
    for inst in corpus["instances"]:
        codes.append(CodeSpec(inst["family"], inst["name"], dict(inst["quits_ctor"])))
        strategies[inst["name"]] = [ExtractorSpec(s) for s in inst["strategies"]]
    return codes, strategies


def build_configs(
    codes: list[CodeSpec],
    strategies: dict[str, list[ExtractorSpec]],
    arch: ArchSpec,
    noise: NoiseSpec,
    decoder: DecoderSpec,
) -> list[dict]:
    """Compose independent specs into experiment config dicts (no StimJob run)."""
    configs = []
    for code in codes:
        for strat in strategies[code.name]:
            configs.append(
                Experiment(code, strat, arch, noise, decoder).to_config()
            )
    return configs


# ---------------------------------------------------------------------------
# Change locality measurement skeleton
# ---------------------------------------------------------------------------

# Pre-registered component inventory (PLAN §5 / gate_audit protocol):
# five spec components + Experiment assembly layer. Fixed before measuring.
COMPONENT_INVENTORY = ["code", "extractor", "arch", "noise", "decoder", "assembly"]

ChangeSpec = dict  # e.g. {"code": {"from": ..., "to": ...}} or {"touched": ["code"]}


def measure_cl(change_spec: ChangeSpec) -> dict:
    """Skeleton CL measurement over the pre-registered component inventory.

    change_spec accepts either {"touched": [component names]} or a mapping
    of component name -> change description. Only inventory components are
    counted; unknown entries are flagged rather than silently dropped.
    """
    if "touched" in change_spec:
        touched = list(change_spec["touched"])
    else:
        touched = [k for k, v in change_spec.items() if v]
    known = [t for t in touched if t in COMPONENT_INVENTORY]
    unknown = [t for t in touched if t not in COMPONENT_INVENTORY]
    modified = len(set(known))
    total = len(COMPONENT_INVENTORY)
    return {
        "cl": modified / total,
        "modified_components": sorted(set(known)),
        "total_components": total,
        "reuse_ratio": (total - modified) / total,
        "unknown_components": unknown,
    }


def swap_code(exp: Experiment, new_code: CodeSpec) -> Experiment:
    """Single-dimension change: only the Code component is replaced."""
    return Experiment(new_code, exp.extractor, exp.arch, exp.noise, exp.decoder)


if __name__ == "__main__":
    exp = Experiment(
        CodeSpec("BB", "bb-144", {}),
        ExtractorSpec("zxcoloration", 3),
        ArchSpec("free"),
        NoiseSpec("SD6", 1e-3),
        DecoderSpec("BP-OSD"),
    )
    print(exp.describe())
    print(swap_code(exp, CodeSpec("HGP", "hgp-seed3x3", {})).describe())

    for law in LAW_TESTS:
        print(f"{law.__name__}: {law()}")

    corpus = load_corpus()
    codes, strategies = specs_from_corpus(corpus)
    configs = build_configs(
        codes[:2], strategies, ArchSpec("free"), NoiseSpec("SD6", 1e-3), DecoderSpec("BP-OSD")
    )
    print(f"composed {len(configs)} configs from {len(codes[:2])} codes x their strategies")
    print(measure_cl({"touched": ["code"]}))
