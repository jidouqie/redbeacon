"""Public CI must work without exposing private source or weakening releases."""
import importlib.util
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("release_contract_scope", TOOLS / "check_release_contracts.py")
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)


def test_public_scope_never_reads_private_checkout(monkeypatch):
    original = Path.read_text

    def read_public_only(path, *args, **kwargs):
        assert not path.is_relative_to(contracts.ROOT / "cli"), path
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_public_only)
    contracts.main(public_only=True)


def test_default_release_gate_still_checks_cli_provenance(monkeypatch):
    original = Path.read_text

    def missing_cli(path, *args, **kwargs):
        if path.is_relative_to(contracts.ROOT / "cli"):
            raise FileNotFoundError("private CLI required")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", missing_cli)
    with pytest.raises(FileNotFoundError, match="private CLI required"):
        contracts.main()
