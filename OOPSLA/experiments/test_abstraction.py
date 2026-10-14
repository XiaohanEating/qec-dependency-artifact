"""Tests for the OOPSLA compositional abstraction prototype (PLAN §4/§6)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import abstraction as ab


def test_all_laws_pass():
    for law in ab.LAW_TESTS:
        assert law() is True, law.__name__


@pytest.mark.parametrize(
    "law",
    ab.LAW_TESTS,
    ids=[law.__name__ for law in ab.LAW_TESTS],
)
def test_law_individually(law):
    assert law() is True


def test_compose_assoc_random():
    ctx = {"code": "HGP", "arch": "grid2d", "noise": "SI1000"}
    assert ab.compose(ab._f, ab.compose(ab._g, ab._h))(ctx) == ab.compose(
        ab.compose(ab._f, ab._g), ab._h
    )(ctx)


def test_corpus_configs_compose_subset():
    corpus = ab.load_corpus()
    codes, strategies = ab.specs_from_corpus(corpus)
    # same spec dataclasses composed across >= 2 codes x >= 2 strategies
    picked = [c for c in codes if c.family in ("BB", "HGP")][:2]
    assert len(picked) >= 2
    configs = ab.build_configs(
        picked, strategies, ab.ArchSpec("free"), ab.NoiseSpec("SD6", 1e-3), ab.DecoderSpec("BP-OSD")
    )
    strats_used = {c["extractor"]["strategy"] for c in configs}
    codes_used = {c["code"]["name"] for c in configs}
    assert len(codes_used) >= 2
    assert len(strats_used) >= 2
    assert len(configs) >= 4


def test_full_corpus_cross_product():
    corpus = ab.load_corpus()
    codes, strategies = ab.specs_from_corpus(corpus)
    configs = ab.build_configs(
        codes, strategies, ab.ArchSpec("free"), ab.NoiseSpec("SD6", 1e-3), ab.DecoderSpec("BP-OSD")
    )
    expected = sum(len(v) for v in strategies.values())
    assert len(configs) == expected


def test_measure_cl_single_dimension():
    out = ab.measure_cl({"touched": ["code"]})
    assert out["cl"] == pytest.approx(1 / len(ab.COMPONENT_INVENTORY))
    assert out["modified_components"] == ["code"]
    assert out["reuse_ratio"] == pytest.approx(1 - 1 / len(ab.COMPONENT_INVENTORY))


def test_measure_cl_mapping_form_and_unknown():
    out = ab.measure_cl({"code": "BB->HGP", "noise": "SD6->SI1000", "bogus": "x"})
    assert out["cl"] == pytest.approx(2 / len(ab.COMPONENT_INVENTORY))
    assert out["unknown_components"] == ["bogus"]


def test_swap_code_locality():
    exp = ab.Experiment(
        ab.CodeSpec("BB", "bb-144", {}),
        ab.ExtractorSpec("custom"),
        ab.ArchSpec("grid2d"),
        ab.NoiseSpec("SD6", 1e-3),
        ab.DecoderSpec("BP-OSD"),
    )
    swapped = ab.swap_code(exp, ab.CodeSpec("HGP", "hgp-seed3x3", {}))
    assert swapped.code.family == "HGP"
    assert swapped.extractor == exp.extractor
    assert swapped.arch == exp.arch
    assert swapped.noise == exp.noise
    assert swapped.decoder == exp.decoder
