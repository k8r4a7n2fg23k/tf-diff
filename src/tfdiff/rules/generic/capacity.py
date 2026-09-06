from collections.abc import Iterator

from tfdiff.model.diff import Kind
from tfdiff.model.findings import Confidence, Evidence, Finding, Severity
from tfdiff.model.plan import Action
from tfdiff.model.values import (
    Sensitive,
    Unknown,
    flag,
    indexes,
    number,
    show,
    show_path,
    value_at,
)
from tfdiff.rules.rule import Context, Rule, finding, leaf, transition

REDUCE = "reduce-capacity"
REDUNDANCY = "remove-redundancy"
DEFAULT_PERCENT = 30
MIN_SPREAD = 2

CAPACITY = frozenset(
    {
        "desired_capacity",
        "desired_count",
        "desired_size",
        "instance_count",
        "min_size",
        "node_count",
        "num_cache_nodes",
        "number_of_nodes",
        "replica_count",
        "replicas",
    }
)
SPREAD = frozenset({"availability_zones", "subnet_ids", "subnets", "vpc_zone_identifier", "zones"})


def reduce(context: Context) -> Iterator[Finding]:
    limit = context.threshold(REDUCE, DEFAULT_PERCENT)
    for attribute in context.attributes:
        before = number(attribute.before)
        if leaf(attribute.path) not in CAPACITY or before is None or before <= 0:
            continue
        evidence = [transition(attribute.path, attribute.before, attribute.after)]
        name = show_path(attribute.path)
        if attribute.kind is Kind.UNKNOWN:
            if context.is_configured(attribute.path):
                yield finding(
                    context,
                    REDUCE,
                    Severity.HIGH,
                    "Capacity may drop",
                    f"{name} is unknown until apply",
                    evidence,
                    Confidence.LOW,
                )
            continue
        after = number(attribute.after)
        if after is None:
            continue
        # compare without dividing: 100 -> 43 is 56.99999 percent in floats
        if (before - after) * 100 >= limit * before:
            drop = (before - after) / before * 100
            yield finding(
                context,
                REDUCE,
                Severity.HIGH,
                "Capacity reduced",
                f"{name} drops by {drop:.0f}% (threshold {limit}%)",
                evidence,
            )


def redundancy(context: Context) -> Iterator[Finding]:
    if context.change.action not in {Action.UPDATE, Action.REPLACE}:
        return
    yield from _spread(context)
    yield from _multi_az(context)


def _spread(context: Context) -> Iterator[Finding]:
    change = context.change
    lists = {
        key[:-1]
        for key, _ in change.before
        if len(key) >= 2 and isinstance(key[-1], int) and key[-2] in SPREAD  # noqa: PLR2004
    }
    # plain tuple order is safe: one parent never holds both an index and a name
    for prefix in sorted(lists):
        count = len(indexes(change.before, prefix))
        if count < MIN_SPREAD:
            continue
        name = show_path(prefix)
        marker = value_at(change.after, prefix)
        if isinstance(marker, Sensitive) and not marker.is_changed:
            continue
        # a list redacted as a whole hides its length as well as its entries
        if isinstance(marker, Unknown | Sensitive):
            if context.is_configured(prefix):
                yield finding(
                    context,
                    REDUNDANCY,
                    Severity.HIGH,
                    "Redundancy may drop",
                    f"{name} spans {count} entries now and is unknown until apply"
                    if isinstance(marker, Unknown)
                    else f"{name} spans {count} entries now and changes to a redacted value",
                    [Evidence(name, f"{count} -> {show(marker)}")],
                    Confidence.LOW,
                )
            continue
        remaining = len(indexes(change.after, prefix))
        if remaining <= 1:
            yield finding(
                context,
                REDUNDANCY,
                Severity.HIGH,
                "Redundancy removed",
                f"{name} drops from {count} entries to {remaining}",
                [Evidence(name, f"{count} -> {remaining}")],
            )


def _multi_az(context: Context) -> Iterator[Finding]:
    for attribute in context.attributes:
        if leaf(attribute.path) != "multi_az" or flag(attribute.before) is not True:
            continue
        evidence = [transition(attribute.path, attribute.before, attribute.after)]
        name = show_path(attribute.path)
        if flag(attribute.after) is False:
            yield finding(
                context,
                REDUNDANCY,
                Severity.HIGH,
                "Multi-AZ disabled",
                f"{name} turns off",
                evidence,
            )
        elif attribute.kind is Kind.UNKNOWN and context.is_configured(attribute.path):
            yield finding(
                context,
                REDUNDANCY,
                Severity.HIGH,
                "Multi-AZ may be disabled",
                f"{name} is unknown until apply",
                evidence,
                Confidence.LOW,
            )


REDUCE_RULE = Rule(
    REDUCE,
    "Capacity attribute drops by the threshold percent or more",
    Severity.HIGH,
    reduce,
    DEFAULT_PERCENT,
)
REDUNDANCY_RULE = Rule(
    REDUNDANCY,
    "Zone or subnet spread falls to one, or Multi-AZ is turned off",
    Severity.HIGH,
    redundancy,
)
