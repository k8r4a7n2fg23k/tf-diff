import io
import json
from datetime import date
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
from tfdiff.model.settings import Settings, Suppression
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
        "no environment: nothing sets it and no resource has an environment tag "
        "(Environment, env), so production-only checks are off; set --environment",
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
        # a blank value under the first key must not shadow the next one
        ({"tags": {"Environment": " ", "env": "qa"}}, {}, ("delete",), "qa"),
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
        "environment tags (Environment, env) disagree on 1 resource(s) (aws_db_instance.db): "
        "production counts if any says so, else the first listed tag the resource has",
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


NO_CONFIG: dict[str, object] = {"root_module": {}}
STAGED = Settings(environment_tags=("Stage", "env"), production_names=frozenset({"prd", "live"}))


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"stage": "qa"}, "qa"),
        # the replaced default no longer counts
        ({"Environment": "production"}, None),
        # earlier in the list wins
        ({"env": "dev", "Stage": "qa"}, "qa"),
        # production wins over the order
        ({"Stage": "qa", "env": "Live"}, "Live"),
    ],
)
def test_configured_tag_keys_decide_the_environment(
    tags: dict[str, str], expected: str | None
) -> None:
    raw = resource_change("aws_instance.logs", actions=("delete",), before={"tags": tags})
    (change,) = parse(plan_text(raw)).changes
    assert environment(change, STAGED) == expected


@pytest.mark.parametrize(
    ("settings", "severities"),
    [
        (STAGED, [Severity.CRITICAL]),
        (Settings(environment="LIVE", production_names=frozenset({"live"})), [Severity.CRITICAL]),
        # "prod" is not production once the names are replaced
        (Settings(environment="prod", production_names=frozenset({"live"})), []),
    ],
)
def test_configured_production_names_turn_on_production_checks(
    settings: Settings, severities: list[Severity]
) -> None:
    raw = resource_change(
        "aws_instance.logs", actions=("delete",), before={"tags": {"Stage": "live"}}
    )
    findings = analyze(parse(plan_text(raw)), settings).findings
    assert [item.severity for item in findings if item.rule == "destroy-production-resource"] == (
        severities
    )


def test_warnings_name_the_configured_tag_keys() -> None:
    clash = resource_change(
        "aws_instance.a", actions=("delete",), before={"tags": {"Stage": "qa", "env": "dev"}}
    )
    untagged = resource_change("aws_instance.b", actions=("delete",), before={})
    assert analyze(parse(plan_text(clash, configuration=NO_CONFIG)), STAGED).warnings == (
        "environment tags (Stage, env) disagree on 1 resource(s) (aws_instance.a): "
        "production counts if any says so, else the first listed tag the resource has",
    )
    (missing,) = analyze(parse(plan_text(untagged, configuration=NO_CONFIG)), STAGED).warnings
    assert "no resource has an environment tag (Stage, env)" in missing


def test_with_three_keys_the_first_one_present_decides() -> None:
    settings = Settings(environment_tags=("Stage", "env", "Environment"))
    raw = resource_change(
        "aws_instance.logs",
        actions=("delete",),
        before={"tags": {"Environment": "qa", "env": "dev"}},
    )
    (change,) = parse(plan_text(raw)).changes
    assert environment(change, settings) == "dev"


def _database(address: str = 'module.db.aws_db_instance.main["blue"]') -> str:
    return plan_text(
        resource_change(address, actions=("delete",), before={"tags": {"env": "prod"}}),
        configuration=NO_CONFIG,
    )


def _muted(resource: str, until: date | None = None, today: date | None = None) -> Settings:
    entry = Suppression("stateful-data-loss", resource, "snapshot taken", until)
    return Settings(suppress=(entry,), today=today)


@pytest.mark.parametrize(
    "resource",
    ['module.db.aws_db_instance.main["blue"]', "module.db.*", "module.db.*.main[?blue?]"],
)
def test_suppression_mutes_one_rule_on_matching_resources(resource: str) -> None:
    report = analyze(parse(_database()), _muted(resource))
    (assessment,) = report.assessments
    assert [item.rule for item in report.findings] == ["destroy-production-resource"]
    assert [item.rule for item in assessment.findings] == ["destroy-production-resource"]
    assert [(muted.finding.rule, muted.reason) for muted in report.suppressed] == [
        ("stateful-data-loss", "snapshot taken")
    ]


