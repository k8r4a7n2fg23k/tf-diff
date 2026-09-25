import io
import json
from pathlib import Path
from random import Random

import pytest
from hypothesis import given
from hypothesis import strategies as st
from rich.console import Console

from factories import GOLDEN, plan_text, resource_change
from tfdiff.analysis.engine import analyze, environment, lookup
from tfdiff.model.errors import InputError
from tfdiff.model.findings import Severity
from tfdiff.model.report import Report
from tfdiff.model.settings import Settings
from tfdiff.report import document, markdown, sarif, terminal
from tfdiff.terraform.parser import parse

AWS = GOLDEN / "aws-production" / "plan.json"


def _instance_delete(address: str = "aws_instance.logs") -> str:
    return plan_text(
        resource_change(address, actions=("delete",), before={"tags": {"Env": "production"}})
    )


def test_tag_sets_environment_and_settings_override_it() -> None:
    plan = parse(_instance_delete())
    (change,) = plan.changes
    assert environment(change, Settings()) == "production"
    assert environment(change, Settings(environment="staging")) == "staging"
    assert [item.rule for item in analyze(plan, Settings(environment="staging")).findings] == []


def test_settings_disable_and_override() -> None:
    plan = parse(_instance_delete())
    assert analyze(plan, Settings()).findings[0].severity is Severity.CRITICAL
    lowered = analyze(plan, Settings(severities={"destroy-production-resource": Severity.LOW}))
    assert lowered.findings[0].severity is Severity.LOW
    assert (
        analyze(plan, Settings(disabled=frozenset({"destroy-production-resource"}))).findings == ()
    )


@pytest.mark.parametrize(
    ("pattern", "is_ignored"),
    [
        ('module.db.aws_instance.logs["blue"]', True),
        ("module.db.*", True),
        ('module.db.aws_instance.logs["b?ue"]', True),
        ('module.db.aws_instance.logs["green"]', False),
        ("aws_instance.*", False),
    ],
)
def test_ignore_matches_indexed_addresses_literally(pattern: str, is_ignored: bool) -> None:
    plan = parse(_instance_delete('module.db.aws_instance.logs["blue"]'))
    report = analyze(plan, Settings(ignore=(pattern,)))
    assert report.ignored == (('module.db.aws_instance.logs["blue"]',) if is_ignored else ())


def test_ignored_resource_does_not_stop_the_rest() -> None:
    plan = parse(
        plan_text(
            resource_change(
                "aws_instance.a", actions=("delete",), before={"tags": {"env": "prod"}}
            ),
            resource_change(
                "aws_instance.b", actions=("delete",), before={"tags": {"env": "prod"}}
            ),
        )
    )
    report = analyze(plan, Settings(ignore=("aws_instance.a",)))
    assert [item.address for item in report.findings] == ["aws_instance.b"]
    assert report.ignored == ("aws_instance.a",)


def test_environment_comes_only_from_tags() -> None:
    plan = parse(
        plan_text(
            resource_change(
                "aws_instance.logs",
                actions=("delete",),
                before={"environment": "production", "labels": {"env": "production"}},
            )
        )
    )
    (change,) = plan.changes
    assert environment(change, Settings()) is None


@pytest.mark.parametrize(
    ("address", "value", "factors"),
    [
        # critical 60 + replace 15 + production 10 + 4 dependents x 3
        (
            "module.database.aws_db_instance.primary",
            97,
            (
                "+60 critical finding (stateful-data-loss)",
                "+15 replace: the old object is destroyed",
                "+10 production",
                "+12 4 dependent resource(s)",
            ),
        ),
        # high 40 + production 10; an update destroys nothing
        (
            "aws_autoscaling_group.web",
            50,
            ("+40 high finding (remove-redundancy)", "+10 production"),
        ),
    ],
    ids=["replace-with-dependents", "update"],
)
def test_score_by_hand(address: str, value: int, factors: tuple[str, ...]) -> None:
    report = analyze(parse(AWS.read_text(encoding="utf-8")), Settings())
    (item,) = (item for item in report.assessments if item.change.address == address)
    assert item.score is not None
    assert (item.score.value, item.score.factors) == (value, factors)


