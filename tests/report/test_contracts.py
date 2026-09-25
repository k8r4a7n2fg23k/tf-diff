import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import (  # type: ignore[import-untyped]  # no stubs; adding types-jsonschema needs a new dep
    Draft4Validator,
    Draft202012Validator,
)
from typer.testing import CliRunner

from factories import GOLDEN, ROOT, plan_text, resource_change
from tfdiff import cli
from tfdiff.analysis.engine import analyze
from tfdiff.config import ENV_ENVIRONMENT
from tfdiff.model.findings import order
from tfdiff.model.settings import Settings
from tfdiff.report import document, markdown, sarif
from tfdiff.terraform.parser import parse

CASES = sorted(path.parent for path in GOLDEN.glob("*/plan.json"))
SARIF_SCHEMA = json.loads((ROOT / "schemas" / "sarif-2.1.0.json").read_text(encoding="utf-8"))
REPORT_SCHEMA = json.loads(document.schema())


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_json_report_matches_schema(case: Path) -> None:
    report = analyze(parse((case / "plan.json").read_text(encoding="utf-8")), Settings())
    errors = list(
        Draft202012Validator(REPORT_SCHEMA).iter_errors(json.loads(document.render(report)))
    )
    assert [error.message for error in errors] == []


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_sarif_matches_2_1_0_schema(case: Path) -> None:
    report = analyze(parse((case / "plan.json").read_text(encoding="utf-8")), Settings())
    log = json.loads(sarif.render(report, "plan.json"))
    assert [error.message for error in Draft4Validator(SARIF_SCHEMA).iter_errors(log)] == []
    assert len(log["runs"][0]["results"]) == len(report.findings)


SAFE = plan_text(
    resource_change("aws_lb.web", before={"idle_timeout": 60}, after={"idle_timeout": 30})
)
CAPACITY = plan_text(
    resource_change(
        "aws_autoscaling_group.web",
        before={"min_size": 6, "desired_capacity": 6},
        after={"min_size": 2, "desired_capacity": 2},
    )
)
DANGEROUS = plan_text(
    resource_change("aws_instance.logs", actions=("delete",), before={"bucket": "logs"})
)


