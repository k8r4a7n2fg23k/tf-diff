"""Golden reports. UPDATE_GOLDEN=1 rewrites expected.*; say in the commit what changed and why."""

import io
import os
from pathlib import Path

import pytest
from rich.console import Console

from factories import GOLDEN
from tfdiff.analysis.engine import analyze
from tfdiff.config import FILENAME, load
from tfdiff.model.report import Report
from tfdiff.report import document, markdown, sarif, terminal
from tfdiff.terraform.parser import parse

CASES = sorted(path.parent for path in GOLDEN.glob("*/plan.json"))


def _terminal(report: Report) -> str:
    buffer = io.StringIO()
    console = Console(
        file=buffer, width=100, color_system=None, force_terminal=False, legacy_windows=False
    )
    terminal.render(console, report)
    return buffer.getvalue()


def _sarif(report: Report) -> str:
    return sarif.render(report, "plan.json")


RENDERERS = {"txt": _terminal, "json": document.render, "md": markdown.render, "sarif": _sarif}


def _report(case: Path) -> Report:
    config = case / FILENAME
    settings = load(config.read_text(encoding="utf-8") if config.exists() else None, {})
    return analyze(parse((case / "plan.json").read_text(encoding="utf-8")), settings)


@pytest.mark.parametrize("extension", sorted(RENDERERS))
@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_golden(case: Path, extension: str) -> None:
    rendered = RENDERERS[extension](_report(case))
    expected = case / f"expected.{extension}"
    if os.environ.get("UPDATE_GOLDEN"):
        expected.write_text(rendered, encoding="utf-8", newline="\n")
    assert rendered == expected.read_text(encoding="utf-8")