def test_lookup_tells_noop_ignored_and_missing() -> None:
    plan = parse(AWS.read_text(encoding="utf-8"))
    report = analyze(plan, Settings())
    assert lookup(report, plan, "aws_iam_role.app") is None
    reading = plan_text(
        resource_change("data.aws_ami.base", actions=("read",), mode="data", after={})
    )
    assert lookup(analyze(parse(reading), Settings()), parse(reading), "data.aws_ami.base") is None
    found = lookup(report, plan, "aws_security_group.bastion")
    assert found is not None
    assert found.findings[0].rule == "security-group-wide-open"
    with pytest.raises(InputError, match=r"aws_iam_role\.ghost: not in the plan"):
        lookup(report, plan, "aws_iam_role.ghost")
    ignoring = analyze(plan, Settings(ignore=("aws_security_group.*",)))
    with pytest.raises(InputError, match=r"bastion: skipped by the ignore list"):
        lookup(ignoring, plan, "aws_security_group.bastion")


def _renders(report: Report) -> list[str]:
    buffer = io.StringIO()
    terminal.render(Console(file=buffer, width=100, color_system=None), report)
    return [
        buffer.getvalue(),
        document.render(report),
        markdown.render(report),
        sarif.render(report, "plan.json"),
    ]


def _shuffled_configuration(node: object, shuffler: Random) -> object:
    """Same configuration, resources and module calls in another order."""
    if isinstance(node, list):
        items = [_shuffled_configuration(item, shuffler) for item in node]
        shuffler.shuffle(items)
        return items
    if isinstance(node, dict):
        keys = list(node)
        shuffler.shuffle(keys)
        return {key: _shuffled_configuration(node[key], shuffler) for key in keys}
    return node


PLANS = sorted(GOLDEN.glob("*/plan.json"))


@pytest.mark.parametrize("plan", PLANS, ids=[plan.parent.name for plan in PLANS])
@given(shuffler=st.randoms())
def test_input_order_does_not_change_the_report(plan: Path, shuffler: Random) -> None:
    raw = json.loads(plan.read_text(encoding="utf-8"))
    expected = _renders(analyze(parse(json.dumps(raw)), Settings()))
    shuffler.shuffle(raw.get("resource_changes", []))
    if "configuration" in raw:
        raw["configuration"] = _shuffled_configuration(raw["configuration"], shuffler)
    assert _renders(analyze(parse(json.dumps(raw)), Settings())) == expected


def _stack(*tags: str | None) -> str:
    """An untagged ASG deletion next to resources with the given Environment tags."""
    return plan_text(
        resource_change("aws_autoscaling_group.web", actions=("delete",), before={}),
        *(
            resource_change(
                f"aws_vpc.n{i}",
                actions=("no-op",),
                before={"tags_all": {"Environment": tag}},
                after={"tags_all": {"Environment": tag}},
            )
            for i, tag in enumerate(tags)
        ),
        configuration={"root_module": {}},
    )


def _asg(report: Report) -> tuple[str | None, list[str]]:
    (assessment,) = report.assessments
    return assessment.environment, [found.rule for found in assessment.findings]


def test_untagged_resource_takes_the_environment_the_stack_agrees_on() -> None:
    report = analyze(parse(_stack("production", "Production")), Settings())
    assert _asg(report) == ("production", ["destroy-production-resource"])
    assert (report.environment, report.warnings) == ("production", ())


def test_mixed_tags_leave_untagged_resources_without_environment() -> None:
    report = analyze(parse(_stack("staging", "production")), Settings())
    assert _asg(report) == (None, [])
    assert report.environment is None
    assert report.warnings == (
        "resources are tagged for different environments (production, staging): untagged ones "
        "get none, set --environment",
    )


