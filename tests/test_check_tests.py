"""scripts/check_tests.py, the gate that keeps assertion-free tests out."""

import importlib.util
from pathlib import Path

import pytest

from factories import ROOT

_SPEC = importlib.util.spec_from_file_location(
    "check_tests", ROOT.parent / "scripts" / "check_tests.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)


@pytest.mark.parametrize(
    ("body", "complaint"),
    [
        ("    assert parse(text)\n", None),
        ("    found = parse(text)\n    assert found\n", "no assertion that can fail"),
        ("    assert len(parse(text))\n", "no assertion that can fail"),
        ("    assert parse(text) is not None\n", "no assertion that can fail"),
        ("    parse(text)\n", "no assertion that can fail"),
        ("    assert parse(text) == 1\n", None),
        ("    with pytest.raises(ValueError):\n        parse(text)\n", None),
        (
            "    monkeypatch.setattr(cli, 'parse', None)\n    assert parse(text) == 1\n",
            "patches our own code",
        ),
    ],
    ids=["call", "bare-name", "len", "is-not-none", "no-assert", "compare", "raises", "patch"],
)
def test_weak_tests_are_flagged(tmp_path: Path, body: str, complaint: str | None) -> None:
    source = tmp_path / "test_sample.py"
    source.write_text(
        f"from tfdiff import cli\n\n\ndef test_sample(monkeypatch, text):\n{body}", encoding="utf-8"
    )
    errors = gate.check_file(source)
    if complaint is None:
        assert errors == []
    else:
        (error,) = errors
        assert complaint in error
