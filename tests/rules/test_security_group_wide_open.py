import pytest

from factories import configuration, context, resource_change
from tfdiff.model.findings import Confidence, Severity
from tfdiff.rules.aws import security_group


def _ingress(
    port: int, cidr: str, protocol: str = "tcp", to_port: int | None = None
) -> dict[str, object]:
    return {
        "from_port": port,
        "to_port": port if to_port is None else to_port,
        "protocol": protocol,
        "cidr_blocks": [cidr],
        "ipv6_cidr_blocks": [],
    }


@pytest.mark.parametrize(
    ("ingress", "expected"),
    [
        (_ingress(22, "0.0.0.0/0"), Severity.CRITICAL),
        (_ingress(0, "0.0.0.0/0", "-1"), Severity.CRITICAL),
        (_ingress(8080, "0.0.0.0/0"), Severity.HIGH),
        (_ingress(443, "0.0.0.0/0"), None),
        (_ingress(22, "203.0.113.0/24"), None),
        (_ingress(-1, "0.0.0.0/0", "icmp"), None),
        # a range is critical when it spans an admin port, here 22 and 23
        (_ingress(20, "0.0.0.0/0", to_port=25), Severity.CRITICAL),
        (_ingress(8000, "0.0.0.0/0", to_port=8100), Severity.HIGH),
    ],
    ids=[
        "ssh",
        "all-traffic",
        "app-port",
        "https",
        "office-cidr",
        "icmp",
        "admin-range",
        "app-range",
    ],
)
def test_new_inline_ingress(ingress: dict[str, object], expected: Severity | None) -> None:
    raw = resource_change(
        "aws_security_group.bastion", before={"ingress": []}, after={"ingress": [ingress]}
    )
    found = list(security_group.evaluate(context(raw)))
    assert [item.severity for item in found] == ([] if expected is None else [expected])


def test_already_open_rule_is_not_new() -> None:
    ssh = _ingress(22, "0.0.0.0/0")
    raw = resource_change(
        "aws_security_group.bastion",
        before={"ingress": [ssh], "description": "a"},
        after={"ingress": [ssh], "description": "b"},
    )
    assert list(security_group.evaluate(context(raw))) == []


def test_standalone_ipv6_rule() -> None:
    raw = resource_change(
        "aws_vpc_security_group_ingress_rule.db",
        actions=("create",),
        after={"cidr_ipv6": "::/0", "ip_protocol": "tcp", "from_port": 5432, "to_port": 5432},
    )
    (found,) = security_group.evaluate(context(raw))
    assert found.severity is Severity.CRITICAL
    assert found.evidence[-1].text == "tcp ports 5432-5432 from ::/0"


def test_unknown_ports_on_world_rule_are_low_confidence() -> None:
    raw = resource_change(
        "aws_security_group_rule.app",
        actions=("create",),
        after={"type": "ingress", "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]},
        after_unknown={"from_port": True, "to_port": True},
    )
    (found,) = security_group.evaluate(context(raw))
    assert (found.severity, found.confidence) == (Severity.HIGH, Confidence.LOW)


@pytest.mark.parametrize(
    ("after", "unknown", "expected"),
    [
        (
            {"type": "ingress", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
            {"protocol": True},
            (Severity.CRITICAL, Confidence.LOW),
        ),
        (
            {"type": "ingress", "from_port": 8080, "to_port": 8080, "protocol": "tcp"},
            {"cidr_blocks": True},
            (Severity.HIGH, Confidence.LOW),
        ),
    ],
    ids=["unknown-protocol", "unknown-cidr"],
)
def test_unknown_deciding_value_is_low_confidence(
    after: object, unknown: object, expected: tuple[Severity, Confidence]
) -> None:
    raw = resource_change(
        "aws_security_group_rule.app", actions=("create",), after=after, after_unknown=unknown
    )
    (found,) = security_group.evaluate(context(raw))
    assert (found.severity, found.confidence) == expected


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(("ingress",), [(Severity.HIGH, Confidence.LOW)]), ((), [])],
    ids=["configured", "computed"],
)
def test_whole_ingress_list_unknown(
    configured: tuple[str, ...], expected: list[tuple[Severity, Confidence]]
) -> None:
    # a dynamic block over a value known only at apply
    raw = resource_change(
        "aws_security_group.app",
        actions=("delete", "create"),
        before={"ingress": [_ingress(443, "0.0.0.0/0")]},
        after={},
        after_unknown={"ingress": True},
    )
    found = security_group.evaluate(context(raw, configuration=configuration(raw, *configured)))
    assert [(item.severity, item.confidence) for item in found] == expected


def test_rule_direction_unknown_is_low_confidence() -> None:
    raw = resource_change(
        "aws_security_group_rule.ssh",
        actions=("create",),
        after={"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
        after_unknown={"type": True},
    )
    (found,) = security_group.evaluate(context(raw))
    assert (found.severity, found.confidence) == (Severity.CRITICAL, Confidence.LOW)


def test_doubtful_opening_does_not_hide_a_certain_one() -> None:
    # one finding per certainty: the certain port 8080 still fails `check`
    unsure = {"from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]}
    raw = resource_change(
        "aws_security_group.app",
        before={"ingress": []},
        after={"ingress": [unsure, _ingress(8080, "0.0.0.0/0")]},
        after_unknown={"ingress": [{"protocol": True}, {}]},
    )
    found = security_group.evaluate(context(raw))
    assert [(item.title, item.severity, item.confidence) for item in found] == [
        ("Ingress opened to the internet", Severity.HIGH, Confidence.HIGH),
        ("Ingress may open to the internet", Severity.CRITICAL, Confidence.LOW),
    ]