def test_no_environment_at_all_is_a_warning() -> None:
    report = analyze(parse(_stack()), Settings())
    assert report.warnings == (
        "no environment: nothing sets it and no resource has an Environment or env tag, so "
        "production-only checks are off; set --environment",
    )
    assert analyze(parse(_stack()), Settings(environment="dev")).warnings == ()


def test_a_plan_without_changes_needs_no_environment() -> None:
    raw = resource_change("aws_vpc.main", actions=("no-op",), before={}, after={})
    plan = plan_text(raw, configuration={"root_module": {}})
    assert analyze(parse(plan), Settings()).warnings == ()


def test_the_tag_after_the_change_decides_the_environment() -> None:
    # moving a resource into production makes it a production change
    raw = resource_change(
        "aws_instance.logs",
        before={"tags": {"Environment": "staging"}},
        after={"tags": {"Environment": "production"}},
    )
    (change,) = parse(plan_text(raw)).changes
    assert environment(change, Settings()) == "production"


def _tagged(before: object, after: object, actions: tuple[str, ...] = ("update",)) -> str | None:
    raw = resource_change("aws_db_instance.db", actions=actions, before=before, after=after)
    (change,) = parse(plan_text(raw)).changes
    return environment(change, Settings())


@pytest.mark.parametrize(
    ("before", "after", "actions", "expected"),
    [
        # the replaced object was production, whatever the new one is tagged
        (
            {"tags": {"Environment": "production"}},
            {"tags": {"Environment": "staging"}},
            ("delete", "create"),
            "production",
        ),
        ({"tags": {"env": "dev"}}, {"tags": {"env": "staging"}}, ("update",), "staging"),
        # tags_all holds the provider's default_tags under the resource's own
        (
            {"tags": {"Name": "db"}, "tags_all": {"Name": "db", "Environment": "production"}},
            {"tags": {"Name": "db"}, "tags_all": {"Name": "db", "Environment": "production"}},
            ("update",),
            "production",
        ),
        (
            {"tags": {"env": "dev"}, "tags_all": {"env": "dev"}},
            {"tags": {"env": "dev"}, "tags_all": {"env": "dev"}},
            ("update",),
            "dev",
        ),
        (
            {"tags": {"env": " production "}},
            {"tags": {"env": " production "}},
            ("update",),
            "production",
        ),
        ({"tags": {"env": " ", "Environment": "qa"}}, {}, ("delete",), "qa"),
        ({"tags": {"Environment": "dev", "env": "prod"}}, {}, ("delete",), "prod"),
        ({"tags": {"Environment": "dev", "env": "qa"}}, {}, ("delete",), "dev"),
    ],
)
def test_the_strictest_environment_tag_counts(
    before: object, after: object, actions: tuple[str, ...], expected: str
) -> None:
    if actions == ("delete",):
        after = None
    assert _tagged(before, after, actions) == expected


def test_disagreeing_environment_tags_on_one_resource_are_a_warning() -> None:
    raw = resource_change(
        "aws_db_instance.db",
        actions=("delete",),
        before={"tags": {"Environment": "dev", "env": "production"}},
    )
    report = analyze(parse(plan_text(raw, configuration={"root_module": {}})), Settings())
    assert report.environment == "production"
    assert report.warnings == (
        "Environment and env tags disagree on 1 resource(s) (aws_db_instance.db): production "
        "counts if either says so, else Environment",
    )


def test_production_synonyms_are_one_environment() -> None:
    report = analyze(parse(_stack("prod", "production", "PRD")), Settings())
    assert _asg(report) == ("prod", ["destroy-production-resource"])
    assert report.warnings == ()


def test_data_source_tags_do_not_vote() -> None:
    shared = resource_change(
        "data.aws_vpc.shared",
        actions=("read",),
        mode="data",
        after={"tags": {"Environment": "shared"}},
    )
    raw = json.loads(_stack("production"))
    raw["resource_changes"].append(shared)
    report = analyze(parse(json.dumps(raw)), Settings())
    assert _asg(report) == ("production", ["destroy-production-resource"])
    assert report.warnings == ()