def test_suppression_leaves_other_resources_alone() -> None:
    report = analyze(parse(_database("aws_db_instance.other")), _muted("module.db.*"))
    assert report.suppressed == ()
    assert {item.rule for item in report.findings} == {
        "destroy-production-resource",
        "stateful-data-loss",
    }


@pytest.mark.parametrize(
    ("today", "is_muted"),
    [(None, True), (date(2027, 3, 1), True), (date(2027, 3, 2), False)],
    ids=["no-clock", "last-day", "day-after"],
)
def test_suppression_holds_through_until(today: date | None, is_muted: bool) -> None:
    resource = "module.db.*"
    report = analyze(parse(_database()), _muted(resource, date(2027, 3, 1), today))
    assert len(report.suppressed) == (1 if is_muted else 0)
    expiry = (
        "suppression of stateful-data-loss on module.db.* expired on 2027-03-01: "
        "its findings count again"
    )
    assert (expiry in report.warnings) is not is_muted
    assert ("stateful-data-loss" in {item.rule for item in report.findings}) is not is_muted


def test_a_resource_with_every_finding_suppressed_has_no_score() -> None:
    entries = tuple(
        Suppression(rule, "module.db.*", "decommissioned")
        for rule in ("destroy-production-resource", "stateful-data-loss")
    )
    report = analyze(parse(_database()), Settings(suppress=entries))
    (assessment,) = report.assessments
    assert (report.findings, assessment.findings, assessment.score) == ((), (), None)
    assert len(report.suppressed) == 2


def _entry(resource: str, reason: str, until: date | None = None) -> Suppression:
    return Suppression("stateful-data-loss", resource, reason, until)


@pytest.mark.parametrize(
    ("entries", "reason"),
    [
        (
            (_entry("module.db.*", "old", date(2027, 1, 1)), _entry("module.db.*main*", "new")),
            "new",
        ),
        ((_entry("module.db.*", "first"), _entry("module.db.*main*", "second")), "first"),
    ],
    ids=["expired-then-live", "two-live"],
)
def test_the_first_entry_in_force_wins(entries: tuple[Suppression, ...], reason: str) -> None:
    settings = Settings(suppress=entries, today=date(2027, 6, 1))
    report = analyze(parse(_database()), settings)
    assert [muted.reason for muted in report.suppressed] == [reason]
    assert not any("expired" in warning for warning in report.warnings)


def test_an_expired_entry_warns_once_and_only_if_it_matched() -> None:
    plan = plan_text(
        *(
            resource_change(address, actions=("delete",), before={"tags": {"env": "prod"}})
            for address in ("module.db.aws_db_instance.a", "module.db.aws_db_instance.b")
        ),
        configuration=NO_CONFIG,
    )
    entries = (
        _entry("module.db.*", "old", date(2027, 1, 1)),
        _entry("aws_db_instance.gone", "old", date(2027, 1, 1)),
    )
    report = analyze(parse(plan), Settings(suppress=entries, today=date(2027, 6, 1)))
    assert [warning for warning in report.warnings if "expired" in warning] == [
        "suppression of stateful-data-loss on module.db.* expired on 2027-01-01: "
        "its findings count again"
    ]
    assert len([item for item in report.findings if item.rule == "stateful-data-loss"]) == 2


def test_expiry_warnings_are_sorted_by_rule_then_resource() -> None:
    gone = date(2027, 1, 1)
    entries = tuple(
        Suppression(rule, resource, "old", gone)
        for resource in ("module.db.*", "module.db.aws_*")
        for rule in ("stateful-data-loss", "destroy-production-resource")
    )
    report = analyze(parse(_database()), Settings(suppress=entries, today=date(2027, 6, 1)))
    assert [
        warning.split(" expired")[0] for warning in report.warnings if "expired" in warning
    ] == [
        "suppression of destroy-production-resource on module.db.*",
        "suppression of destroy-production-resource on module.db.aws_*",
        "suppression of stateful-data-loss on module.db.*",
        "suppression of stateful-data-loss on module.db.aws_*",
    ]
