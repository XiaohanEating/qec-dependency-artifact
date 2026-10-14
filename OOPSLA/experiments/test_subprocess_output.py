"""Hash-seed restarts must preserve main(argv)'s output directory."""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.mark.parametrize("module_name", ["dynamic_impact", "stim_circuit_gate"])
def test_hash_restart_preserves_explicit_output_arguments(monkeypatch, module_name, tmp_path):
    module = importlib.import_module(module_name)
    monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    monkeypatch.setattr(sys, "argv", ["pytest", "--unrelated-pytest-argument"])
    captured = []

    class Result:
        returncode = 0

    def run(command, **kwargs):
        captured.append((command, kwargs))
        return Result()

    monkeypatch.setattr(module.subprocess, "run", run)
    argv = ["--quick", "--out", str(tmp_path)]
    assert module._ensure_hash_seed(argv) == 0
    command, kwargs = captured[0]
    assert command[2:] == argv
    assert kwargs["env"]["PYTHONHASHSEED"] == "0"
