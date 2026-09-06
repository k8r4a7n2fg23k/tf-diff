import pytest

from factories import Raw, context, evidence, resource_change
from tfdiff.model.findings import Severity
from tfdiff.rules.generic import replace


def _replace(actions: tuple[str, ...]) -> Raw:
    return resource_change(
        "aws_instance.web",
        actions=actions,
        before={"ami": "ami-1", "tags": {"Name": "web"}},
        after={"ami": "ami-2", "tags": {"Name": "web"}},
        replace_paths=[["ami"]],
    )


@pytest.mark.parametrize(
    ("environment", "severity"),
    [("production", Severity.MEDIUM), ("dev", Severity.LOW)],
)
def test_replace_names_the_forcing_attribute(environment: str, severity: Severity) -> None:
    (found,) = replace.evaluate(context(_replace(("delete", "create")), environment=environment))
    assert found.severity is severity
    assert found.reason == "ami cannot be updated in place"
    texts = evidence(found)
    assert texts["ami"] == '"ami-1" -> "ami-2"'
    assert texts["order"].startswith("destroy before create")


def test_create_before_destroy_order_is_kept() -> None:
    (found,) = replace.evaluate(context(_replace(("create", "delete"))))
    assert evidence(found)["order"] == "create before destroy"


def test_in_place_update_is_silent() -> None:
    raw = resource_change("aws_instance.web", before={"ami": "a"}, after={"ami": "b"})
    assert list(replace.evaluate(context(raw, environment="production"))) == []