@pytest.mark.parametrize(
    ("plan", "config", "args", "code"),
    [
        (SAFE, None, [], cli.Exit.SUCCESS),
        (DANGEROUS, None, [], cli.Exit.SUCCESS),
        (DANGEROUS, None, ["--environment", "production"], cli.Exit.POLICY_VIOLATION),
        (DANGEROUS, "environment: production\n", [], cli.Exit.POLICY_VIOLATION),
        (DANGEROUS, "environment: production\nfail_on: critical\n", [], cli.Exit.POLICY_VIOLATION),
        (
            DANGEROUS,
            "environment: production\nrules:\n  destroy-production-resource:\n    enabled: false\n",
            [],
            cli.Exit.SUCCESS,
        ),
        ("{not json", None, [], cli.Exit.INVALID_INPUT),
        ('{"format_version": "9.0"}', None, [], cli.Exit.INVALID_INPUT),
        (SAFE, "rules:\n  nope: {}\n", [], cli.Exit.CONFIGURATION_ERROR),
        (CAPACITY, "fail_on: critical\n", [], cli.Exit.SUCCESS),
        (CAPACITY, "fail_on: critical\n", ["--fail-on", "high"], cli.Exit.POLICY_VIOLATION),
        (CAPACITY, None, ["--fail-on", "critical"], cli.Exit.SUCCESS),
        # click reports usage errors with 2; the README documents it next to invalid input
        (SAFE, None, ["--fail-on", "bogus"], cli.Exit.INVALID_INPUT),
    ],
    ids=[
        "safe",
        "no-environment",
        "prod-flag",
        "prod-config",
        "fail-on-critical",
        "rule-disabled",
        "bad-json",
        "bad-format",
        "bad-config",
        "high-below-critical",
        "flag-over-config",
        "flag-alone",
        "bad-flag-value",
    ],
)
def test_check_exit_codes(  # noqa: PLR0913, PLR0917  - parametrized case plus two fixtures
    plan: str,
    config: str | None,
    args: list[str],
    code: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(ENV_ENVIRONMENT, raising=False)
    Path("plan.json").write_text(plan, encoding="utf-8")
    if config is not None:
        Path(".tf-diff.yaml").write_text(config, encoding="utf-8")
    outcome = CliRunner().invoke(cli.app, ["check", "plan.json", *args])
    assert outcome.exit_code == code, outcome.output


UNKNOWN_CAPACITY = plan_text(
    resource_change(
        "aws_autoscaling_group.web",
        actions=("delete", "create"),
        before={"min_size": 6},
        after={},
        after_unknown={"min_size": True},
    )
)


@pytest.mark.parametrize(
    ("config", "args", "code"),
    [
        (None, [], cli.Exit.SUCCESS),
        (None, ["--fail-on-confidence", "low"], cli.Exit.POLICY_VIOLATION),
        ("fail_on_confidence: low\n", [], cli.Exit.POLICY_VIOLATION),
        ("fail_on_confidence: low\n", ["--fail-on-confidence", "high"], cli.Exit.SUCCESS),
    ],
    ids=["default-reports-only", "flag", "config", "flag-over-config"],
)
def test_low_confidence_findings_fail_only_when_asked(
    config: str | None,
    args: list[str],
    code: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the replaced group's min_size is unknown until apply: a HIGH finding with low confidence
    monkeypatch.chdir(tmp_path)
    Path("plan.json").write_text(UNKNOWN_CAPACITY, encoding="utf-8")
    if config is not None:
        Path(".tf-diff.yaml").write_text(config, encoding="utf-8")
    outcome = CliRunner().invoke(cli.app, ["check", "plan.json", "-f", "json", *args])
    assert outcome.exit_code == code, outcome.output
    (finding,) = [
        item for item in json.loads(outcome.stdout)["findings"] if item["rule"] == "reduce-capacity"
    ]
    assert (finding["severity"], finding["confidence"]) == ("high", "low")
    # the finding is reported either way; a passing run says what it left out
    is_noted = "1 low-confidence finding(s) at high or above not counted" in outcome.stderr
    assert is_noted is (code == cli.Exit.SUCCESS)


def test_unexpected_error_exits_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(SAFE, encoding="utf-8")

    def broken(*_: object, **__: object) -> object:
        raise RuntimeError("CANARY-internal")

    monkeypatch.setattr(json, "loads", broken)
    monkeypatch.setattr(sys, "argv", ["tf-diff", "analyze", str(plan)])
    with pytest.raises(SystemExit) as caught:
        cli.main()
    assert caught.value.code == cli.Exit.INTERNAL_ERROR
    assert capsys.readouterr().err == "internal error: RuntimeError; please report it\n"


def test_sarif_keeps_the_most_severe_results_github_accepts() -> None:
    # min_size and desired_capacity 6 -> 2: two high findings; the public database: one critical
    plan = plan_text(
        _shrink("aws_autoscaling_group.web", 6, 2),
        resource_change(
            "aws_db_instance.db",
            before={"publicly_accessible": False},
            after={"publicly_accessible": True},
        ),
    )
    report = analyze(parse(plan), Settings())
    # 3 x 8334 = 25002: the two left out are high, every critical is kept
    many = replace(report, findings=tuple(sorted(report.findings * 8334, key=order)))
    (run,) = json.loads(sarif.render(many, "plan.json"))["runs"]
    severities = Counter(result["properties"]["severity"] for result in run["results"])
    assert severities == {"critical": 8334, "high": 16666}
    (notice,) = run["invocations"][0]["toolExecutionNotifications"]
    assert notice["message"]["text"] == (
        "2 least severe finding(s) left out: GitHub rejects a run of more than 25000 results; "
        "the JSON report has them all"
    )
    run["results"] = run["results"][:1]
    errors = Draft4Validator(SARIF_SCHEMA).iter_errors({"version": "2.1.0", "runs": [run]})
    assert [error.message for error in errors] == []


def _fingerprints(*changes: dict[str, object]) -> list[str]:
    report = analyze(parse(plan_text(*changes)), Settings())
    results = json.loads(sarif.render(report, "plan.json"))["runs"][0]["results"]
    return [result["partialFingerprints"]["tfdiffFinding/v1"] for result in results]


def _shrink(address: str, before: int, after: int) -> dict[str, object]:
    return resource_change(
        address,
        before={"min_size": before, "desired_capacity": before},
        after={"min_size": after, "desired_capacity": after},
    )


def test_fingerprints_follow_the_finding_not_its_values() -> None:
    # code scanning keeps one alert open across runs while the numbers move
    first = _fingerprints(_shrink("aws_autoscaling_group.web", 6, 2))
    assert len(set(first)) == len(first) == 2
    assert _fingerprints(_shrink("aws_autoscaling_group.web", 8, 1)) == first
    assert set(_fingerprints(_shrink("aws_autoscaling_group.api", 6, 2))).isdisjoint(first)


@pytest.mark.parametrize(
    ("plan", "uri"),
    [("plan.json", "plan.json"), (None, "file:///")],
    ids=["relative", "absolute"],
)
def test_sarif_location_is_a_uri(
    plan: str | None, uri: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("plan.json").write_text(CAPACITY, encoding="utf-8")
    target = plan or str(tmp_path / "plan.json")
    outcome = CliRunner().invoke(cli.app, ["analyze", target, "-f", "sarif"])
    (result, *_) = json.loads(outcome.stdout)["runs"][0]["results"]
    location = result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    # on Windows a bare C:/... would read as a URI with scheme "C"
    assert location.startswith(uri)


@pytest.mark.parametrize(
    ("encoding", "code"),
    [
        ("utf-8-sig", cli.Exit.POLICY_VIOLATION),
        ("utf-16", cli.Exit.POLICY_VIOLATION),
        ("cp1251", cli.Exit.INVALID_INPUT),
    ],
    ids=["out-file-bom", "powershell-redirect", "legacy-codepage"],
)
def test_plan_encodings_windows_shells_write(tmp_path: Path, encoding: str, code: int) -> None:
    # terraform writes non-ASCII unescaped; a changed tag carries it into the report
    raw = resource_change(
        "aws_autoscaling_group.web",
        before={"desired_capacity": 6, "tags": {"Owner": "Пётр"}},
        after={"desired_capacity": 1, "tags": {"Owner": "Анна"}},
    )
    plan = json.dumps(json.loads(plan_text(raw)), ensure_ascii=False)
    path = tmp_path / "plan.json"
    path.write_bytes(plan.encode(encoding))
    outcome = CliRunner().invoke(cli.app, ["check", str(path), "-f", "json"])
    assert outcome.exit_code == code
    if code == cli.Exit.POLICY_VIOLATION:
        report = json.loads(outcome.stdout)
        (change,) = report["changes"]
        owner = next(item for item in change["attributes"] if item["path"] == "tags.Owner")
        assert (owner["before"]["value"], owner["after"]["value"]) == ("Пётр", "Анна")
        assert report["summary"]["risk"]["high"] == 1


def test_missing_file_is_invalid_input() -> None:
    outcome = CliRunner().invoke(cli.app, ["analyze", "definitely-missing.json"])
    assert outcome.exit_code == cli.Exit.INVALID_INPUT


@pytest.mark.parametrize(
    ("command", "code", "stderr"),
    [
        ("analyze", cli.Exit.SUCCESS, []),
        ("check", cli.Exit.POLICY_VIOLATION, ["check failed: 1500 finding(s) at high or above"]),
    ],
)
def test_reader_closing_the_pipe_keeps_the_verdict(
    command: str, code: int, stderr: list[str], tmp_path: Path
) -> None:
    # far more output than a pipe buffer holds, so the write hits a closed pipe
    deletes = [
        resource_change(f"aws_instance.b{i}", actions=("delete",), before={"bucket": f"b{i}"})
        for i in range(1500)
    ]
    plan = tmp_path / "plan.json"
    plan.write_text(plan_text(*deletes), encoding="utf-8")
    entry = "from tfdiff.cli import main; main()"
    process = subprocess.Popen(  # noqa: S603  - our interpreter, fixed arguments
        [sys.executable, "-c", entry, command, str(plan), "--environment", "production"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    process.stdout.read(64)
    process.stdout.close()
    lines = process.stderr.read().decode().splitlines()
    assert (process.wait(timeout=120), lines) == (code, stderr)


def test_markdown_keeps_odd_for_each_keys_inside_their_cell() -> None:
    address = 'aws_instance.logs["a|<b>&c"]'
    text = markdown.render(
        analyze(
            parse(DANGEROUS.replace("aws_instance.logs", address.replace('"', '\\"'))),
            Settings(environment="production"),
        )
    )
    (row,) = [line for line in text.splitlines() if line.startswith("| **CRITICAL**")]
    # five unescaped pipes: four cells
    assert len(re.findall(r"(?<!\\)\|", row)) == 5, row
    assert "<summary><code>aws_instance.logs[&quot;a|&lt;b&gt;&amp;c&quot;]</code>" in text


def test_markdown_table_counts_findings_that_read_the_same() -> None:
    plan = plan_text(
        resource_change(
            "aws_autoscaling_group.web",
            before={"min_size": 4, "desired_capacity": 4, "max_size": 4},
            after={"min_size": 1, "desired_capacity": 1, "max_size": 1},
        )
    )
    text = markdown.render(analyze(parse(plan), Settings()))
    rows = [line for line in text.splitlines() if line.startswith("| **HIGH**")]
    assert rows == [
        "| **HIGH** | `aws_autoscaling_group.web` | Capacity reduced (`reduce-capacity`) x2 "
        "| high |"
    ]
    # the details still tell the two apart
    assert "desired\\_capacity drops by 75%" in text
    assert "min\\_size drops by 75%" in text


def test_markdown_text_from_the_plan_cannot_ping_link_or_embed() -> None:
    # the comment is posted as the repository's bot; plan values are not its words
    raw = "@org/team [x](https://e.test) ![i](https://e.test/i.png) &lt; `c`"
    assert markdown._text(raw) == (
        r"&#64;org/team \[x\](https://e.test) \!\[i\](https://e.test/i.png) &amp;lt; \`c\`"
    )
