from collections.abc import Iterator
from dataclasses import dataclass, replace

from tfdiff.model.findings import Confidence, Evidence, Finding, Severity
from tfdiff.model.plan import Action
from tfdiff.model.values import (
    Attributes,
    Known,
    Path,
    Unknown,
    Value,
    indexes,
    number,
    show,
    value_at,
)
from tfdiff.rules.rule import Context, Rule, finding

ID = "security-group-wide-open"

WORLD = frozenset({"0.0.0.0/0", "::/0"})
ALL_PROTOCOLS = frozenset({"-1", "all"})
ICMP = frozenset({"icmp", "icmpv6", "1", "58"})
WEB_PORTS = frozenset({80, 443})
# ssh, telnet, rdp, databases, caches, search, docker and etcd APIs
ADMIN_PORTS = frozenset(
    {22, 23, 1433, 1521, 2375, 2379, 3306, 3389, 5432, 5601, 6379, 9200, 11211, 27017}
)


@dataclass(frozen=True, slots=True, order=True)
class Opening:
    protocol: str
    ports: str
    source: str
    severity: Severity
    confidence: Confidence


def _assess(
    protocol: str, low: float | None, high: float | None
) -> tuple[Severity, Confidence] | None:
    if protocol in ICMP:
        return None
    if protocol in ALL_PROTOCOLS:
        return Severity.CRITICAL, Confidence.HIGH
    if low is None or high is None:
        return Severity.HIGH, Confidence.LOW
    if low == high and int(low) in WEB_PORTS:
        return None
    # an unknown protocol may still turn out to be icmp: keep the port verdict, drop the certainty
    confidence = Confidence.LOW if protocol == "?" else Confidence.HIGH
    if any(low <= port <= high for port in ADMIN_PORTS):
        return Severity.CRITICAL, confidence
    return Severity.HIGH, confidence


def _openings_of_rule(
    attributes: Attributes, prefix: Path, protocol_key: str, sources: list[Value]
) -> list[Opening]:
    named = value_at(attributes, (*prefix, protocol_key))
    # "?" stands for an unknown protocol
    protocol = str(named.value).lower() if isinstance(named, Known) else "?"
    low = number(value_at(attributes, (*prefix, "from_port")))
    high = number(value_at(attributes, (*prefix, "to_port")))
    if protocol in ALL_PROTOCOLS:
        low, high = 0, 65535
    assessed = _assess(protocol, low, high)
    if assessed is None:
        return []
    ports = "all" if (low, high) == (0, 65535) else f"{_port(low)}-{_port(high)}"
    found: list[Opening] = []
    for source in sources:
        if isinstance(source, Known) and source.value in WORLD:
            found.append(Opening(protocol, ports, str(source.value), *assessed))
        elif isinstance(source, Unknown):
            found.append(Opening(protocol, ports, show(source), assessed[0], Confidence.LOW))
    return found


def _port(value: float | None) -> str:
    return "?" if value is None else str(int(value))


def _cidrs(attributes: Attributes, prefix: Path) -> list[Value]:
    found: list[Value] = []
    for name in ("cidr_blocks", "ipv6_cidr_blocks"):
        block = (*prefix, name)
        marker = value_at(attributes, block)
        if isinstance(marker, Unknown):
            found.append(marker)
            continue
        found.extend(value_at(attributes, (*block, index)) for index in indexes(attributes, block))
    return found


# the whole rule list unknown: a dynamic block over a value computed at apply, say
HIDDEN = Opening("?", "?", "(known after apply)", Severity.HIGH, Confidence.LOW)


def openings(kind: str, attributes: Attributes) -> frozenset[Opening]:
    """Ingress rules open to the internet, as declared on a resource of type `kind`."""
    if kind == "aws_security_group":
        if isinstance(value_at(attributes, ("ingress",)), Unknown):
            return frozenset({HIDDEN})
        return frozenset(
            opening
            for index in indexes(attributes, ("ingress",))
            for opening in _openings_of_rule(
                attributes, ("ingress", index), "protocol", _cidrs(attributes, ("ingress", index))
            )
        )
    if kind == "aws_security_group_rule":
        direction = value_at(attributes, ("type",))
        found = _openings_of_rule(attributes, (), "protocol", _cidrs(attributes, ()))
        if isinstance(direction, Unknown):
            return frozenset(replace(opening, confidence=Confidence.LOW) for opening in found)
        return frozenset(found) if direction == Known("ingress") else frozenset()
    if kind == "aws_vpc_security_group_ingress_rule":
        sources = [value_at(attributes, ("cidr_ipv4",)), value_at(attributes, ("cidr_ipv6",))]
        return frozenset(_openings_of_rule(attributes, (), "ip_protocol", sources))
    return frozenset()


def evaluate(context: Context) -> Iterator[Finding]:
    change = context.change
    if change.action not in {Action.CREATE, Action.UPDATE, Action.REPLACE}:
        return
    kind = change.resource.type
    known = {
        (opening.protocol, opening.ports, opening.source)
        for opening in openings(kind, change.before)
    }
    new = sorted(
        opening
        for opening in openings(kind, change.after)
        if (opening.protocol, opening.ports, opening.source) not in known
        # ingress is optional and computed: unknown on every replace unless the author sets it
        and (opening != HIDDEN or context.is_configured(("ingress",)))
    )
    # certain and doubtful openings apart, or one unknown port would hide a certain one from `check`
    for group, title in (
        (
            [opening for opening in new if opening.confidence is Confidence.HIGH],
            "Ingress opened to the internet",
        ),
        (
            [opening for opening in new if opening.confidence is Confidence.LOW],
            "Ingress may open to the internet",
        ),
    ):
        if group:
            yield _finding(context, group, title)


def _finding(context: Context, group: list[Opening], title: str) -> Finding:
    sources = ", ".join(sorted({opening.source for opening in group}))
    return finding(
        context,
        ID,
        max((opening.severity for opening in group), key=lambda level: level.rank),
        title,
        f"{len(group)} ingress rule(s) newly open to {sources}",
        [
            Evidence("ingress", f"{opening.protocol} ports {opening.ports} from {opening.source}")
            for opening in group
        ],
        group[0].confidence,
    )


RULE = Rule(
    ID,
    "Security group ingress newly open to 0.0.0.0/0 or ::/0 (critical on admin/database ports)",
    Severity.CRITICAL,
    evaluate,
)
