import pytest

from factories import configuration, context, resource_change
from tfdiff.model.findings import Confidence, Evidence, Severity
from tfdiff.rules.generic import sensitive


@pytest.mark.parametrize(
    ("after", "fires"), [("CANARY-new", True), ("CANARY-old", False)], ids=["rotated", "same"]
)
def test_sensitive_change_is_reported_without_value(after: str, fires: bool) -> None:
    raw = resource_change(
        "aws_db_instance.main",
        before={"master": [{"pass": "CANARY-old"}]},
        after={"master": [{"pass": after}]},
        before_sensitive={"master": [{"pass": True}]},
        after_sensitive={"master": [{"pass": True}]},
    )
    found = list(sensitive.evaluate(context(raw)))
    assert [(item.severity, item.evidence[-1].text) for item in found] == (
        [(Severity.INFO, "master[0].pass")] if fires else []
    )
    assert "CANARY" not in repr(found)


def test_empty_secret_slot_becoming_null_is_no_change() -> None:
    # state keeps "" for an unset field; the replace plan shows null
    raw = resource_change(
        "aws_db_instance.main",
        actions=("delete", "create"),
        before={"domain_auth_secret_arn": "", "size": 1},
        after={"domain_auth_secret_arn": None, "size": 2},
    )
    assert list(sensitive.evaluate(context(raw))) == []


def test_only_configured_secrets_are_reported() -> None:
    raw = resource_change(
        "aws_db_instance.main",
        actions=("delete", "create"),
        before={"password": "CANARY-old", "master_user_secret": [{"arn": "CANARY-arn"}]},
        after={"password": "CANARY-new"},
        after_unknown={"master_user_secret": True},
    )
    (found,) = sensitive.evaluate(context(raw, configuration=configuration(raw, "password")))
    assert found.evidence[-1].text == "password"


def test_secret_unknown_until_apply_is_low_confidence() -> None:
    # the password comes from a random_password that is replaced too
    raw = resource_change(
        "aws_db_instance.main",
        actions=("delete", "create"),
        before={"password": "CANARY-old", "master_password": "CANARY-m"},
        after={},
        after_unknown={"password": True, "master_password": True},
    )
    declared = configuration(raw, "password", "master_password")
    (found,) = sensitive.evaluate(context(raw, configuration=declared))
    assert (found.rule, found.severity, found.confidence) == (
        sensitive.ID,
        Severity.INFO,
        Confidence.LOW,
    )
    assert (found.title, found.reason) == (
        "Sensitive value may change",
        "a secret or credential is unknown until apply",
    )
    assert found.evidence[-1] == Evidence("paths", "master_password, password")
    assert "CANARY" not in repr(found)
