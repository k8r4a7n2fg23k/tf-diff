"""The commands other than analyze/check, and --config, as a user runs them."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from factories import GOLDEN
from tfdiff import __version__, cli
from tfdiff.rules.registry import RULES

AWS = (GOLDEN / "aws-production" / "plan.json").as_posix()
PRIMARY = "module.database.aws_db_instance.primary"


def _invoke(*args: str) -> tuple[int, str, str]:
    outcome = CliRunner().invoke(cli.app, list(args))
    return outcome.exit_code, outcome.stdout, outcome.stderr


def test_explain_shows_the_assessment() -> None:
    code, out, _ = _invoke("explain", AWS, PRIMARY)
    assert code == cli.Exit.SUCCESS
    rows = {line.split("  ", 1)[0]: line.split("  ", 1)[-1].strip() for line in out.splitlines()}
    assert rows["ACTION"] == "REPLACE (delete, create)"
    assert rows["SCORE"] == "97/100, confidence high"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("explain", AWS, "aws_iam_role.ghost"), "aws_iam_role.ghost: not in the plan"),
        (("graph", AWS, "--resource", "aws_iam_role.ghost"), "aws_iam_role.ghost: not in the plan"),
        (("graph", AWS, "--to", PRIMARY), "--to needs --resource"),
    ],
    ids=["explain-missing", "graph-missing", "to-alone"],
)
def test_bad_address_is_invalid_input(args: tuple[str, ...], message: str) -> None:
    code, out, err = _invoke(*args)
    assert (code, out) == (cli.Exit.INVALID_INPUT, "")
    assert err == f"error: {message}\n"


def test_explain_of_an_ignored_resource_says_so(tmp_path: Path) -> None:
    config = tmp_path / "ignore.yaml"
    config.write_text(f"ignore:\n  - {PRIMARY}\n", encoding="utf-8")
    code, _, err = _invoke("explain", AWS, PRIMARY, "--config", str(config))
    assert code == cli.Exit.INVALID_INPUT
    assert "skipped by the ignore list" in err


def test_graph_json_neighbourhood_and_path() -> None:
    target = "module.api.aws_ecs_service.api"
    code, out, _ = _invoke("graph", AWS, "--resource", PRIMARY, "--to", target, "-f", "json")
    assert code == cli.Exit.SUCCESS
    view = json.loads(out)
    assert view["blast_radius"] == {
        "direct": [
            "module.analytics.aws_db_instance.reporting",
            "module.api.aws_ecs_task_definition.api",
            "module.worker.aws_ecs_service.worker",
        ],
        "indirect": [target],
    }
    assert view["path"] == [PRIMARY, "module.api.aws_ecs_task_definition.api", target]


def test_graph_json_edges_name_known_nodes() -> None:
    code, out, _ = _invoke("graph", AWS, "-f", "json")
    assert code == cli.Exit.SUCCESS
    view = json.loads(out)
    assert [PRIMARY, "module.api.aws_ecs_task_definition.api"] in view["edges"]
    assert {node for edge in view["edges"] for node in edge} <= set(view["nodes"])


def test_listing_commands() -> None:
    _, rules, _ = _invoke("rules")
    assert sorted(line.split()[1] for line in rules.splitlines()[1:]) == sorted(
        rule.id for rule in RULES
    )
    _, version, _ = _invoke("version")
    assert version.startswith(f"tf-diff {__version__} (rules 1, report schema 1)")
    _, schema, _ = _invoke("schema")
    assert json.loads(schema)["title"] == "tf-diff report, schema version 1"


def test_missing_config_named_on_the_command_line(tmp_path: Path) -> None:
    # an explicit --config must exist: falling back to defaults would drop the user's fail_on
    missing = tmp_path / ("very-long-directory-name-" * 4) / "tf-diff.yaml"
    code, _, err = _invoke("check", AWS, "--config", str(missing))
    assert code == cli.Exit.CONFIGURATION_ERROR
    # one line, so a log grep for the path finds it
    assert err.count("\n") == 1
    assert str(missing) in err


def test_config_saved_by_powershell_is_read(tmp_path: Path) -> None:
    config = tmp_path / "tf-diff.yaml"
    config.write_text("fail_on: critical\n", encoding="utf-16")
    # aws-production holds critical findings: the file's threshold must take effect
    assert _invoke("check", AWS, "--config", str(config))[0] == cli.Exit.POLICY_VIOLATION
    config.write_text("fail_on: critical\nignore: ['*']\n", encoding="utf-16")
    assert _invoke("check", AWS, "--config", str(config))[0] == cli.Exit.SUCCESS


def test_deposed_object_is_explained_by_its_label() -> None:
    catalogue = (GOLDEN / "rule-catalogue" / "plan.json").as_posix()
    code, out, _ = _invoke("explain", catalogue, "aws_s3_bucket.archive (deposed 0a1b2c3d)")
    assert code == cli.Exit.SUCCESS
    assert "DEPOSED       0a1b2c3d" in out.splitlines()


@pytest.mark.parametrize(
    ("content", "message"),
    [(None, "is a directory"), ("{not json", "not JSON: line 1 column 2")],
    ids=["directory", "bad-json"],
)
def test_plan_errors_name_the_file(tmp_path: Path, content: str | None, message: str) -> None:
    plan = tmp_path / "plan.json"
    if content is None:
        plan.mkdir()
    else:
        plan.write_text(content, encoding="utf-8")
    code, _, err = _invoke("analyze", str(plan))
    assert code == cli.Exit.INVALID_INPUT
    assert err.startswith(f"error: {plan}: {message}")


def test_reports_end_lines_with_lf_on_every_platform(tmp_path: Path) -> None:
    # a report saved on Windows must be the same bytes as on Linux (goldens, diffs, caches)
    entry = "from tfdiff.cli import main; main()"
    done = subprocess.run(  # noqa: S603  - our interpreter, fixed arguments
        [sys.executable, "-c", entry, "analyze", AWS, "-f", "markdown"],
        capture_output=True,
        check=False,
    )
    assert done.returncode == cli.Exit.SUCCESS
    assert b"\r\n" not in done.stdout
    assert done.stdout.startswith(b"<!-- tf-diff:report -->\n")
