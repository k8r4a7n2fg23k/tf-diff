"""Secrets canary: planted CANARY values must never reach any output. Never loosen this."""

from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from factories import GOLDEN, plan_text, resource_change
from tfdiff.analysis.engine import analyze
from tfdiff.cli import app
from tfdiff.model.settings import Settings
from tfdiff.report import document, markdown, sarif, terminal
from tfdiff.terraform.parser import parse

CANARY = "CANARY"


def _planted() -> str:
    marked = resource_change(
        "aws_db_instance.main",
        actions=("delete", "create"),
        before={"password": "CANARY-a", "users": [{"token": "CANARY-b"}], "engine": "postgres"},
        after={"password": "CANARY-c", "users": [{"token": "CANARY-d"}], "engine": "mysql"},
        before_sensitive={"password": True, "users": [{"token": True}]},
        after_sensitive={"password": True, "users": [{"token": True}]},
        replace_paths=[["engine"]],
    )
    # not marked by the provider: only the name gives it away
    unmarked = resource_change(
        "terraform_data.app",
        before={"output": {"db_password": "CANARY-e", "api_key": "CANARY-f"}},
        after={"output": {"db_password": "CANARY-g", "api_key": "CANARY-h"}},
    )
    return plan_text(marked, unmarked)


@pytest.mark.parametrize(
    "text",
    [
        _planted(),
        (GOLDEN / "terraform-1.16" / "plan.json").read_text(encoding="utf-8"),
        # hashicorp/aws against moto: a real provider schema marks the RDS password
        (GOLDEN / "moto-dangerous" / "plan.json").read_text(encoding="utf-8"),
    ],
    ids=["synthetic", "recorded", "recorded-aws"],
)
def test_no_output_contains_a_secret(text: str) -> None:
    assert CANARY in text
    plan = parse(text)
    report = analyze(plan, Settings(environment="production"))
    console = Console(record=True, width=120, color_system=None)
    terminal.render(console, report)
    for item in report.assessments:
        terminal.explain(console, item.change.address, item)
    outputs = [
        console.export_text(),
        document.render(report),
        markdown.render(report),
        sarif.render(report, "plan.json"),
        repr(plan),
        repr(report),
    ]
    assert [CANARY in output for output in outputs] == [False] * len(outputs)


@pytest.mark.parametrize(
    "text",
    [
        '{"format_version": "1.2", "resource_changes": [{"address": "CANARY-x"',
        '{"format_version": "1.2", "resource_changes": [{"address": ["CANARY-x"]}]}',
    ],
    ids=["truncated", "mistyped"],
)
def test_cli_errors_do_not_echo_secrets(text: str, tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(text, encoding="utf-8")
    failed = CliRunner().invoke(app, ["analyze", str(plan)])
    assert failed.exit_code == 2
    assert CANARY not in failed.output
